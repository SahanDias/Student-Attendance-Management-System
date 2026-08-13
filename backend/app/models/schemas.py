from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel


class Subject(BaseModel):
    code: str
    title: str


class Student(BaseModel):
    index: str
    name: str
    batch: str
    subjects: list[str] = []
    row_no: int
    title: str | None = None


class SheetMeta(BaseModel):
    id: str
    source_image: str
    module: str
    hall: str
    date: date
    time_from: str
    time_to: str
    lecturer_name: str
    lecturer_signed: bool
    notes: str | None = None
    sheet_number: str | None = None


class StepImage(BaseModel):
    name: str
    order: int
    path: str


class Session(BaseModel):
    subject_code: str
    date: date
    original_filename: str
    image_path: str
    info_xml_path: str
    status: Literal["uploaded", "processing", "processed", "failed"] = "uploaded"
    steps: list[StepImage] = []
    uploaded_at: datetime


class AttendanceRecord(BaseModel):
    session_id: str
    student_index: str
    present: bool
    ink_ratio: float
    cell_bbox: list[int]
    cell_image: str
    confidence: float


class SignatureRecord(BaseModel):
    student_index: str
    session_id: str
    image_path: str
    match_score: float
    flagged: bool
