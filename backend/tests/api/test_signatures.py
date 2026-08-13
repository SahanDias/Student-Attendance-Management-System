import cv2
import numpy as np
from bson import ObjectId


def _write_signature_image(path, seed: int) -> str:
    rng = np.random.default_rng(seed)
    img = np.full((80, 150, 3), 255, dtype=np.uint8)
    for _ in range(4):
        p1 = tuple(int(v) for v in rng.integers(10, 140, size=2))
        p2 = tuple(int(v) for v in rng.integers(10, 70, size=2))
        cv2.line(img, p1, p2, (10, 10, 10), 3)
    cv2.imwrite(str(path), img)
    return str(path)


async def test_list_signature_review_builds_queue_correctly(client, mock_db, tmp_path):
    reference_path = _write_signature_image(tmp_path / "ref.png", seed=1)
    detected_path = _write_signature_image(tmp_path / "det.png", seed=1)

    session_a = ObjectId()
    session_b = ObjectId()
    await mock_db.sessions.insert_many(
        [
            {"_id": session_a, "date": "2026-01-01", "subject_code": "CS101"},
            {"_id": session_b, "date": "2026-01-08", "subject_code": "CS101"},
        ]
    )
    await mock_db.students.insert_one({"index": "S1", "name": "Alice", "row_no": 1, "batch": ""})
    await mock_db.attendance.insert_many(
        [
            {
                "session_id": str(session_a),
                "student_index": "S1",
                "present": True,
                "cell_image": reference_path,
                "confidence": 0.9,
            },
            {
                "session_id": str(session_b),
                "student_index": "S1",
                "present": True,
                "cell_image": detected_path,
                "confidence": 0.9,
            },
        ]
    )

    response = await client.get("/api/signatures")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    item = body[0]
    assert item["student_id"] == "S1"
    assert item["session_id"] == str(session_b)
    assert item["reference_signature"] == reference_path
    assert item["detected_signature"] == detected_path
    assert "similarity_score" in item
    assert "review_required" in item


async def test_list_signature_review_skips_students_with_only_one_present_session(
    client, mock_db, tmp_path
):
    path = _write_signature_image(tmp_path / "only.png", seed=2)
    session_a = ObjectId()
    await mock_db.sessions.insert_one({"_id": session_a, "date": "2026-01-01"})
    await mock_db.attendance.insert_one(
        {
            "session_id": str(session_a),
            "student_index": "S1",
            "present": True,
            "cell_image": path,
            "confidence": 0.9,
        }
    )

    response = await client.get("/api/signatures")

    assert response.status_code == 200
    assert response.json() == []


async def test_verify_student_signatures_returns_per_session_results(client, mock_db, tmp_path):
    reference_path = _write_signature_image(tmp_path / "ref.png", seed=3)
    detected_path = _write_signature_image(tmp_path / "det.png", seed=3)

    session_a = ObjectId()
    session_b = ObjectId()
    await mock_db.sessions.insert_many(
        [
            {"_id": session_a, "date": "2026-01-01"},
            {"_id": session_b, "date": "2026-01-08"},
        ]
    )
    await mock_db.attendance.insert_many(
        [
            {
                "session_id": str(session_a),
                "student_index": "S1",
                "present": True,
                "cell_image": reference_path,
                "confidence": 0.9,
            },
            {
                "session_id": str(session_b),
                "student_index": "S1",
                "present": True,
                "cell_image": detected_path,
                "confidence": 0.9,
            },
        ]
    )

    response = await client.post("/api/signatures/S1/verify")

    assert response.status_code == 200
    body = response.json()
    assert body["student_index"] == "S1"
    assert len(body["sessions"]) == 2
    assert body["sessions"][0]["method"] == "reference"


async def test_verify_student_signatures_unknown_student_returns_404(client, mock_db):
    response = await client.post("/api/signatures/unknown/verify")

    assert response.status_code == 404


async def test_submit_signature_review_upserts_and_appears_in_reviews_list(client, mock_db):
    payload = {"session_id": "session-1", "decision": "confirmed", "note": "looks fine"}

    response = await client.post("/api/signatures/S1/review", json=payload)

    assert response.status_code == 200
    assert response.json()["decision"] == "confirmed"

    reviews_response = await client.get("/api/signatures/reviews")
    reviews = reviews_response.json()
    assert len(reviews) == 1
    assert reviews[0]["student_index"] == "S1"
    assert reviews[0]["decision"] == "confirmed"

    # Re-submitting the same student+session upserts rather than duplicating.
    await client.post(
        "/api/signatures/S1/review",
        json={"session_id": "session-1", "decision": "flagged", "note": None},
    )
    reviews_response = await client.get("/api/signatures/reviews")
    reviews = reviews_response.json()
    assert len(reviews) == 1
    assert reviews[0]["decision"] == "flagged"


async def test_signature_sessions_scoping_filters_correctly(client, mock_db, tmp_path):
    """Three sessions (A -> B -> C) for one student produce two comparison
    pairs, A-vs-B attributed to session B and B-vs-C attributed to session C.
    Each session-scoped endpoint must return only its own pair.
    """
    img_a = _write_signature_image(tmp_path / "a.png", seed=10)
    img_b = _write_signature_image(tmp_path / "b.png", seed=11)
    img_c = _write_signature_image(tmp_path / "c.png", seed=12)

    session_a, session_b, session_c = ObjectId(), ObjectId(), ObjectId()
    await mock_db.sessions.insert_many(
        [
            {"_id": session_a, "date": "2026-01-01", "subject_code": "CS101"},
            {"_id": session_b, "date": "2026-01-08", "subject_code": "CS101"},
            {"_id": session_c, "date": "2026-01-15", "subject_code": "CS101"},
        ]
    )
    await mock_db.attendance.insert_many(
        [
            {"session_id": str(session_a), "student_index": "S1", "present": True, "cell_image": img_a, "confidence": 0.9},
            {"session_id": str(session_b), "student_index": "S1", "present": True, "cell_image": img_b, "confidence": 0.9},
            {"session_id": str(session_c), "student_index": "S1", "present": True, "cell_image": img_c, "confidence": 0.9},
        ]
    )

    sessions_response = await client.get("/api/signatures/sessions")
    assert sessions_response.status_code == 200
    counts = {item["session_id"]: item["item_count"] for item in sessions_response.json()}
    assert counts[str(session_a)] == 0
    assert counts[str(session_b)] == 1
    assert counts[str(session_c)] == 1

    items_b = await client.get(f"/api/signatures/sessions/{session_b}")
    assert items_b.status_code == 200
    body_b = items_b.json()
    assert len(body_b) == 1
    assert body_b[0]["session_id"] == str(session_b)
    assert body_b[0]["reference_signature"] == img_a

    items_c = await client.get(f"/api/signatures/sessions/{session_c}")
    assert items_c.status_code == 200
    body_c = items_c.json()
    assert len(body_c) == 1
    assert body_c[0]["session_id"] == str(session_c)
    assert body_c[0]["reference_signature"] == img_b


async def test_signature_session_items_unknown_session_returns_404(client, mock_db):
    response = await client.get(f"/api/signatures/sessions/{ObjectId()}")

    assert response.status_code == 404
