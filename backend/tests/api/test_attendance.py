from bson import ObjectId


async def test_trend_empty_collections_returns_empty_list(client, mock_db):
    response = await client.get("/api/attendance/trend")

    assert response.status_code == 200
    assert response.json() == []


async def test_summary_empty_collections_returns_empty_list(client, mock_db):
    response = await client.get("/api/attendance/summary")

    assert response.status_code == 200
    assert response.json() == []


async def test_trend_computes_rate_per_processed_session(client, mock_db):
    session_id = ObjectId()
    await mock_db.sessions.insert_one(
        {"_id": session_id, "status": "processed", "date": "2026-01-01", "subject_code": "CS101"}
    )
    await mock_db.attendance.insert_many(
        [
            {"session_id": str(session_id), "student_index": "1", "present": True},
            {"session_id": str(session_id), "student_index": "2", "present": False},
        ]
    )

    response = await client.get("/api/attendance/trend")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["subject_code"] == "CS101"
    assert body[0]["rate"] == 50.0


async def test_summary_computes_percentage_per_student(client, mock_db):
    session_id = ObjectId()
    await mock_db.sessions.insert_one({"_id": session_id, "status": "processed", "date": "2026-01-01"})
    await mock_db.students.insert_one({"index": "1", "name": "Alice", "row_no": 1, "batch": ""})
    await mock_db.attendance.insert_one(
        {"session_id": str(session_id), "student_index": "1", "present": True}
    )

    response = await client.get("/api/attendance/summary")

    assert response.status_code == 200
    body = response.json()
    assert body == [
        {
            "index": "1",
            "name": "Alice",
            "sessions_attended": 1,
            "sessions_total": 1,
            "percentage": 100.0,
        }
    ]


async def test_get_attendance_returns_records_for_student(client, mock_db):
    await mock_db.attendance.insert_many(
        [
            {"session_id": "s1", "student_index": "1", "present": True},
            {"session_id": "s2", "student_index": "1", "present": False},
            {"session_id": "s1", "student_index": "2", "present": True},
        ]
    )

    response = await client.get("/api/attendance/1")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 2
    assert all(record["student_index"] == "1" for record in body)


async def test_get_attendance_summary_unknown_student_returns_404(client, mock_db):
    response = await client.get("/api/attendance/does-not-exist/summary")

    assert response.status_code == 404


async def test_get_attendance_summary_computes_present_absent_counts(client, mock_db):
    session_id = ObjectId()
    await mock_db.sessions.insert_one({"_id": session_id, "date": "2026-01-01", "status": "processed"})
    await mock_db.attendance.insert_many(
        [
            {"session_id": str(session_id), "student_index": "1", "present": True},
        ]
    )

    response = await client.get("/api/attendance/1/summary")

    assert response.status_code == 200
    body = response.json()
    assert body["present_count"] == 1
    assert body["absent_count"] == 0
    assert body["total_count"] == 1
    assert body["percentage"] == 100.0
