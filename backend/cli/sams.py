"""Usage: python sams.py <image> <info.xml>

Runs the attendance pipeline on a single sheet synchronously (no FastAPI/
event loop involved), printing progress as each step completes and a final
present/absent table.
"""

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from datetime import datetime  # noqa: E402

import cv2  # noqa: E402

from app.core.db import get_sync_db  # noqa: E402
from app.core.storage import StorageManager  # noqa: E402
from app.models.schemas import AttendanceRecord, Student  # noqa: E402
from app.services.cell_extractor import CellExtractor  # noqa: E402
from app.services.evaluation import Evaluator  # noqa: E402
from app.services.grid_detector import GridDetector  # noqa: E402
from app.services.info_parser import InfoParser  # noqa: E402
from app.services.pipeline import Pipeline  # noqa: E402
from app.services.presence_detector import PresenceDetector  # noqa: E402
from app.services.steps.binarize import BinarizeStep  # noqa: E402
from app.services.steps.deskew import DeskewStep  # noqa: E402
from app.services.steps.denoise import DenoiseStep  # noqa: E402
from app.services.steps.grayscale import GrayscaleStep  # noqa: E402
from app.services.steps.resize import ResizeStep  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the attendance pipeline on a single sheet.")
    parser.add_argument("image", help="Path to the attendance sheet image")
    parser.add_argument("info_xml", help="Path to the info.xml file listing students")
    args = parser.parse_args()

    db = get_sync_db()
    storage = StorageManager()

    signature_col = -1

    students = InfoParser().parse(args.info_xml)

    now = datetime.utcnow()
    insert_result = db.sessions.insert_one(
        {
            "subject_code": "",
            "date": now.date().isoformat(),
            "original_filename": Path(args.image).name,
            "image_path": args.image,
            "info_xml_path": args.info_xml,
            "status": "processing",
            "steps": [],
            "uploaded_at": now,
        }
    )
    session_object_id = insert_result.inserted_id
    session_id = str(session_object_id)

    def progress_callback(step_name: str, order: int, total: int, path: str) -> None:
        print(f"[{order}/{total}] {step_name} -> {path}")

    steps = [
        ResizeStep(order=1),
        GrayscaleStep(order=2),
        DenoiseStep(order=3),
        DeskewStep(order=4),
        BinarizeStep(order=5),
    ]
    pipeline = Pipeline(steps, storage=storage)
    result = pipeline.run(args.image, session_id, progress_callback=progress_callback)

    # The grid is detected on the deskewed grayscale/binary branch; crops must
    # come from the color frame warped through that same deskew (Pipeline.run
    # stashes it as context["color_aligned"]), not a plain re-read of the
    # resize step's un-rotated output -- otherwise cell boxes and ink don't
    # line up on any sheet that needed deskewing.
    grid_detector = GridDetector(storage=storage)
    rows = grid_detector.detect(result.final_image, session_id=session_id)
    rows = grid_detector.drop_header_rows(rows, expected_row_count=len(students))
    color_aligned = result.context["color_aligned"]

    CellExtractor.validate_alignment(rows, students)

    cell_extractor = CellExtractor(session_id, storage=storage, signature_col=signature_col)
    crops, presence_crops = cell_extractor.extract_signature_cells(color_aligned, rows)

    presence_detector = PresenceDetector()

    attendance_rows: list[tuple[Student, AttendanceRecord]] = []
    for row_index, (student, row) in enumerate(zip(students, rows)):
        if row_index >= len(crops):
            continue
        col_index = signature_col % len(row)
        present, ink_ratio, confidence = presence_detector.is_present(
            presence_crops[row_index], row_index=row_index
        )
        record = AttendanceRecord(
            session_id=session_id,
            student_index=student.index,
            present=present,
            ink_ratio=ink_ratio,
            cell_bbox=list(row[col_index]),
            cell_image=storage.step_path(
                session_id, row_index, f"signature_col{col_index}.png"
            ),
            confidence=confidence,
        )
        attendance_rows.append((student, record))

    if attendance_rows:
        db.attendance.delete_many({"session_id": session_id})
        db.attendance.insert_many([record.model_dump() for _, record in attendance_rows])

    db.sessions.update_one(
        {"_id": session_object_id},
        {
            "$set": {
                "status": "processed",
                "steps": [step.model_dump() for step in result.steps],
            }
        },
    )

    print()
    header = f"{'Index':<12}{'Name':<24}{'Status':<10}{'Ink Ratio':<12}{'Confidence':<10}"
    print(header)
    print("-" * len(header))
    for student, record in attendance_rows:
        status = "PRESENT" if record.present else "ABSENT"
        print(
            f"{student.index:<12}{student.name:<24}{status:<10}"
            f"{record.ink_ratio:<12.3f}{record.confidence:<10.3f}"
        )

    present_total = sum(1 for _, record in attendance_rows if record.present)
    print("-" * len(header))
    print(f"Present: {present_total}/{len(attendance_rows)}")

    evaluator = Evaluator()
    try:
        evaluator.parse_ground_truth(Path(args.image).name)
    except ValueError as exc:
        print()
        print(f"Skipping evaluation: {exc}")
    else:
        evaluation = asyncio.run(evaluator.evaluate(session_id))
        names_by_index = {student.index: student.name for student in students}

        print()
        eval_header = f"{'Index':<12}{'Name':<24}{'Expected':<10}{'Detected':<10}"
        print(eval_header)
        print("-" * len(eval_header))
        for entry in evaluation["per_student"]:
            name = names_by_index.get(entry["student_index"], "?")
            expected = "PRESENT" if entry["expected"] else "ABSENT"
            detected = "PRESENT" if entry["detected"] else "ABSENT"
            print(f"{entry['student_index']:<12}{name:<24}{expected:<10}{detected:<10}")
        print("-" * len(eval_header))
        print(
            f"Accuracy: {evaluation['accuracy']:.3f}  "
            f"Precision: {evaluation['precision']:.3f}  "
            f"Recall: {evaluation['recall']:.3f}  "
            f"F1: {evaluation['f1']:.3f}"
        )


if __name__ == "__main__":
    main()
