async def test_list_students_returns_all(client, mock_db):
    await mock_db.students.insert_many(
        [
            {"index": "1", "name": "Alice", "batch": "2024", "subjects": [], "row_no": 1},
            {"index": "2", "name": "Bob", "batch": "2024", "subjects": [], "row_no": 2},
        ]
    )

    response = await client.get("/api/students")

    assert response.status_code == 200
    body = response.json()
    assert {s["index"] for s in body} == {"1", "2"}


async def test_list_students_empty_collection_returns_empty_list(client, mock_db):
    response = await client.get("/api/students")

    assert response.status_code == 200
    assert response.json() == []


async def test_get_student_returns_matching_student(client, mock_db):
    await mock_db.students.insert_one(
        {"index": "42", "name": "Carol", "batch": "2024", "subjects": [], "row_no": 1}
    )

    response = await client.get("/api/students/42")

    assert response.status_code == 200
    assert response.json()["index"] == "42"
    assert response.json()["name"] == "Carol"


async def test_get_student_unknown_index_returns_404(client, mock_db):
    response = await client.get("/api/students/does-not-exist")

    assert response.status_code == 404
