from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.routes import attendance, sheets, signatures, students
from app.config import get_settings
from app.core.db import init_indexes

settings = get_settings()

app = FastAPI(title="Student Attendance System")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(sheets.router, prefix=settings.API_PREFIX)
app.include_router(attendance.router, prefix=settings.API_PREFIX)
app.include_router(students.router, prefix=settings.API_PREFIX)
app.include_router(signatures.router, prefix=settings.API_PREFIX)

app.mount("/static", StaticFiles(directory=settings.STORAGE_ROOT), name="static")


@app.on_event("startup")
async def on_startup() -> None:
    await init_indexes()


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}
