from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from pymongo import ASCENDING, MongoClient
from pymongo.database import Database

from app.config import get_settings

_async_client: AsyncIOMotorClient | None = None
_sync_client: MongoClient | None = None


def get_db() -> AsyncIOMotorDatabase:
    global _async_client
    settings = get_settings()
    if _async_client is None:
        _async_client = AsyncIOMotorClient(settings.MONGODB_URI)
    return _async_client[settings.DB_NAME]


def get_sync_db() -> Database:
    global _sync_client
    settings = get_settings()
    if _sync_client is None:
        _sync_client = MongoClient(settings.MONGODB_URI)
    return _sync_client[settings.DB_NAME]


async def init_indexes() -> None:
    db = get_db()
    await db.attendance.create_index(
        [("session_id", ASCENDING), ("student_index", ASCENDING)], unique=True
    )
    await db.attendance.create_index([("student_index", ASCENDING)])
