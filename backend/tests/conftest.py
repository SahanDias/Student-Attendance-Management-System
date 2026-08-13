from pathlib import Path

import cv2
import numpy as np
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from mongomock_motor import AsyncMongoMockClient

from app.config import Settings


@pytest_asyncio.fixture
async def mock_db():
    """A fresh in-memory mongomock-motor database for each test."""
    mongo_client = AsyncMongoMockClient()
    yield mongo_client["test_db"]


@pytest.fixture
def storage_root(tmp_path, monkeypatch):
    """Redirects StorageManager's default root to a temp directory, so no
    test ever writes into the real backend/storage/.
    """
    fake_settings = Settings(
        MONGODB_URI="mongodb://localhost/unused",
        DB_NAME="unused",
        STORAGE_ROOT=str(tmp_path),
        API_PREFIX="/api",
    )
    monkeypatch.setattr("app.core.storage.get_settings", lambda: fake_settings)
    return tmp_path


@pytest_asyncio.fixture
async def client(mock_db, storage_root):
    """An httpx AsyncClient wrapping the FastAPI app over ASGITransport, with
    get_db overridden to the mock_db fixture so no test hits real MongoDB.
    """
    from app.core.db import get_db
    from app.main import app

    app.dependency_overrides[get_db] = lambda: mock_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest.fixture
def synthetic_sheet():
    """Generates a synthetic attendance-sheet image in memory: a white canvas
    with black horizontal/vertical rule lines forming an N-row x M-col grid,
    plus a few pen-like scribbles in one column so presence detection has
    something to find. Returned as a BGR numpy array -- never written to or
    read from disk.
    """

    def _make(
        rows: int = 4,
        cols: int = 4,
        cell_width: int = 150,
        cell_height: int = 80,
        margin: int = 40,
        signed_rows: tuple[int, ...] = (0, 2),
        signature_col: int = -1,
    ) -> np.ndarray:
        width = margin * 2 + cell_width * cols
        height = margin * 2 + cell_height * rows
        canvas = np.full((height, width, 3), 255, dtype=np.uint8)

        xs = [margin + c * cell_width for c in range(cols + 1)]
        ys = [margin + r * cell_height for r in range(rows + 1)]

        for y in ys:
            cv2.line(canvas, (xs[0], y), (xs[-1], y), (0, 0, 0), 2)
        for x in xs:
            cv2.line(canvas, (x, ys[0]), (x, ys[-1]), (0, 0, 0), 2)

        sig_col_index = signature_col % cols
        for row in signed_rows:
            if row >= rows:
                continue
            x1, x2 = xs[sig_col_index] + 10, xs[sig_col_index + 1] - 10
            y1, y2 = ys[row] + 15, ys[row + 1] - 15
            cv2.line(canvas, (x1, y1), (x2, y2), (10, 10, 10), 3)
            cv2.line(canvas, (x1, y2), (x2, y1), (10, 10, 10), 3)

        return canvas

    return _make


@pytest.fixture
def sample_info_xml(tmp_path):
    """Writes a valid roster info.xml to tmp_path and returns its path."""

    def _make(students: list[dict] | None = None) -> Path:
        students = students or [
            {"student_id": "10000409", "title": "Ms", "name": "M S Dilshanika Perera"},
            {"student_id": "10009301", "title": "Mr", "name": "K A Perera"},
        ]
        entries = "\n".join(
            f"""  <student>
    <student_id>{s['student_id']}</student_id>
    <title>{s.get('title', '')}</title>
    <name>{s['name']}</name>
  </student>"""
            for s in students
        )
        xml = f"<students>\n{entries}\n</students>\n"
        path = tmp_path / "info.xml"
        path.write_text(xml, encoding="utf-8")
        return path

    return _make
