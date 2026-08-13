import cv2
import numpy as np
from bson import ObjectId

from app.services.pipeline import PipelineResult


def _image_bytes(synthetic_sheet) -> bytes:
    ok, buf = cv2.imencode(".png", synthetic_sheet())
    assert ok
    return buf.tobytes()


async def test_upload_sheet_valid_files_returns_200_and_upserts_students(
    client, mock_db, synthetic_sheet
):
    files = {
        "image": ("sheet.png", _image_bytes(synthetic_sheet), "image/png"),
        "info_xml": (
            "info.xml",
            b"<students>"
            b"<student><student_id>1</student_id><name>Alice</name></student>"
            b"<student><student_id>2</student_id><name>Bob</name></student>"
            b"</students>",
            "application/xml",
        ),
    }
    data = {"subject_code": "CS101", "session_date": "2026-01-01"}

    response = await client.post("/api/sheets/upload", files=files, data=data)

    assert response.status_code == 200
    body = response.json()
    assert body["student_count"] == 2
    assert "session_id" in body

    students = await mock_db.students.find().to_list(length=None)
    assert {s["index"] for s in students} == {"1", "2"}

    session_doc = await mock_db.sessions.find_one({"_id": ObjectId(body["session_id"])})
    assert session_doc["status"] == "uploaded"
    assert session_doc["subject_code"] == "CS101"


async def test_upload_sheet_malformed_roster_returns_400(client, mock_db, synthetic_sheet):
    files = {
        "image": ("sheet.png", _image_bytes(synthetic_sheet), "image/png"),
        "info_xml": ("info.xml", b"<students><student><name>Broken</students>", "application/xml"),
    }
    data = {"subject_code": "CS101", "session_date": "2026-01-01"}

    response = await client.post("/api/sheets/upload", files=files, data=data)

    assert response.status_code == 400


async def test_upload_sheet_missing_required_file_returns_422(client, mock_db):
    data = {"subject_code": "CS101", "session_date": "2026-01-01"}

    response = await client.post("/api/sheets/upload", data=data)

    assert response.status_code == 422


async def test_process_sheet_unknown_session_returns_404(client, mock_db):
    response = await client.post(f"/api/sheets/{ObjectId()}/process")

    assert response.status_code == 404


async def test_process_sheet_invokes_pipeline_and_marks_processed(
    client, mock_db, monkeypatch, tmp_path
):
    """POST /process must hand off to the CV pipeline and persist its
    results -- the real CV code is monkeypatched out so this only exercises
    the route/background-task wiring, not OpenCV itself.
    """
    session_id = ObjectId()
    xml_path = tmp_path / "info.xml"
    xml_path.write_text(
        "<students><student><student_id>1</student_id><name>Alice</name></student></students>",
        encoding="utf-8",
    )
    await mock_db.sessions.insert_one(
        {
            "_id": session_id,
            "subject_code": "CS101",
            "date": "2026-01-01",
            "original_filename": "sheet.png",
            "image_path": str(tmp_path / "sheet.png"),
            "info_xml_path": str(xml_path),
            "status": "uploaded",
            "steps": [],
        }
    )

    calls: list[str] = []

    def fake_run_cv_pipeline(session_id, image_path, storage, loop, students, options):
        calls.append(session_id)
        result = PipelineResult(
            final_image=np.zeros((10, 10), dtype=np.uint8),
            context={"color_aligned": np.zeros((10, 10, 3), dtype=np.uint8)},
            steps=[],
        )
        attendance_raw = [
            {
                "row_index": 0,
                "present": True,
                "ink_ratio": 0.1,
                "confidence": 0.8,
                "cell_bbox": [0, 0, 10, 10],
                "cell_image": str(tmp_path / "crop.png"),
            }
        ]
        return result, attendance_raw

    monkeypatch.setattr(
        "app.api.routes.sheets._run_cv_pipeline", fake_run_cv_pipeline
    )

    response = await client.post(f"/api/sheets/{session_id}/process")

    assert response.status_code == 200
    assert response.json()["status"] == "processing"
    assert calls == [str(session_id)]

    session_doc = await mock_db.sessions.find_one({"_id": session_id})
    assert session_doc["status"] == "processed"

    records = await mock_db.attendance.find({"session_id": str(session_id)}).to_list(length=None)
    assert len(records) == 1
    assert records[0]["student_index"] == "1"
    assert records[0]["present"] is True


async def test_list_sessions_empty_collection_returns_empty_list(client, mock_db):
    response = await client.get("/api/sheets")

    assert response.status_code == 200
    assert response.json() == []


async def test_get_steps_unknown_session_returns_404(client, mock_db):
    response = await client.get(f"/api/sheets/{ObjectId()}/steps")

    assert response.status_code == 404


async def test_get_results_empty_returns_empty_list(client, mock_db):
    response = await client.get(f"/api/sheets/{ObjectId()}/results")

    assert response.status_code == 200
    assert response.json() == []


async def test_get_results_resolves_student_name_from_roster(client, mock_db):
    """GET /results must join each attendance record's student_index against
    the students roster to attach a name -- regression test for the "Name"
    column always rendering "—" because attendance records only ever store
    student_index, never a name of their own.
    """
    session_id = "session-1"
    await mock_db.students.insert_one(
        {"index": "10000409", "name": "M S Dilshanika Perera", "batch": "", "row_no": 1}
    )
    await mock_db.attendance.insert_one(
        {
            "session_id": session_id,
            "student_index": "10000409",
            "present": True,
            "ink_ratio": 0.219,
            "cell_bbox": [0, 0, 10, 10],
            "cell_image": "crop.png",
            "confidence": 0.9,
        }
    )

    response = await client.get(f"/api/sheets/{session_id}/results")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["student_index"] == "10000409"
    assert body[0]["name"] == "M S Dilshanika Perera"
    # Detection fields must be untouched by the join.
    assert body[0]["present"] is True
    assert body[0]["ink_ratio"] == 0.219
    assert body[0]["cell_image"] == "crop.png"


async def test_get_results_unknown_student_returns_null_name(client, mock_db):
    """A detected index with no matching roster entry must resolve to a
    missing/null name (frontend falls back to "—"), not raise or invent one.
    """
    session_id = "session-2"
    await mock_db.attendance.insert_one(
        {
            "session_id": session_id,
            "student_index": "99999999",
            "present": False,
            "ink_ratio": 0.01,
            "cell_bbox": [0, 0, 10, 10],
            "cell_image": "crop.png",
            "confidence": 0.5,
        }
    )

    response = await client.get(f"/api/sheets/{session_id}/results")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["name"] is None
