import asyncio
from datetime import datetime

import cv2
from bson import ObjectId
from bson.errors import InvalidId
from fastapi import (
    APIRouter,
    BackgroundTasks,
    File,
    Form,
    HTTPException,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
)
from pydantic import BaseModel, Field, field_validator

from app.core.db import get_db
from app.core.storage import StorageManager
from app.models.schemas import AttendanceRecord, Student
from app.services.cell_extractor import CellExtractor
from app.services.evaluation import Evaluator
from app.services.grid_detector import GridDetector
from app.services.info_parser import InfoParser
from app.services.pipeline import Pipeline, PipelineResult
from app.services.presence_detector import PresenceDetector
from app.services.steps.base import PipelineStep
from app.services.steps.binarize import BinarizeStep
from app.services.steps.deskew import DeskewStep
from app.services.steps.denoise import DenoiseStep
from app.services.steps.grayscale import GrayscaleStep
from app.services.steps.resize import ResizeStep

router = APIRouter(prefix="/sheets", tags=["sheets"])


class ProcessOptions(BaseModel):
    """Every field beyond header_rows/signature_col is optional and defaults
    to None -- omitted fields fall through to the relevant service's own
    constructor default (see _non_null_kwargs and its call sites below), so
    a client only needs to send what it wants to override. Range bounds
    mirror the Settings page's sliders; FastAPI/pydantic reject anything
    outside them with a 422 automatically, no custom handling needed.
    """

    header_rows: int = Field(default=1, ge=0, le=3)
    signature_col: int = -1

    # PROCESSING -- ResizeStep / DeskewStep
    resize_width: int | None = Field(default=None, ge=800, le=3000)
    adaptive_block_size: int | None = Field(default=None, ge=11, le=51)
    adaptive_constant: int | None = Field(default=None, ge=2, le=30)
    deskew_search_range_degrees: float | None = Field(default=None, ge=2, le=15)

    # GRID DETECTION -- GridDetector
    horizontal_threshold_fraction: float | None = Field(default=None, ge=0.05, le=0.60)
    vertical_threshold_fraction: float | None = Field(default=None, ge=0.05, le=0.60)
    horizontal_kernel_scale: int | None = Field(default=None, ge=10, le=60)
    vertical_kernel_scale: int | None = Field(default=None, ge=10, le=60)
    min_cols: int | None = Field(default=None, ge=2, le=8)

    # CELL EXTRACTION -- CellExtractor
    signature_horizontal_shrink: float | None = Field(default=None, ge=0.0, le=0.25)
    signature_vertical_shrink: float | None = Field(default=None, ge=0.0, le=0.25)
    signature_vertical_expansion: float | None = Field(default=None, ge=0.0, le=0.25)
    presence_horizontal_shrink: float | None = Field(default=None, ge=0.0, le=0.25)
    presence_vertical_shrink: float | None = Field(default=None, ge=0.0, le=0.25)

    # PRESENCE DETECTION -- PresenceDetector
    min_ink_ratio: float | None = Field(default=None, ge=0.005, le=0.20)
    min_component_area: int | None = Field(default=None, ge=10, le=500)

    # SIGNATURE MATCHING -- SignatureMatcher. Not consumed during processing
    # itself (signature matching only ever runs later, across sessions, when
    # the review queue is built) -- stored on this session's document instead
    # and applied when SignatureMatcher compares one of *this* session's
    # crops; see app/api/routes/signatures.py's _matcher_for_session.
    similarity_threshold: float | None = Field(default=None, ge=0.1, le=0.95)
    orb_nfeatures: int | None = Field(default=None, ge=100, le=2000)
    min_keypoints: int | None = Field(default=None, ge=5, le=50)

    @field_validator("adaptive_block_size")
    @classmethod
    def _validate_odd_block_size(cls, value: int | None) -> int | None:
        if value is not None and value % 2 == 0:
            raise ValueError("adaptive_block_size must be an odd number")
        return value


# session_id -> queues of subscribed /sheets/ws/{id} connections.
_progress_subscribers: dict[str, list[asyncio.Queue]] = {}

# Pipeline.run() only knows about its own 5 image-transform steps; grid
# detection, cell extraction and presence detection (6-8) run afterward in
# _run_cv_pipeline itself, so this is the one place that knows the true
# total across all 8 stages.
TOTAL_STAGES = 8


def _to_object_id(session_id: str) -> ObjectId:
    try:
        return ObjectId(session_id)
    except (InvalidId, TypeError):
        raise HTTPException(status_code=400, detail="Invalid session id") from None


def _broadcast_progress(session_id: str, event: dict) -> None:
    for queue in _progress_subscribers.get(session_id, []):
        queue.put_nowait(event)


def _non_null_kwargs(**values: object) -> dict[str, object]:
    """Drop any keyword whose value is None, so a constructor call built
    from an optional ProcessOptions field falls through to that
    constructor's own default instead of being explicitly passed None.
    """
    return {key: value for key, value in values.items() if value is not None}


def _build_pipeline_steps(options: ProcessOptions) -> list[PipelineStep]:
    return [
        ResizeStep(order=1, **_non_null_kwargs(target_width=options.resize_width)),
        GrayscaleStep(order=2),
        DenoiseStep(order=3),
        DeskewStep(
            order=4,
            **_non_null_kwargs(
                adaptive_block_size=options.adaptive_block_size,
                adaptive_c=options.adaptive_constant,
                coarse_range_degrees=options.deskew_search_range_degrees,
            ),
        ),
        BinarizeStep(order=5),
    ]


def _run_cv_pipeline(
    session_id: str,
    image_path: str,
    storage: StorageManager,
    loop: asyncio.AbstractEventLoop,
    students: list[Student],
    options: ProcessOptions,
) -> tuple[PipelineResult, list[dict]]:
    """All OpenCV work for one session, run off the event loop by the caller
    via loop.run_in_executor. Returns the pipeline result plus one attendance
    entry per detected row (student assignment happens back on the event loop).
    """

    def broadcast(event: dict) -> None:
        loop.call_soon_threadsafe(_broadcast_progress, session_id, event)

    def progress_callback(step_name: str, order: int, total: int, path: str) -> None:
        # Pipeline.run only calls this after a step finishes (see pipeline.py),
        # so "done" is the only accurate status here. The frontend's
        # ProcessingEvent type requires this field on every message -- without
        # it, StepState.status ends up undefined and the icon lookup in
        # PipelineStepper crashes React's renderer.
        #
        # `total` here is Pipeline.run()'s own count of its 5 image-transform
        # steps -- it has no idea grid detection/cell extraction/presence
        # detection (6-8) run afterward in this same function, so its total
        # is overridden with the real 8-stage count rather than passed
        # through as-is.
        event = {
            "step": step_name,
            "order": order,
            "total": TOTAL_STAGES,
            "path": path,
            "status": "done",
        }
        broadcast(event)

    signature_col = options.signature_col

    pipeline = Pipeline(_build_pipeline_steps(options), storage=storage)
    result = pipeline.run(image_path, session_id, progress_callback=progress_callback)

    broadcast({"step": "Grid Detection", "order": 6, "total": TOTAL_STAGES, "status": "running"})
    # storage=storage: without it, GridDetector falls back to its own
    # default StorageManager(), which only happens to write to the same
    # place as this function's `storage` because neither overrides the
    # root -- the debug path broadcast just below needs this to actually be
    # the same instance, not merely the same default by coincidence.
    grid_detector = GridDetector(
        header_rows=options.header_rows,
        storage=storage,
        **_non_null_kwargs(
            horizontal_threshold_fraction=options.horizontal_threshold_fraction,
            vertical_threshold_fraction=options.vertical_threshold_fraction,
            horizontal_kernel_scale=options.horizontal_kernel_scale,
            vertical_kernel_scale=options.vertical_kernel_scale,
            min_cols=options.min_cols,
        ),
    )
    rows = grid_detector.detect(result.final_image, session_id=session_id)
    rows = grid_detector.drop_header_rows(rows, expected_row_count=len(students))
    # GridDetector writes this debug image itself (see grid_detector.py);
    # reconstructed here rather than returned, since detect() only returns
    # the detected rows.
    grid_debug_path = StorageManager._to_relative(
        storage.root / "steps" / session_id / "06d_cells.png"
    )
    broadcast(
        {
            "step": "Grid Detection",
            "order": 6,
            "total": TOTAL_STAGES,
            "path": grid_debug_path,
            "status": "done",
        }
    )

    # The grid was detected on the deskewed grayscale/binary branch; crops
    # must come from the color frame warped through that same deskew (see
    # Pipeline.run), not the original un-rotated upload.
    color_aligned = result.context["color_aligned"]

    CellExtractor.validate_alignment(rows, students)

    broadcast({"step": "Cell Extraction", "order": 7, "total": TOTAL_STAGES, "status": "running"})
    cell_extractor = CellExtractor(
        session_id,
        storage=storage,
        signature_col=signature_col,
        **_non_null_kwargs(
            horizontal_shrink_ratio=options.signature_horizontal_shrink,
            vertical_shrink_ratio=options.signature_vertical_shrink,
            vertical_expansion_ratio=options.signature_vertical_expansion,
            presence_horizontal_shrink_ratio=options.presence_horizontal_shrink,
            presence_vertical_shrink_ratio=options.presence_vertical_shrink,
        ),
    )
    crops, presence_crops = cell_extractor.extract_signature_cells(color_aligned, rows)
    cell_extraction_event = {
        "step": "Cell Extraction",
        "order": 7,
        "total": TOTAL_STAGES,
        "status": "done",
    }
    if rows:
        # Same path CellExtractor itself just wrote row 0's crop to.
        first_col_index = signature_col % len(rows[0])
        cell_extraction_event["path"] = storage.step_path(
            session_id, 0, f"signature_col{first_col_index}.png"
        )
    broadcast(cell_extraction_event)

    broadcast({"step": "Presence Detection", "order": 8, "total": TOTAL_STAGES, "status": "running"})
    presence_detector = PresenceDetector(
        **_non_null_kwargs(
            min_ink_ratio=options.min_ink_ratio,
            min_component_area=options.min_component_area,
        )
    )
    attendance_raw: list[dict] = []
    for row_index, row in enumerate(rows):
        if row_index >= len(crops):
            continue
        col_index = signature_col % len(row)
        present, ink_ratio, confidence = presence_detector.is_present(
            presence_crops[row_index], row_index=row_index
        )
        attendance_raw.append(
            {
                "row_index": row_index,
                "present": present,
                "ink_ratio": ink_ratio,
                "confidence": confidence,
                "cell_bbox": list(row[col_index]),
                "cell_image": storage.step_path(
                    session_id, row_index, f"signature_col{col_index}.png"
                ),
            }
        )

    # PresenceDetector.is_present() is a pure computation with no image
    # output of its own, so the report gets one built here: every detected
    # cell boxed in green (present) / red (absent) over the same aligned
    # color frame the crops themselves came from, labelled with the student
    # index and ink ratio that drove the present/absent call.
    students_by_row_no = {student.row_no: student for student in students}
    presence_canvas = color_aligned.copy()
    for entry in attendance_raw:
        x, y, w, h = entry["cell_bbox"]
        color = (0, 255, 0) if entry["present"] else (0, 0, 255)
        cv2.rectangle(presence_canvas, (x, y), (x + w, y + h), color, 2)

        student = students_by_row_no.get(entry["row_index"] + 1)
        label = f"{student.index if student else '?'} {entry['ink_ratio']:.3f}"
        cv2.putText(
            presence_canvas,
            label,
            (x, max(y - 6, 12)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.45,
            color,
            1,
            cv2.LINE_AA,
        )

    presence_debug_path = storage.step_path(session_id, 8, "presence.png")
    cv2.imwrite(presence_debug_path, presence_canvas)

    broadcast(
        {
            "step": "Presence Detection",
            "order": 8,
            "total": TOTAL_STAGES,
            "path": presence_debug_path,
            "status": "done",
        }
    )

    return result, attendance_raw


async def _process_session(session_id: str, options: ProcessOptions) -> None:
    db = get_db()
    object_id = _to_object_id(session_id)
    session_doc = await db.sessions.find_one({"_id": object_id})
    if session_doc is None:
        return

    storage = StorageManager()
    loop = asyncio.get_running_loop()

    try:
        students = InfoParser().parse_students(session_doc["info_xml_path"])
        students_by_row_no = {student.row_no: student for student in students}

        result, attendance_raw = await loop.run_in_executor(
            None,
            _run_cv_pipeline,
            session_id,
            session_doc["image_path"],
            storage,
            loop,
            students,
            options,
        )

        attendance_docs = []
        for entry in attendance_raw:
            row_index = entry["row_index"]
            # Table rows are 0-indexed post header-drop; a student's row_no is
            # its 1-indexed position in info.xml document order (InfoParser),
            # so row_index + 1 is the row_no to look up.
            student = students_by_row_no.get(row_index + 1)
            if student is None:
                continue
            record = AttendanceRecord(
                session_id=session_id,
                student_index=student.index,
                present=entry["present"],
                ink_ratio=entry["ink_ratio"],
                cell_bbox=entry["cell_bbox"],
                cell_image=entry["cell_image"],
                confidence=entry["confidence"],
            )
            attendance_docs.append(record.model_dump())

        if attendance_docs:
            await db.attendance.delete_many({"session_id": session_id})
            await db.attendance.insert_many(attendance_docs)

        await db.sessions.update_one(
            {"_id": object_id},
            {
                "$set": {
                    "status": "processed",
                    "steps": [step.model_dump() for step in result.steps],
                }
            },
        )
        # Distinct from the per-step "done" events above: this is the only
        # signal the frontend should treat as "processing is actually
        # finished" -- sent after the attendance write and status update are
        # both confirmed, not when the last CV step merely finishes running.
        _broadcast_progress(
            session_id,
            {
                "status": "complete",
                "session_id": session_id,
                "record_count": len(attendance_docs),
            },
        )
    except Exception as exc:  # noqa: BLE001 - surface failure to the session record
        await db.sessions.update_one(
            {"_id": object_id}, {"$set": {"status": "failed"}}
        )
        # "message", not "error" -- ProcessingEvent.message is what the
        # frontend's onError handler actually reads.
        _broadcast_progress(session_id, {"status": "failed", "message": str(exc)})


@router.post("/upload")
async def upload_sheet(
    image: UploadFile = File(...),
    info_xml: UploadFile = File(...),
    subject_code: str = Form(...),
    session_date: str = Form(...),
) -> dict:
    db = get_db()
    storage = StorageManager()

    now = datetime.utcnow()
    insert_result = await db.sessions.insert_one(
        {
            "subject_code": subject_code,
            "date": session_date,
            "original_filename": image.filename,
            "image_path": "",
            "info_xml_path": "",
            "status": "uploaded",
            "steps": [],
            "uploaded_at": now,
        }
    )
    session_id = str(insert_result.inserted_id)

    image_path = storage.save_upload(session_id, image.filename, await image.read())
    xml_path = storage.save_upload(session_id, info_xml.filename, await info_xml.read())

    await db.sessions.update_one(
        {"_id": insert_result.inserted_id},
        {"$set": {"image_path": image_path, "info_xml_path": xml_path}},
    )

    try:
        students = InfoParser().parse_students(xml_path)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    for student in students:
        await db.students.update_one(
            {"index": student.index}, {"$set": student.model_dump()}, upsert=True
        )

    return {
        "session_id": session_id,
        "student_count": len(students),
    }


@router.post("/{session_id}/process")
async def process_sheet(
    session_id: str,
    background_tasks: BackgroundTasks,
    options: ProcessOptions | None = None,
) -> dict:
    db = get_db()
    object_id = _to_object_id(session_id)
    session_doc = await db.sessions.find_one({"_id": object_id})
    if session_doc is None:
        raise HTTPException(status_code=404, detail="Session not found")

    resolved_options = options or ProcessOptions()

    # Stored in full (including the signature-matching fields _run_cv_pipeline
    # never touches) so signatures.py can later read this session's own
    # similarity_threshold/orb_nfeatures/min_keypoints when it constructs a
    # SignatureMatcher for crops that came from this session -- see
    # _matcher_for_session there.
    await db.sessions.update_one(
        {"_id": object_id},
        {"$set": {"status": "processing", "processing_options": resolved_options.model_dump()}},
    )
    background_tasks.add_task(_process_session, session_id, resolved_options)

    return {"session_id": session_id, "status": "processing"}


@router.get("")
async def list_sessions(
    subject_code: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    status: str | None = None,
    limit: int = 50,
    skip: int = 0,
) -> list[dict]:
    db = get_db()

    query: dict = {}
    if subject_code:
        query["subject_code"] = subject_code
    if status:
        query["status"] = status
    if date_from or date_to:
        date_query: dict = {}
        if date_from:
            date_query["$gte"] = date_from
        if date_to:
            date_query["$lte"] = date_to
        query["date"] = date_query

    session_docs = await (
        db.sessions.find(query).sort("uploaded_at", -1).skip(skip).limit(limit).to_list(length=None)
    )
    if not session_docs:
        return []

    session_ids = [str(doc["_id"]) for doc in session_docs]
    attendance_records = await db.attendance.find(
        {"session_id": {"$in": session_ids}}
    ).to_list(length=None)

    counts: dict[str, dict[str, int]] = {}
    for record in attendance_records:
        entry = counts.setdefault(record["session_id"], {"detected": 0, "present": 0})
        entry["detected"] += 1
        if record.get("present"):
            entry["present"] += 1

    items = []
    for doc in session_docs:
        session_id = str(doc["_id"])
        entry = counts.get(session_id, {"detected": 0, "present": 0})
        items.append(
            {
                "id": session_id,
                "subject_code": doc.get("subject_code"),
                "date": doc.get("date"),
                "original_filename": doc.get("original_filename"),
                "status": doc.get("status"),
                "uploaded_at": doc.get("uploaded_at"),
                "students_detected": entry["detected"],
                "present_count": entry["present"],
                "absent_count": entry["detected"] - entry["present"],
            }
        )

    return items


@router.get("/{session_id}/steps")
async def get_steps(session_id: str) -> list[dict]:
    db = get_db()
    session_doc = await db.sessions.find_one({"_id": _to_object_id(session_id)})
    if session_doc is None:
        raise HTTPException(status_code=404, detail="Session not found")

    return session_doc.get("steps", [])


@router.get("/{session_id}/results")
async def get_results(session_id: str) -> list[dict]:
    db = get_db()
    records = await db.attendance.find({"session_id": session_id}).to_list(length=None)
    for record in records:
        record["_id"] = str(record["_id"])
    return records


@router.get("/{session_id}/evaluation")
async def get_evaluation(session_id: str) -> dict:
    try:
        return await Evaluator().evaluate(session_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.websocket("/ws/{session_id}")
async def sheet_progress_ws(websocket: WebSocket, session_id: str) -> None:
    await websocket.accept()
    queue: asyncio.Queue = asyncio.Queue()
    _progress_subscribers.setdefault(session_id, []).append(queue)

    try:
        while True:
            event = await queue.get()
            await websocket.send_json(event)
    except WebSocketDisconnect:
        pass
    finally:
        subscribers = _progress_subscribers.get(session_id, [])
        if queue in subscribers:
            subscribers.remove(queue)
