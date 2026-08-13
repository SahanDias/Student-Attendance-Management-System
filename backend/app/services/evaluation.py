import json
from pathlib import Path

from bson import ObjectId
from bson.errors import InvalidId

from app.core.db import get_db

# backend/app/services/evaluation.py -> backend/tests/ground_truth.json
GROUND_TRUTH_PATH = Path(__file__).resolve().parents[2] / "tests" / "ground_truth.json"


class Evaluator:
    """Scores detected attendance against manually-curated ground truth for
    a session's uploaded image.

    Ground truth is read here for MEASUREMENT ONLY, after the fact: this
    class never runs during detection and PresenceDetector never sees it.
    info.xml carries no ground truth in the current schema (see InfoParser),
    so this comes from a separate hand-maintained file at
    tests/ground_truth.json, keyed by image filename:
        { "1.jpeg": { "10000409": true, "10009301": false, ... }, ... }
    """

    def __init__(self, ground_truth_path: Path | None = None) -> None:
        self.ground_truth_path = ground_truth_path or GROUND_TRUTH_PATH

    def parse_ground_truth(self, image_filename: str) -> dict[str, bool]:
        if not self.ground_truth_path.exists():
            raise ValueError(
                f"No ground truth file at {self.ground_truth_path}: create it "
                "manually to enable evaluation"
            )

        try:
            with open(self.ground_truth_path, encoding="utf-8") as f:
                all_ground_truth = json.load(f)
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(
                f"Malformed ground truth file {self.ground_truth_path}: {exc}"
            ) from exc

        ground_truth = all_ground_truth.get(image_filename)
        if not ground_truth:
            raise ValueError(
                f"No ground truth available for image '{image_filename}' in "
                f"{self.ground_truth_path}"
            )
        return ground_truth

    async def evaluate(self, session_id: str) -> dict:
        db = get_db()

        try:
            object_id = ObjectId(session_id)
        except (InvalidId, TypeError) as exc:
            raise ValueError(f"Invalid session id: {session_id}") from exc

        session_doc = await db.sessions.find_one({"_id": object_id})
        if session_doc is None:
            raise ValueError(f"Session {session_id} not found")

        ground_truth = self.parse_ground_truth(session_doc["original_filename"])

        records = await db.attendance.find({"session_id": session_id}).to_list(length=None)
        detected = {record["student_index"]: bool(record.get("present")) for record in records}

        per_student = []
        true_positives = 0
        true_negatives = 0
        false_positives = 0
        false_negatives = 0

        for student_no, expected in ground_truth.items():
            detected_present = detected.get(student_no, False)
            per_student.append(
                {
                    "student_index": student_no,
                    "expected": expected,
                    "detected": detected_present,
                }
            )
            if expected and detected_present:
                true_positives += 1
            elif not expected and not detected_present:
                true_negatives += 1
            elif not expected and detected_present:
                false_positives += 1
            else:  # expected and not detected_present
                false_negatives += 1

        total = true_positives + true_negatives + false_positives + false_negatives
        accuracy = (true_positives + true_negatives) / total if total else 0.0
        precision = (
            true_positives / (true_positives + false_positives)
            if (true_positives + false_positives)
            else 0.0
        )
        recall = (
            true_positives / (true_positives + false_negatives)
            if (true_positives + false_negatives)
            else 0.0
        )
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0

        return {
            "per_student": per_student,
            "true_positives": true_positives,
            "true_negatives": true_negatives,
            "false_positives": false_positives,
            "false_negatives": false_negatives,
            "accuracy": accuracy,
            "precision": precision,
            "recall": recall,
            "f1": f1,
        }
