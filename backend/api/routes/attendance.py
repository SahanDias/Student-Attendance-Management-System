from bson import ObjectId
from bson.errors import InvalidId
from fastapi import APIRouter, Depends, HTTPException
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.db import get_db

router = APIRouter(prefix="/attendance", tags=["attendance"])


@router.get("/trend")
async def get_attendance_trend(db: AsyncIOMotorDatabase = Depends(get_db)) -> list[dict]:
    # Declared before /{student_index} so "trend" isn't swallowed by that
    # dynamic path.
    session_docs = await (
        db.sessions.find({"status": "processed"}).sort("date", 1).to_list(length=None)
    )
    if not session_docs:
        return []

    session_ids = [str(doc["_id"]) for doc in session_docs]
    records = await db.attendance.find({"session_id": {"$in": session_ids}}).to_list(length=None)

    counts: dict[str, dict[str, int]] = {}
    for record in records:
        entry = counts.setdefault(record["session_id"], {"detected": 0, "present": 0})
        entry["detected"] += 1
        if record.get("present"):
            entry["present"] += 1

    trend = []
    for doc in session_docs:
        entry = counts.get(str(doc["_id"]))
        if not entry or not entry["detected"]:
            continue
        trend.append(
            {
                "date": doc.get("date"),
                "subject_code": doc.get("subject_code"),
                "rate": round((entry["present"] / entry["detected"]) * 100, 1),
            }
        )

    return trend


@router.get("/summary")
async def get_all_attendance_summaries(db: AsyncIOMotorDatabase = Depends(get_db)) -> list[dict]:
    # Declared before /{student_index} so "summary" isn't swallowed by that
    # dynamic path -- same fix as /trend.
    processed_sessions = await db.sessions.find({"status": "processed"}).to_list(length=None)
    session_ids = [str(doc["_id"]) for doc in processed_sessions]
    sessions_total = len(session_ids)

    students = await db.students.find().to_list(length=None)

    present_counts: dict[str, int] = {}
    if session_ids:
        records = await db.attendance.find(
            {"session_id": {"$in": session_ids}, "present": True}
        ).to_list(length=None)
        for record in records:
            present_counts[record["student_index"]] = (
                present_counts.get(record["student_index"], 0) + 1
            )

    summary = []
    for student in students:
        attended = present_counts.get(student["index"], 0)
        percentage = round((attended / sessions_total) * 100, 2) if sessions_total else 0.0
        summary.append(
            {
                "index": student["index"],
                "name": student.get("name", ""),
                "sessions_attended": attended,
                "sessions_total": sessions_total,
                "percentage": percentage,
            }
        )

    return summary


@router.get("/{student_index}")
async def get_attendance(
    student_index: str, db: AsyncIOMotorDatabase = Depends(get_db)
) -> list[dict]:
    records = await db.attendance.find({"student_index": student_index}).to_list(length=None)
    for record in records:
        record["_id"] = str(record["_id"])
    return records


@router.get("/{student_index}/summary")
async def get_attendance_summary(
    student_index: str, db: AsyncIOMotorDatabase = Depends(get_db)
) -> dict:
    records = await db.attendance.find({"student_index": student_index}).to_list(length=None)

    if not records:
        raise HTTPException(
            status_code=404, detail="No attendance records found for this student"
        )

    session_object_ids = []
    for record in records:
        try:
            session_object_ids.append(ObjectId(record["session_id"]))
        except (InvalidId, TypeError):
            continue

    sessions = await db.sessions.find({"_id": {"$in": session_object_ids}}).to_list(length=None)
    session_dates = {str(session["_id"]): session.get("date") for session in sessions}

    present_count = sum(1 for record in records if record.get("present"))
    total_count = len(records)
    absent_count = total_count - present_count
    percentage = round((present_count / total_count) * 100, 2) if total_count else 0.0

    series = sorted(
        (
            {
                "date": session_dates.get(record["session_id"]),
                "present": bool(record.get("present")),
            }
            for record in records
        ),
        key=lambda entry: entry["date"] or "",
    )

    return {
        "student_index": student_index,
        "present_count": present_count,
        "absent_count": absent_count,
        "total_count": total_count,
        "percentage": percentage,
        "series": series,
    }
