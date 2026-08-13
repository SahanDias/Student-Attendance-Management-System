"""Usage: python investigate.py <student_index>

Compares every session's detected signature crop against the student's
earliest processed session (treated as the reference) using
SignatureMatcher, and prints a table of similarity scores. Exits with
status 1 if any session is flagged for review.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import cv2  # noqa: E402
from bson import ObjectId  # noqa: E402
from bson.errors import InvalidId  # noqa: E402

from app.core.db import get_sync_db  # noqa: E402
from app.services.signature_matcher import SignatureMatcher  # noqa: E402


def _to_object_ids(session_ids: list[str]) -> list[ObjectId]:
    object_ids = []
    for session_id in session_ids:
        try:
            object_ids.append(ObjectId(session_id))
        except (InvalidId, TypeError):
            continue
    return object_ids


def _session_date(record: dict, sessions: dict) -> str:
    session = sessions.get(record["session_id"])
    return str(session.get("date")) if session else ""


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Investigate a student's signature/attendance history."
    )
    parser.add_argument("student_index", help="Student index to investigate")
    args = parser.parse_args()

    db = get_sync_db()
    records = list(db.attendance.find({"student_index": args.student_index}))

    if not records:
        print(f"No attendance records found for student '{args.student_index}'.")
        return

    sessions = {
        str(doc["_id"]): doc
        for doc in db.sessions.find(
            {"_id": {"$in": _to_object_ids([r["session_id"] for r in records])}}
        )
    }

    ordered = sorted(records, key=lambda r: _session_date(r, sessions))
    reference_record = ordered[0]
    reference_image = cv2.imread(reference_record["cell_image"])
    if reference_image is None:
        print(f"Could not read reference signature crop at {reference_record['cell_image']}")
        sys.exit(1)

    matcher = SignatureMatcher()

    header = f"{'Date':<12}{'Similarity':<12}{'Method':<12}{'Flagged':<8}"
    print(header)
    print("-" * len(header))

    any_flagged = False
    for record in ordered:
        date = _session_date(record, sessions) or "?"

        if record is reference_record:
            print(f"{date:<12}{'1.000':<12}{'reference':<12}{'N':<8}")
            continue

        candidate_image = cv2.imread(record["cell_image"])
        if candidate_image is None:
            print(f"{date:<12}{'?':<12}{'missing image':<12}{'Y':<8}")
            any_flagged = True
            continue

        verdict = matcher.verify(candidate_image, [reference_image])
        flagged = verdict["flagged"]
        any_flagged = any_flagged or flagged
        print(
            f"{date:<12}{verdict['score']:<12.3f}{verdict['method']:<12}"
            f"{'Y' if flagged else 'N':<8}"
        )

    sys.exit(1 if any_flagged else 0)


if __name__ == "__main__":
    main()
