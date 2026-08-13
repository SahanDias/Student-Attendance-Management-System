"""Usage: python infovis.py <student_index>

Queries attendance for one student and renders a bar chart (per-date
present/absent) plus a pie chart (overall present/absent split).
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import matplotlib.pyplot as plt  # noqa: E402
from bson import ObjectId  # noqa: E402
from bson.errors import InvalidId  # noqa: E402

from app.core.db import get_sync_db  # noqa: E402


def _to_object_ids(session_ids: list[str]) -> list[ObjectId]:
    object_ids = []
    for session_id in session_ids:
        try:
            object_ids.append(ObjectId(session_id))
        except (InvalidId, TypeError):
            continue
    return object_ids


def main() -> None:
    parser = argparse.ArgumentParser(description="Visualize a student's attendance history.")
    parser.add_argument("student_index", help="Student index to visualize")
    args = parser.parse_args()

    db = get_sync_db()
    records = list(db.attendance.find({"student_index": args.student_index}))

    if not records:
        print(f"No attendance records found for student '{args.student_index}'.")
        return

    session_ids = [record["session_id"] for record in records]
    sessions = {
        str(doc["_id"]): doc
        for doc in db.sessions.find({"_id": {"$in": _to_object_ids(session_ids)}})
    }

    present_count = sum(1 for record in records if record.get("present"))
    total_count = len(records)
    absent_count = total_count - present_count

    dated_records = sorted(
        (
            (
                sessions.get(record["session_id"], {}).get("date", "?"),
                bool(record.get("present")),
            )
            for record in records
        ),
        key=lambda item: item[0],
    )
    dates = [item[0] for item in dated_records]
    presence = [1 if item[1] else 0 for item in dated_records]
    colors = ["#2e7d32" if p else "#c62828" for p in presence]

    fig, (bar_ax, pie_ax) = plt.subplots(1, 2, figsize=(12, 5))

    bar_ax.bar(dates, presence, color=colors)
    bar_ax.set_ylim(0, 1.2)
    bar_ax.set_yticks([0, 1])
    bar_ax.set_yticklabels(["Absent", "Present"])
    bar_ax.set_title(f"Attendance timeline: {args.student_index}")
    bar_ax.set_xlabel("Date")
    bar_ax.tick_params(axis="x", rotation=45)

    pie_ax.pie(
        [present_count, absent_count],
        labels=["Present", "Absent"],
        colors=["#2e7d32", "#c62828"],
        autopct="%1.1f%%",
        startangle=90,
    )
    pie_ax.set_title("Overall attendance")

    fig.tight_layout()
    plt.show()


if __name__ == "__main__":
    main()
