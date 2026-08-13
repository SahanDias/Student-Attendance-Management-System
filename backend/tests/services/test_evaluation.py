import json

import pytest
from bson import ObjectId

from app.services.evaluation import Evaluator


def test_score_all_correct_returns_perfect_metrics():
    ground_truth = {"10000409": True, "10009301": False}
    detected = {"10000409": True, "10009301": False}

    result = Evaluator.score(ground_truth, detected)

    assert result["true_positives"] == 1
    assert result["true_negatives"] == 1
    assert result["false_positives"] == 0
    assert result["false_negatives"] == 0
    assert result["accuracy"] == 1.0
    assert result["precision"] == 1.0
    assert result["recall"] == 1.0
    assert result["f1"] == 1.0


def test_score_all_wrong_returns_zeroed_metrics():
    ground_truth = {"10000409": True, "10009301": False}
    detected = {"10000409": False, "10009301": True}

    result = Evaluator.score(ground_truth, detected)

    assert result["true_positives"] == 0
    assert result["true_negatives"] == 0
    assert result["false_positives"] == 1
    assert result["false_negatives"] == 1
    assert result["accuracy"] == 0.0
    assert result["precision"] == 0.0
    assert result["recall"] == 0.0
    assert result["f1"] == 0.0


def test_score_zero_positives_does_not_divide_by_zero():
    """No student is expected present and none is detected present -- both
    precision (tp+fp==0) and recall (tp+fn==0) guards must return 0.0
    instead of raising ZeroDivisionError.
    """
    ground_truth = {"10000409": False, "10009301": False}
    detected: dict[str, bool] = {}

    result = Evaluator.score(ground_truth, detected)

    assert result["true_positives"] == 0
    assert result["false_positives"] == 0
    assert result["false_negatives"] == 0
    assert result["precision"] == 0.0
    assert result["recall"] == 0.0
    assert result["f1"] == 0.0
    assert result["accuracy"] == 1.0


def test_score_mismatched_student_counts_ignores_extra_detected():
    """A student missing from `detected` counts as not-detected; a student in
    `detected` but absent from ground truth is ignored entirely, since
    scoring only ever covers what ground truth itself lists.
    """
    ground_truth = {"10000409": True}
    detected = {"10000409": True, "99999999": True}

    result = Evaluator.score(ground_truth, detected)

    assert len(result["per_student"]) == 1
    assert result["per_student"][0]["student_index"] == "10000409"
    assert result["true_positives"] == 1
    assert result["accuracy"] == 1.0


def test_score_missing_detected_entry_counts_as_absent():
    ground_truth = {"10000409": True}
    detected: dict[str, bool] = {}

    result = Evaluator.score(ground_truth, detected)

    assert result["per_student"] == [
        {"student_index": "10000409", "expected": True, "detected": False}
    ]
    assert result["false_negatives"] == 1


def test_parse_ground_truth_valid_file_returns_mapping(tmp_path):
    gt_path = tmp_path / "ground_truth.json"
    gt_path.write_text(json.dumps({"1.jpeg": {"10000409": True, "10009301": False}}))

    ground_truth = Evaluator(ground_truth_path=gt_path).parse_ground_truth("1.jpeg")

    assert ground_truth == {"10000409": True, "10009301": False}


def test_parse_ground_truth_missing_file_raises_value_error(tmp_path):
    gt_path = tmp_path / "does_not_exist.json"

    with pytest.raises(ValueError, match="No ground truth file"):
        Evaluator(ground_truth_path=gt_path).parse_ground_truth("1.jpeg")


def test_parse_ground_truth_malformed_json_raises_value_error(tmp_path):
    gt_path = tmp_path / "ground_truth.json"
    gt_path.write_text("{not valid json")

    with pytest.raises(ValueError, match="Malformed ground truth file"):
        Evaluator(ground_truth_path=gt_path).parse_ground_truth("1.jpeg")


def test_parse_ground_truth_unknown_image_raises_value_error(tmp_path):
    gt_path = tmp_path / "ground_truth.json"
    gt_path.write_text(json.dumps({"1.jpeg": {"10000409": True}}))

    with pytest.raises(ValueError, match="No ground truth available"):
        Evaluator(ground_truth_path=gt_path).parse_ground_truth("2.jpeg")


async def test_evaluate_valid_session_scores_against_ground_truth(mock_db, tmp_path, monkeypatch):
    monkeypatch.setattr("app.services.evaluation.get_db", lambda: mock_db)

    gt_path = tmp_path / "ground_truth.json"
    gt_path.write_text(json.dumps({"1.jpeg": {"10000409": True, "10009301": False}}))

    session_id = ObjectId()
    await mock_db.sessions.insert_one({"_id": session_id, "original_filename": "1.jpeg"})
    await mock_db.attendance.insert_one(
        {"session_id": str(session_id), "student_index": "10000409", "present": True}
    )

    result = await Evaluator(ground_truth_path=gt_path).evaluate(str(session_id))

    assert result["true_positives"] == 1
    assert result["true_negatives"] == 1
    assert result["accuracy"] == 1.0


async def test_evaluate_invalid_session_id_raises_value_error(mock_db, monkeypatch):
    monkeypatch.setattr("app.services.evaluation.get_db", lambda: mock_db)

    with pytest.raises(ValueError, match="Invalid session id"):
        await Evaluator().evaluate("not-an-object-id")


async def test_evaluate_unknown_session_raises_value_error(mock_db, monkeypatch):
    monkeypatch.setattr("app.services.evaluation.get_db", lambda: mock_db)

    with pytest.raises(ValueError, match="not found"):
        await Evaluator().evaluate(str(ObjectId()))
