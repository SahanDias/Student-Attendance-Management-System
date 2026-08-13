"""Signature review queue and per-student verification.

`GET /signatures` builds a review queue from every attendance record on
file: each student's earliest processed session is treated as their
reference signature, and every later session's cell crop is compared
against it with SignatureMatcher (ORB keypoint matching, falling back to a
coarse structural comparison -- see app/services/signature_matcher.py).
This is a lightweight heuristic meant to flag candidates for a human to
look at, not forensic signature verification.

`confidence_score` -- the presence-detection ink-ratio confidence from
PresenceDetector -- is kept in the response alongside the new
`similarity_score`/`match_method` fields so existing clients reading the
old field don't break.

`GET /signatures/sessions` and `GET /signatures/sessions/{session_id}` back
the session-scoped review UI: the first lists every processed session with a
count of comparable items, the second returns those items for one session,
each student's crop compared against their own crop from the previous
session they were present for (not the all-time earliest reference `GET
/signatures` uses). Both skip absent records and a student's first present
session, since there's nothing to compare it against.

`POST /signatures/{student_index}/verify` re-runs that comparison for one
student across every session they have a record for.

`POST /signatures/{student_index}/review` records an operator's decision
(confirmed/flagged) for one student+session, upserted into the
`signature_reviews` collection so re-submitting a decision for the same
pair overwrites it rather than accumulating duplicate history.
`GET /signatures/reviews` returns every stored decision so the review
queue can show what's already been resolved across page reloads.

All OpenCV work (image decoding, ORB, structural comparison) is blocking
and CPU-bound, so it always runs through run_in_executor rather than
inline in these async route handlers.
"""

import asyncio
import logging
from collections import defaultdict
from datetime import datetime
from typing import Literal

import cv2
import numpy as np
from bson import ObjectId
from bson.errors import InvalidId
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.core.db import get_db
from app.services.signature_matcher import SignatureMatcher

router = APIRouter(prefix="/signatures", tags=["signatures"])

logger = logging.getLogger(__name__)


class SignatureReviewDecision(BaseModel):
    session_id: str
    decision: Literal["confirmed", "flagged"]
    note: str | None = None


_MISSING_IMAGE_VERDICT = {
    "score": 0.0,
    "mean_score": 0.0,
    "method": "none",
    "reference_count": 0,
    "flagged": True,
}


def _confidence_score(record: dict) -> float:
    """Presence-detection confidence, kept for clients still reading the
    old `confidence_score` field instead of `similarity_score`.
    """
    return float(record.get("confidence", 0.0))


def _load_cell_image(path: str) -> np.ndarray | None:
    return cv2.imread(path)


def _session_date(record: dict, session_by_id: dict) -> str:
    session = session_by_id.get(record["session_id"])
    return str(session.get("date")) if session else ""


async def _object_ids_for_sessions(records: list[dict]) -> list[ObjectId]:
    session_ids = {record["session_id"] for record in records}
    object_ids = []
    for session_id in session_ids:
        try:
            object_ids.append(ObjectId(session_id))
        except (InvalidId, TypeError):
            continue
    return object_ids


async def _fetch_review_context() -> tuple[list[dict], dict, dict]:
    """DB reads only -- safe to run directly on the event loop."""
    db = get_db()
    records = await db.attendance.find().to_list(length=None)
    if not records:
        return [], {}, {}

    object_ids = await _object_ids_for_sessions(records)
    sessions = await db.sessions.find({"_id": {"$in": object_ids}}).to_list(length=None)
    session_by_id = {str(session["_id"]): session for session in sessions}

    students = await db.students.find().to_list(length=None)
    student_by_index = {student["index"]: student for student in students}

    return records, session_by_id, student_by_index


def _build_review_queue(records: list[dict], session_by_id: dict, student_by_index: dict) -> list[dict]:
    """Blocking: loads every crop from disk and runs SignatureMatcher.
    Must be called via run_in_executor.
    """
    matcher = SignatureMatcher()

    by_student: dict[str, list[dict]] = defaultdict(list)
    skipped_absent = 0
    for record in records:
        if not record.get("present"):
            skipped_absent += 1
            continue
        by_student[record["student_index"]].append(record)

    if skipped_absent:
        logger.info("Skipped %d absent attendance record(s) when building signature review queue", skipped_absent)

    items: list[dict] = []
    for student_index, student_records in by_student.items():
        if len(student_records) < 2:
            continue

        ordered = sorted(student_records, key=lambda r: _session_date(r, session_by_id))
        reference = ordered[0]
        student = student_by_index.get(student_index)
        student_name = student.get("name") if student else student_index

        reference_image = _load_cell_image(reference["cell_image"])

        for record in ordered[1:]:
            session = session_by_id.get(record["session_id"])

            if reference_image is None:
                verdict = dict(_MISSING_IMAGE_VERDICT)
            else:
                candidate_image = _load_cell_image(record["cell_image"])
                verdict = (
                    matcher.verify(candidate_image, [reference_image])
                    if candidate_image is not None
                    else dict(_MISSING_IMAGE_VERDICT)
                )

            items.append(
                {
                    "id": f"{record['session_id']}_{student_index}",
                    "student_id": student_index,
                    "student_name": student_name,
                    "session_id": record["session_id"],
                    "session_date": session.get("date") if session else None,
                    "subject_code": session.get("subject_code") if session else None,
                    "reference_signature": reference["cell_image"],
                    "detected_signature": record["cell_image"],
                    "confidence_score": _confidence_score(record),
                    "similarity_score": verdict["score"],
                    "match_method": verdict["method"],
                    "review_required": verdict["flagged"],
                }
            )

    return items


@router.get("")
async def list_signature_review() -> list[dict]:
    records, session_by_id, student_by_index = await _fetch_review_context()
    if not records:
        return []

    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _build_review_queue, records, session_by_id, student_by_index)


def _present_pairs(records: list[dict], session_by_id: dict) -> tuple[list[dict], int]:
    """Pairs each present attendance record with the immediately preceding
    present record for the same student -- that pair's `previous` is the
    comparison reference for its `current`. Skips absent records entirely
    and each student's first present session, since there's nothing earlier
    to compare it against. Pure computation, no image I/O -- safe to call
    directly on the event loop.
    """
    by_student: dict[str, list[dict]] = defaultdict(list)
    skipped_absent = 0
    for record in records:
        if not record.get("present"):
            skipped_absent += 1
            continue
        by_student[record["student_index"]].append(record)

    pairs: list[dict] = []
    for student_index, student_records in by_student.items():
        ordered = sorted(student_records, key=lambda r: _session_date(r, session_by_id))
        for previous, current in zip(ordered, ordered[1:]):
            pairs.append({"student_index": student_index, "previous": previous, "current": current})

    return pairs, skipped_absent


@router.get("/sessions")
async def list_signature_sessions() -> list[dict]:
    records, session_by_id, _ = await _fetch_review_context()
    if not records:
        return []

    pairs, skipped_absent = _present_pairs(records, session_by_id)
    if skipped_absent:
        logger.info("Skipped %d absent attendance record(s) when listing signature sessions", skipped_absent)

    item_counts: dict[str, int] = defaultdict(int)
    for pair in pairs:
        item_counts[pair["current"]["session_id"]] += 1

    summaries = [
        {
            "session_id": session_id,
            "session_date": session.get("date"),
            "subject_code": session.get("subject_code"),
            "lecturer_name": session.get("lecturer_name"),
            "batch": session.get("batch"),
            "original_filename": session.get("original_filename"),
            "item_count": item_counts.get(session_id, 0),
        }
        for session_id, session in session_by_id.items()
    ]
    summaries.sort(key=lambda s: (s["session_date"] or "", str(s["session_id"])), reverse=True)
    return summaries


def _matcher_for_session(session: dict | None) -> SignatureMatcher:
    """SignatureMatcher tuned by whichever similarity_threshold/orb_nfeatures/
    min_keypoints were submitted on POST /sheets/{id}/process for the
    session that produced the *current* crop being judged (see ProcessOptions
    in app/api/routes/sheets.py, whose full payload is stored on the session
    document as `processing_options`). Any of the three left out at process
    time -- or a session processed before this existed at all -- falls
    through to SignatureMatcher's own constructor defaults.
    """
    config = (session or {}).get("processing_options") or {}
    kwargs = {
        key: value
        for key, value in {
            "similarity_threshold": config.get("similarity_threshold"),
            "nfeatures": config.get("orb_nfeatures"),
            "min_matches": config.get("min_keypoints"),
        }.items()
        if value is not None
    }
    return SignatureMatcher(**kwargs)


def _build_session_items(
    session_id: str,
    pairs: list[dict],
    session_by_id: dict,
    student_by_index: dict,
) -> list[dict]:
    """Blocking: loads every crop from disk and runs SignatureMatcher.
    Must be called via run_in_executor.
    """
    session = session_by_id.get(session_id)
    matcher = _matcher_for_session(session)

    items: list[dict] = []
    for pair in pairs:
        current = pair["current"]
        previous = pair["previous"]
        student_index = pair["student_index"]
        student = student_by_index.get(student_index)
        student_name = student.get("name") if student else student_index
        previous_session = session_by_id.get(previous["session_id"])

        reference_image = _load_cell_image(previous["cell_image"])
        if reference_image is None:
            verdict = dict(_MISSING_IMAGE_VERDICT)
        else:
            candidate_image = _load_cell_image(current["cell_image"])
            verdict = (
                matcher.verify(candidate_image, [reference_image])
                if candidate_image is not None
                else dict(_MISSING_IMAGE_VERDICT)
            )

        items.append(
            {
                "id": f"{session_id}_{student_index}",
                "student_id": student_index,
                "student_name": student_name,
                "session_id": session_id,
                "session_date": session.get("date") if session else None,
                "subject_code": session.get("subject_code") if session else None,
                "previous_session_date": previous_session.get("date") if previous_session else None,
                "reference_signature": previous["cell_image"],
                "detected_signature": current["cell_image"],
                "confidence_score": _confidence_score(current),
                "similarity_score": verdict["score"],
                "match_method": verdict["method"],
                "review_required": verdict["flagged"],
            }
        )

    return items


@router.get("/sessions/{session_id}")
async def get_signature_session_items(session_id: str) -> list[dict]:
    db = get_db()
    try:
        object_id = ObjectId(session_id)
    except (InvalidId, TypeError):
        raise HTTPException(status_code=400, detail="Invalid session id") from None

    session_doc = await db.sessions.find_one({"_id": object_id})
    if session_doc is None:
        raise HTTPException(status_code=404, detail="Session not found")

    records, session_by_id, student_by_index = await _fetch_review_context()
    if not records:
        return []

    pairs, skipped_absent = _present_pairs(records, session_by_id)
    if skipped_absent:
        logger.info(
            "Skipped %d absent attendance record(s) when building signature session %s",
            skipped_absent,
            session_id,
        )

    relevant_pairs = [pair for pair in pairs if pair["current"]["session_id"] == session_id]
    if not relevant_pairs:
        return []

    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        None, _build_session_items, session_id, relevant_pairs, session_by_id, student_by_index
    )


def _to_review(doc: dict) -> dict:
    reviewed_at = doc.get("reviewed_at")
    return {
        "student_index": doc["student_index"],
        "session_id": doc["session_id"],
        "decision": doc["decision"],
        "note": doc.get("note"),
        "reviewed_at": reviewed_at.isoformat() if isinstance(reviewed_at, datetime) else reviewed_at,
    }


@router.get("/reviews")
async def list_signature_reviews() -> list[dict]:
    # Declared as a static "/reviews" path -- FastAPI matches HTTP method +
    # path together, so this can't be swallowed by the dynamic
    # "/{student_index}/verify" or "/{student_index}/review" POST routes
    # below regardless of declaration order, but is grouped with the other
    # GET here to mirror the /trend and /summary ordering note in
    # attendance.py.
    db = get_db()
    docs = await db.signature_reviews.find().to_list(length=None)
    return [_to_review(doc) for doc in docs]


def _verify_student_records(records: list[dict], session_by_id: dict) -> list[dict]:
    """Blocking: compares every session for one student against their
    earliest reference crop. Must be called via run_in_executor.
    """
    matcher = SignatureMatcher()

    ordered = sorted(records, key=lambda r: _session_date(r, session_by_id))
    reference_record = ordered[0]
    reference_image = _load_cell_image(reference_record["cell_image"])

    results: list[dict] = []
    for record in ordered:
        session = session_by_id.get(record["session_id"])
        session_date = session.get("date") if session else None
        subject_code = session.get("subject_code") if session else None

        if record is reference_record:
            results.append(
                {
                    "session_id": record["session_id"],
                    "session_date": session_date,
                    "subject_code": subject_code,
                    "score": 1.0,
                    "mean_score": 1.0,
                    "method": "reference",
                    "reference_count": 0,
                    "flagged": False,
                }
            )
            continue

        if reference_image is None:
            verdict = dict(_MISSING_IMAGE_VERDICT)
        else:
            candidate_image = _load_cell_image(record["cell_image"])
            verdict = (
                matcher.verify(candidate_image, [reference_image])
                if candidate_image is not None
                else dict(_MISSING_IMAGE_VERDICT)
            )

        results.append(
            {
                "session_id": record["session_id"],
                "session_date": session_date,
                "subject_code": subject_code,
                **verdict,
            }
        )

    return results


@router.post("/{student_index}/verify")
async def verify_student_signatures(student_index: str) -> dict:
    db = get_db()
    records = await db.attendance.find({"student_index": student_index}).to_list(length=None)
    if not records:
        raise HTTPException(status_code=404, detail="No attendance records found for this student")

    object_ids = await _object_ids_for_sessions(records)
    sessions = await db.sessions.find({"_id": {"$in": object_ids}}).to_list(length=None)
    session_by_id = {str(session["_id"]): session for session in sessions}

    loop = asyncio.get_running_loop()
    sessions_result = await loop.run_in_executor(None, _verify_student_records, records, session_by_id)

    return {"student_index": student_index, "sessions": sessions_result}


@router.post("/{student_index}/review")
async def submit_signature_review(student_index: str, decision: SignatureReviewDecision) -> dict:
    db = get_db()
    reviewed_at = datetime.utcnow()

    # Upserted on (student_index, session_id) rather than inserted fresh
    # each time -- a student's decision for one session is a single current
    # state (confirmed or flagged), not a log; re-submitting overwrites it
    # instead of leaving stale duplicates for /reviews to sort out.
    await db.signature_reviews.update_one(
        {"student_index": student_index, "session_id": decision.session_id},
        {
            "$set": {
                "student_index": student_index,
                "session_id": decision.session_id,
                "decision": decision.decision,
                "note": decision.note,
                "reviewed_at": reviewed_at,
            }
        },
        upsert=True,
    )

    return {
        "student_index": student_index,
        "session_id": decision.session_id,
        "decision": decision.decision,
        "note": decision.note,
        "reviewed_at": reviewed_at.isoformat(),
    }
