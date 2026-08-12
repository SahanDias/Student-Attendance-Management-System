from fastapi import APIRouter, HTTPException

from app.core.db import get_db
from app.models.schemas import Student

router = APIRouter(prefix="/students", tags=["students"])


def _to_student(doc: dict) -> Student:
    return Student(**{key: value for key, value in doc.items() if key != "_id"})


@router.get("")
async def list_students() -> list[Student]:
    db = get_db()
    docs = await db.students.find().to_list(length=None)
    return [_to_student(doc) for doc in docs]


@router.get("/{index}")
async def get_student(index: str) -> Student:
    db = get_db()
    doc = await db.students.find_one({"index": index})
    if doc is None:
        raise HTTPException(status_code=404, detail="Student not found")
    return _to_student(doc)
