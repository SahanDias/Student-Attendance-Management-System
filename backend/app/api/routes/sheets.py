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


# ============================================================================
# ROUTER CONFIGURATION
# ============================================================================

router = APIRouter(
    prefix="/sheets",
    tags=["sheets"],
)


# ============================================================================
# PROCESSING OPTIONS
# ============================================================================

class ProcessOptions(BaseModel):
    """
    Optional configuration values for the attendance-sheet processing
    pipeline.

    The main processing settings are optional. When a setting is omitted,
    None is passed internally and _non_null_kwargs() removes it before the
    relevant service is constructed. This allows the service itself to use
    its own default value.

    The available ranges mirror the processing settings exposed by the
    frontend Settings page. Pydantic/FastAPI automatically rejects values
    outside the defined ranges with HTTP 422.
    """

    # ------------------------------------------------------------------------
    # GENERAL SHEET SETTINGS
    # ------------------------------------------------------------------------

    header_rows: int = Field(
        default=1,
        ge=0,
        le=3,
    )

    signature_col: int = -1

    # ------------------------------------------------------------------------
    # IMAGE PROCESSING
    # ResizeStep / DeskewStep
    # ------------------------------------------------------------------------

    resize_width: int | None = Field(
        default=None,
        ge=800,
        le=3000,
    )

    adaptive_block_size: int | None = Field(
        default=None,
        ge=11,
        le=51,
    )

    adaptive_constant: int | None = Field(
        default=None,
        ge=2,
        le=30,
    )

    deskew_search_range_degrees: float | None = Field(
        default=None,
        ge=2,
        le=15,
    )

    # ------------------------------------------------------------------------
    # GRID DETECTION
    # GridDetector
    # ------------------------------------------------------------------------

    horizontal_threshold_fraction: float | None = Field(
        default=None,
        ge=0.05,
        le=0.60,
    )

    vertical_threshold_fraction: float | None = Field(
        default=None,
        ge=0.05,
        le=0.60,
    )

    horizontal_kernel_scale: int | None = Field(
        default=None,
        ge=10,
        le=60,
    )

    vertical_kernel_scale: int | None = Field(
        default=None,
        ge=10,
        le=60,
    )

    min_cols: int | None = Field(
        default=None,
        ge=2,
        le=8,
    )

    # ------------------------------------------------------------------------
    # CELL EXTRACTION
    # CellExtractor
    # ------------------------------------------------------------------------

    signature_horizontal_shrink: float | None = Field(
        default=None,
        ge=0.0,
        le=0.25,
    )

    signature_vertical_shrink: float | None = Field(
        default=None,
        ge=0.0,
        le=0.25,
    )

    signature_vertical_expansion: float | None = Field(
        default=None,
        ge=0.0,
        le=0.25,
    )

    presence_horizontal_shrink: float | None = Field(
        default=None,
        ge=0.0,
        le=0.25,
    )

    presence_vertical_shrink: float | None = Field(
        default=None,
        ge=0.0,
        le=0.25,
    )

    # ------------------------------------------------------------------------
    # PRESENCE DETECTION
    # PresenceDetector
    # ------------------------------------------------------------------------

    min_ink_ratio: float | None = Field(
        default=None,
        ge=0.005,
        le=0.20,
    )

    min_component_area: int | None = Field(
        default=None,
        ge=10,
        le=500,
    )

    # ------------------------------------------------------------------------
    # SIGNATURE MATCHING
    #
    # These values are not used while the image-processing pipeline is
    # running. They are stored with the session and later consumed by
    # signatures.py when SignatureMatcher is created for this session.
    # ------------------------------------------------------------------------

    similarity_threshold: float | None = Field(
        default=None,
        ge=0.1,
        le=0.95,
    )

    orb_nfeatures: int | None = Field(
        default=None,
        ge=100,
        le=2000,
    )

    min_keypoints: int | None = Field(
        default=None,
        ge=5,
        le=50,
    )

    # ------------------------------------------------------------------------
    # VALIDATION
    # ------------------------------------------------------------------------

    @field_validator("adaptive_block_size")
    @classmethod
    def _validate_odd_block_size(
        cls,
        value: int | None,
    ) -> int | None:
        """
        OpenCV adaptive thresholding requires an odd block size.

        Keeping this validation here means invalid values are rejected before
        processing begins.
        """
        if value is not None and value % 2 == 0:
            raise ValueError(
                "adaptive_block_size must be an odd number"
            )

        return value


# ============================================================================
# PROCESSING PROGRESS SUBSCRIBERS
# ============================================================================
#
# Each processing session has zero or more WebSocket subscribers.
#
# session_id
#     |
#     +-- Queue 1 -> WebSocket client
#     +-- Queue 2 -> WebSocket client
#     +-- Queue 3 -> WebSocket client
#
# Progress events are pushed into these queues as the processing pipeline
# advances.
# ============================================================================

_progress_subscribers: dict[str, list[asyncio.Queue]] = {}


# ============================================================================
# PIPELINE CONFIGURATION
# ============================================================================

# Pipeline.run() contains the first five image-processing stages.
#
# Stages 6-8 are performed afterward inside _run_cv_pipeline():
#
#   6. Grid Detection
#   7. Cell Extraction
#   8. Presence Detection
#
# Therefore, the frontend must always receive the real total number of
# processing stages rather than Pipeline.run()'s internal count of five.
TOTAL_STAGES = 8


# ============================================================================
# OBJECT ID HELPER
# ============================================================================

def _to_object_id(session_id: str) -> ObjectId:
    """
    Convert a session ID string into a MongoDB ObjectId.

    A consistent HTTP 400 response is returned when the supplied ID is
    malformed.
    """
    try:
        return ObjectId(session_id)

    except (InvalidId, TypeError):
        raise HTTPException(
            status_code=400,
            detail="Invalid session id",
        ) from None


# ============================================================================
# PROGRESS BROADCASTING
# ============================================================================

def _broadcast_progress(
    session_id: str,
    event: dict,
) -> None:
    """
    Send a processing event to every WebSocket subscriber belonging to the
    supplied session.

    put_nowait() is intentionally used because this function may be invoked
    from a worker thread through the event loop.
    """
    for queue in _progress_subscribers.get(session_id, []):
        queue.put_nowait(event)


# ============================================================================
# OPTIONAL CONSTRUCTOR ARGUMENT HELPER
# ============================================================================

def _non_null_kwargs(
    **values: object,
) -> dict[str, object]:
    """
    Remove optional constructor arguments whose value is None.

    This is important because:

        None

    should mean:

        "Do not override the service's own default."

    Instead of explicitly passing None into the service constructor, the
    corresponding keyword is omitted completely.
    """
    return {
        key: value
        for key, value in values.items()
        if value is not None
    }


# ============================================================================
# PIPELINE STEP CONSTRUCTION
# ============================================================================

def _build_pipeline_steps(
    options: ProcessOptions,
) -> list[PipelineStep]:
    """
    Construct the five image-processing steps used by Pipeline.run().

    The remaining three stages are executed separately in
    _run_cv_pipeline(), because they depend on the intermediate pipeline
    result and student information.
    """

    return [
        # Stage 1 ------------------------------------------------------------
        ResizeStep(
            order=1,
            **_non_null_kwargs(
                target_width=options.resize_width,
            ),
        ),

        # Stage 2 ------------------------------------------------------------
        GrayscaleStep(
            order=2,
        ),

        # Stage 3 ------------------------------------------------------------
        DenoiseStep(
            order=3,
        ),

        # Stage 4 ------------------------------------------------------------
        DeskewStep(
            order=4,
            **_non_null_kwargs(
                adaptive_block_size=options.adaptive_block_size,
                adaptive_c=options.adaptive_constant,
                coarse_range_degrees=(
                    options.deskew_search_range_degrees
                ),
            ),
        ),

        # Stage 5 ------------------------------------------------------------
        BinarizeStep(
            order=5,
        ),
    ]


# ============================================================================
# OPENCV PROCESSING PIPELINE
# ============================================================================

def _run_cv_pipeline(
    session_id: str,
    image_path: str,
    storage: StorageManager,
    loop: asyncio.AbstractEventLoop,
    students: list[Student],
    options: ProcessOptions,
) -> tuple[PipelineResult, list[dict]]:
    """
    Execute all computer-vision processing for a single attendance sheet.

    This function is deliberately executed outside the main asyncio event
    loop by _process_session().

    Processing stages:

        1. Resize
        2. Grayscale
        3. Denoise
        4. Deskew
        5. Binarize
        6. Grid Detection
        7. Cell Extraction
        8. Presence Detection

    Returns:
        (
            PipelineResult,
            attendance_raw
        )

    Student assignment to attendance rows is intentionally performed later
    on the event loop in _process_session().
    """

    # ------------------------------------------------------------------------
    # Thread-safe progress callback
    # ------------------------------------------------------------------------

    def broadcast(event: dict) -> None:
        """
        Safely transfer a progress event from the worker thread to the
        asyncio event loop.
        """
        loop.call_soon_threadsafe(
            _broadcast_progress,
            session_id,
            event,
        )

    # ------------------------------------------------------------------------
    # Pipeline progress callback
    # ------------------------------------------------------------------------

    def progress_callback(
        step_name: str,
        order: int,
        total: int,
        path: str,
    ) -> None:
        """
        Handle completion events emitted by Pipeline.run().

        Pipeline.run() knows only about its five internal image-transform
        steps. The public processing pipeline has eight stages, so the total
        sent to the frontend is explicitly replaced with TOTAL_STAGES.

        Every processing event includes status="done" because Pipeline.run()
        invokes this callback after a step has completed.
        """

        event = {
            "step": step_name,
            "order": order,
            "total": TOTAL_STAGES,
            "path": path,
            "status": "done",
        }

        broadcast(event)

    # ------------------------------------------------------------------------
    # Read signature column configuration
    # ------------------------------------------------------------------------

    signature_col = options.signature_col

    # ------------------------------------------------------------------------
    # Stages 1-5: Image processing pipeline
    # ------------------------------------------------------------------------

    pipeline = Pipeline(
        _build_pipeline_steps(options),
        storage=storage,
    )

    result = pipeline.run(
        image_path,
        session_id,
        progress_callback=progress_callback,
    )

    # ------------------------------------------------------------------------
    # Stage 6: Grid Detection
    # ------------------------------------------------------------------------

    broadcast(
        {
            "step": "Grid Detection",
            "order": 6,
            "total": TOTAL_STAGES,
            "status": "running",
        }
    )

    grid_detector = GridDetector(
        header_rows=options.header_rows,
        storage=storage,
        **_non_null_kwargs(
            horizontal_threshold_fraction=(
                options.horizontal_threshold_fraction
            ),
            vertical_threshold_fraction=(
                options.vertical_threshold_fraction
            ),
            horizontal_kernel_scale=(
                options.horizontal_kernel_scale
            ),
            vertical_kernel_scale=(
                options.vertical_kernel_scale
            ),
            min_cols=options.min_cols,
        ),
    )

    # Detect table rows/cells from the processed image.
    rows = grid_detector.detect(
        result.final_image,
        session_id=session_id,
    )

    # Remove header rows so that the remaining rows correspond to students.
    rows = grid_detector.drop_header_rows(
        rows,
        expected_row_count=len(students),
    )

    # GridDetector writes this debugging image internally. Reconstruct the
    # relative storage path here so that it can be sent to the frontend.
    grid_debug_path = StorageManager._to_relative(
        storage.root
        / "steps"
        / session_id
        / "06d_cells.png"
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

    # ------------------------------------------------------------------------
    # Color alignment
    # ------------------------------------------------------------------------
    #
    # Grid detection operates on the processed image branch. Signature
    # crops must instead come from the color image after the same deskew
    # transformation.
    # ------------------------------------------------------------------------

    color_aligned = result.context["color_aligned"]

    # Make sure detected rows are compatible with the student list before
    # attempting cell extraction.
    CellExtractor.validate_alignment(
        rows,
        students,
    )

    # ------------------------------------------------------------------------
    # Stage 7: Cell Extraction
    # ------------------------------------------------------------------------

    broadcast(
        {
            "step": "Cell Extraction",
            "order": 7,
            "total": TOTAL_STAGES,
            "status": "running",
        }
    )

    cell_extractor = CellExtractor(
        session_id,
        storage=storage,
        signature_col=signature_col,
        **_non_null_kwargs(
            horizontal_shrink_ratio=(
                options.signature_horizontal_shrink
            ),
            vertical_shrink_ratio=(
                options.signature_vertical_shrink
            ),
            vertical_expansion_ratio=(
                options.signature_vertical_expansion
            ),
            presence_horizontal_shrink_ratio=(
                options.presence_horizontal_shrink
            ),
            presence_vertical_shrink_ratio=(
                options.presence_vertical_shrink
            ),
        ),
    )

    # Extract both:
    #
    #   crops
    #       signature crops
    #
    #   presence_crops
    #       crops used by PresenceDetector
    #
    crops, presence_crops = (
        cell_extractor.extract_signature_cells(
            color_aligned,
            rows,
        )
    )

    cell_extraction_event = {
        "step": "Cell Extraction",
        "order": 7,
        "total": TOTAL_STAGES,
        "status": "done",
    }

    # CellExtractor writes the first extracted crop into the corresponding
    # step directory. Include that path in the frontend event when rows
    # exist.
    if rows:
        first_col_index = signature_col % len(rows[0])

        cell_extraction_event["path"] = storage.step_path(
            session_id,
            0,
            f"signature_col{first_col_index}.png",
        )

    broadcast(cell_extraction_event)

    # ------------------------------------------------------------------------
    # Stage 8: Presence Detection
    # ------------------------------------------------------------------------

    broadcast(
        {
            "step": "Presence Detection",
            "order": 8,
            "total": TOTAL_STAGES,
            "status": "running",
        }
    )

    presence_detector = PresenceDetector(
        **_non_null_kwargs(
            min_ink_ratio=options.min_ink_ratio,
            min_component_area=options.min_component_area,
        ),
    )

    # Each dictionary represents one detected attendance row.
    attendance_raw: list[dict] = []

    for row_index, row in enumerate(rows):

        # Safety check in case fewer crops were generated than detected rows.
        if row_index >= len(crops):
            continue

        # Support negative signature_col values such as -1.
        col_index = signature_col % len(row)

        present, ink_ratio, confidence = (
            presence_detector.is_present(
                presence_crops[row_index],
                row_index=row_index,
            )
        )

        attendance_raw.append(
            {
                "row_index": row_index,
                "present": present,
                "ink_ratio": ink_ratio,
                "confidence": confidence,

                # Bounding box of the detected signature cell.
                "cell_bbox": list(
                    row[col_index]
                ),

                # Stored signature-cell image path.
                "cell_image": storage.step_path(
                    session_id,
                    row_index,
                    f"signature_col{col_index}.png",
                ),
            }
        )

    # ------------------------------------------------------------------------
    # Build Presence Detection debug image
    # ------------------------------------------------------------------------
    #
    # PresenceDetector itself performs computation only and does not create
    # an annotated image. Therefore an annotated copy of the aligned color
    # frame is created here.
    #
    # Present -> green rectangle
    # Absent  -> red rectangle
    #
    # Each cell is also labelled with:
    #
    #   student index
    #   ink ratio
    # ------------------------------------------------------------------------

    students_by_row_no = {
        student.row_no: student
        for student in students
    }

    presence_canvas = color_aligned.copy()

    for entry in attendance_raw:

        x, y, w, h = entry["cell_bbox"]

        # OpenCV uses BGR.
        color = (
            (0, 255, 0)
            if entry["present"]
            else (0, 0, 255)
        )

        # Draw attendance result around the detected cell.
        cv2.rectangle(
            presence_canvas,
            (x, y),
            (x + w, y + h),
            color,
            2,
        )

        # InfoParser uses 1-based row numbers.
        student = students_by_row_no.get(
            entry["row_index"] + 1
        )

        label = (
            f"{student.index if student else '?'} "
            f"{entry['ink_ratio']:.3f}"
        )

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

    # Store the annotated presence-detection image.
    presence_debug_path = storage.step_path(
        session_id,
        8,
        "presence.png",
    )

    cv2.imwrite(
        presence_debug_path,
        presence_canvas,
    )

    # Notify frontend that Stage 8 has finished.
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


# ============================================================================
# BACKGROUND SESSION PROCESSING
# ============================================================================

async def _process_session(
    session_id: str,
    options: ProcessOptions,
) -> None:
    """
    Process one uploaded attendance-sheet session in the background.

    Database responsibilities:

        1. Load session
        2. Parse students
        3. Execute OpenCV pipeline
        4. Convert raw attendance to AttendanceRecord documents
        5. Replace previous attendance records
        6. Mark session as processed
        7. Broadcast completion

    If any stage fails, the session is marked as failed and a WebSocket
    failure event is sent to connected clients.
    """

    db = get_db()

    object_id = _to_object_id(session_id)

    session_doc = await db.sessions.find_one(
        {"_id": object_id}
    )

    # The background task may outlive the request that created it.
    # If the session no longer exists, simply stop processing.
    if session_doc is None:
        return

    storage = StorageManager()

    loop = asyncio.get_running_loop()

    try:

        # --------------------------------------------------------------------
        # Parse student information from XML
        # --------------------------------------------------------------------

        students = InfoParser().parse_students(
            session_doc["info_xml_path"]
        )

        students_by_row_no = {
            student.row_no: student
            for student in students
        }

        # --------------------------------------------------------------------
        # Run CPU-heavy OpenCV work outside the asyncio event loop
        # --------------------------------------------------------------------

        result, attendance_raw = (
            await loop.run_in_executor(
                None,
                _run_cv_pipeline,
                session_id,
                session_doc["image_path"],
                storage,
                loop,
                students,
                options,
            )
        )

        # --------------------------------------------------------------------
        # Convert raw CV results into database attendance records
        # --------------------------------------------------------------------

        attendance_docs = []

        for entry in attendance_raw:

            row_index = entry["row_index"]

            # The post-header-drop row index is zero-based.
            #
            # InfoParser student row_no is one-based.
            #
            # Therefore:
            #
            #     row_index + 1 -> student.row_no
            #
            student = students_by_row_no.get(
                row_index + 1
            )

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

            attendance_docs.append(
                record.model_dump()
            )

        # --------------------------------------------------------------------
        # Replace previous attendance records
        # --------------------------------------------------------------------
        #
        # This ensures re-processing a session does not leave stale
        # attendance records from an earlier run.
        # --------------------------------------------------------------------

        if attendance_docs:

            await db.attendance.delete_many(
                {
                    "session_id": session_id
                }
            )

            await db.attendance.insert_many(
                attendance_docs
            )

        # --------------------------------------------------------------------
        # Mark session as successfully processed
        # --------------------------------------------------------------------

        await db.sessions.update_one(
            {"_id": object_id},
            {
                "$set": {
                    "status": "processed",
                    "steps": [
                        step.model_dump()
                        for step in result.steps
                    ],
                }
            },
        )

        # --------------------------------------------------------------------
        # Final completion event
        # --------------------------------------------------------------------
        #
        # This is intentionally different from the Stage 8 "done" event.
        #
        # The frontend should consider processing completely finished only
        # after:
        #
        #   - CV processing has completed
        #   - attendance records have been written
        #   - session status has been updated
        #
        # --------------------------------------------------------------------

        _broadcast_progress(
            session_id,
            {
                "status": "complete",
                "session_id": session_id,
                "record_count": len(attendance_docs),
            },
        )

    except Exception as exc:  # noqa: BLE001
        # --------------------------------------------------------------------
        # Processing failure
        # --------------------------------------------------------------------

        await db.sessions.update_one(
            {"_id": object_id},
            {
                "$set": {
                    "status": "failed"
                }
            },
        )

        # The frontend ProcessingEvent expects "message".
        _broadcast_progress(
            session_id,
            {
                "status": "failed",
                "message": str(exc),
            },
        )


# ============================================================================
# UPLOAD ATTENDANCE SHEET
# ============================================================================

@router.post("/upload")
async def upload_sheet(
    image: UploadFile = File(...),
    info_xml: UploadFile = File(...),
    subject_code: str = Form(...),
    session_date: str = Form(...),
) -> dict:
    """
    Upload an attendance sheet image and its corresponding student XML file.

    A session document is created first so that all uploaded files and
    processing results can be associated with a single session ID.
    """

    db = get_db()

    storage = StorageManager()

    # ------------------------------------------------------------------------
    # Create initial session document
    # ------------------------------------------------------------------------

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

    session_id = str(
        insert_result.inserted_id
    )

    # ------------------------------------------------------------------------
    # Save uploaded attendance sheet
    # ------------------------------------------------------------------------

    image_path = storage.save_upload(
        session_id,
        image.filename,
        await image.read(),
    )

    # ------------------------------------------------------------------------
    # Save student information XML
    # ------------------------------------------------------------------------

    xml_path = storage.save_upload(
        session_id,
        info_xml.filename,
        await info_xml.read(),
    )

    # ------------------------------------------------------------------------
    # Store file paths in session document
    # ------------------------------------------------------------------------

    await db.sessions.update_one(
        {"_id": insert_result.inserted_id},
        {
            "$set": {
                "image_path": image_path,
                "info_xml_path": xml_path,
            }
        },
    )

    # ------------------------------------------------------------------------
    # Parse student information
    # ------------------------------------------------------------------------

    try:

        students = InfoParser().parse_students(
            xml_path
        )

    except ValueError as exc:

        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc

    # ------------------------------------------------------------------------
    # Upsert students into students collection
    # ------------------------------------------------------------------------

    for student in students:

        await db.students.update_one(
            {"index": student.index},
            {
                "$set": student.model_dump()
            },
            upsert=True,
        )

    # ------------------------------------------------------------------------
    # Return upload information
    # ------------------------------------------------------------------------

    return {
        "session_id": session_id,
        "student_count": len(students),
    }


# ============================================================================
# START SESSION PROCESSING
# ============================================================================

@router.post("/{session_id}/process")
async def process_sheet(
    session_id: str,
    background_tasks: BackgroundTasks,
    options: ProcessOptions | None = None,
) -> dict:
    """
    Start background processing for an uploaded attendance session.

    The request returns immediately with status="processing". The actual
    computer-vision processing happens through FastAPI BackgroundTasks.
    """

    db = get_db()

    object_id = _to_object_id(
        session_id
    )

    # ------------------------------------------------------------------------
    # Verify session exists
    # ------------------------------------------------------------------------

    session_doc = await db.sessions.find_one(
        {"_id": object_id}
    )

    if session_doc is None:

        raise HTTPException(
            status_code=404,
            detail="Session not found",
        )

    # ------------------------------------------------------------------------
    # Resolve processing options
    # ------------------------------------------------------------------------

    resolved_options = (
        options
        or ProcessOptions()
    )

    # ------------------------------------------------------------------------
    # Store processing configuration
    # ------------------------------------------------------------------------
    #
    # The complete options object is stored, including signature-matching
    # fields that are not used by _run_cv_pipeline().
    #
    # signatures.py can later use these session-specific values when
    # constructing SignatureMatcher.
    # ------------------------------------------------------------------------

    await db.sessions.update_one(
        {"_id": object_id},
        {
            "$set": {
                "status": "processing",
                "processing_options": (
                    resolved_options.model_dump()
                ),
            }
        },
    )

    # ------------------------------------------------------------------------
    # Start background processing
    # ------------------------------------------------------------------------

    background_tasks.add_task(
        _process_session,
        session_id,
        resolved_options,
    )

    return {
        "session_id": session_id,
        "status": "processing",
    }


# ============================================================================
# LIST SESSIONS
# ============================================================================

@router.get("")
async def list_sessions(
    subject_code: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    status: str | None = None,
    limit: int = 50,
    skip: int = 0,
) -> list[dict]:
    """
    Return attendance-processing sessions.

    Optional filters:
        subject_code
        date_from
        date_to
        status

    Attendance counts are calculated from the attendance collection and
    attached to each session.
    """

    db = get_db()

    # ------------------------------------------------------------------------
    # Build MongoDB query
    # ------------------------------------------------------------------------

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

    # ------------------------------------------------------------------------
    # Retrieve sessions
    # ------------------------------------------------------------------------

    session_docs = await (
        db.sessions
        .find(query)
        .sort("uploaded_at", -1)
        .skip(skip)
        .limit(limit)
        .to_list(length=None)
    )

    if not session_docs:
        return []

    # ------------------------------------------------------------------------
    # Retrieve attendance records for all sessions
    # ------------------------------------------------------------------------

    session_ids = [
        str(doc["_id"])
        for doc in session_docs
    ]

    attendance_records = await (
        db.attendance
        .find(
            {
                "session_id": {
                    "$in": session_ids
                }
            }
        )
        .to_list(length=None)
    )

    # ------------------------------------------------------------------------
    # Calculate attendance counts
    # ------------------------------------------------------------------------

    counts: dict[str, dict[str, int]] = {}

    for record in attendance_records:

        entry = counts.setdefault(
            record["session_id"],
            {
                "detected": 0,
                "present": 0,
            },
        )

        entry["detected"] += 1

        if record.get("present"):
            entry["present"] += 1

    # ------------------------------------------------------------------------
    # Build API response
    # ------------------------------------------------------------------------

    items = []

    for doc in session_docs:

        session_id = str(
            doc["_id"]
        )

        entry = counts.get(
            session_id,
            {
                "detected": 0,
                "present": 0,
            },
        )

        items.append(
            {
                "id": session_id,
                "subject_code": doc.get(
                    "subject_code"
                ),
                "date": doc.get(
                    "date"
                ),
                "original_filename": doc.get(
                    "original_filename"
                ),
                "status": doc.get(
                    "status"
                ),
                "uploaded_at": doc.get(
                    "uploaded_at"
                ),
                "students_detected": entry[
                    "detected"
                ],
                "present_count": entry[
                    "present"
                ],
                "absent_count": (
                    entry["detected"]
                    - entry["present"]
                ),
            }
        )

    return items


# ============================================================================
# GET PROCESSING STEPS
# ============================================================================

@router.get("/{session_id}/steps")
async def get_steps(
    session_id: str,
) -> list[dict]:
    """
    Return the stored processing steps for a session.
    """

    db = get_db()

    session_doc = await db.sessions.find_one(
        {
            "_id": _to_object_id(
                session_id
            )
        }
    )

    if session_doc is None:

        raise HTTPException(
            status_code=404,
            detail="Session not found",
        )

    return session_doc.get(
        "steps",
        [],
    )


# ============================================================================
# GET ATTENDANCE RESULTS
# ============================================================================

@router.get("/{session_id}/results")
async def get_results(
    session_id: str,
) -> list[dict]:
    """
    Return all attendance records belonging to a session.
    """

    db = get_db()

    records = await (
        db.attendance
        .find(
            {
                "session_id": session_id
            }
        )
        .to_list(length=None)
    )

    # Convert MongoDB ObjectIds into strings so the result can be serialized
    # safely by FastAPI.
    for record in records:

        record["_id"] = str(
            record["_id"]
        )

    return records


# ============================================================================
# GET SESSION EVALUATION
# ============================================================================

@router.get("/{session_id}/evaluation")
async def get_evaluation(
    session_id: str,
) -> dict:
    """
    Evaluate the attendance-processing result for a session.

    Evaluator raises ValueError when the requested session/result does not
    exist, which is translated into HTTP 404 here.
    """

    try:

        return await Evaluator().evaluate(
            session_id
        )

    except ValueError as exc:

        raise HTTPException(
            status_code=404,
            detail=str(exc),
        ) from exc


# ============================================================================
# WEBSOCKET PROCESSING PROGRESS
# ============================================================================

@router.websocket("/ws/{session_id}")
async def sheet_progress_ws(
    websocket: WebSocket,
    session_id: str,
) -> None:
    """
    Stream processing progress events for a specific session.

    The WebSocket receives:

        Stage events:
            {
                "step": "...",
                "order": ...,
                "total": 8,
                "status": "running/done",
                ...
            }

        Completion event:
            {
                "status": "complete",
                ...
            }

        Failure event:
            {
                "status": "failed",
                "message": "..."
            }
    """

    # ------------------------------------------------------------------------
    # Accept WebSocket connection
    # ------------------------------------------------------------------------

    await websocket.accept()

    # Each connection gets its own queue.
    queue: asyncio.Queue = asyncio.Queue()

    # Register this connection for the requested session.
    _progress_subscribers.setdefault(
        session_id,
        [],
    ).append(queue)

    try:

        # --------------------------------------------------------------------
        # Continuously forward queued events to the client
        # --------------------------------------------------------------------

        while True:

            event = await queue.get()

            await websocket.send_json(
                event
            )

    except WebSocketDisconnect:
        # Client closed the WebSocket connection.
        pass

    finally:

        # --------------------------------------------------------------------
        # Remove disconnected client
        # --------------------------------------------------------------------

        subscribers = _progress_subscribers.get(
            session_id,
            [],
        )

        if queue in subscribers:
            subscribers.remove(queue)

        # Remove empty session subscriber lists to avoid keeping unused
        # session IDs in memory.
        if not subscribers:
            _progress_subscribers.pop(
                session_id,
                None,
            )