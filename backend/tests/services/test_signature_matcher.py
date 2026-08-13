import cv2
import numpy as np

from app.services.signature_matcher import SignatureMatcher

CELL_HEIGHT = 80
CELL_WIDTH = 150


def _blank() -> np.ndarray:
    return np.full((CELL_HEIGHT, CELL_WIDTH, 3), 255, dtype=np.uint8)


def _signature_a() -> np.ndarray:
    img = _blank()
    cv2.line(img, (20, 20), (120, 60), (10, 10, 10), 3)
    cv2.line(img, (30, 60), (100, 20), (10, 10, 10), 3)
    cv2.line(img, (20, 40), (130, 40), (10, 10, 10), 2)
    return img


def _signature_b() -> np.ndarray:
    """A shape clearly distinct from _signature_a: a single circle instead
    of criss-crossing strokes, occupying a different footprint.
    """
    img = _blank()
    cv2.circle(img, (75, 40), 30, (10, 10, 10), 3)
    return img


def test_verify_identical_crop_against_itself_is_high_score_not_flagged():
    matcher = SignatureMatcher()
    signature = _signature_a()

    result = matcher.verify(signature, [signature])

    assert result["score"] >= 0.95
    assert result["flagged"] is False


def test_verify_clearly_different_crops_is_low_score_flagged():
    matcher = SignatureMatcher()

    result = matcher.verify(_signature_a(), [_signature_b()])

    assert result["score"] < matcher.similarity_threshold
    assert result["flagged"] is True


def test_verify_featureless_crop_falls_back_to_structural_without_crash():
    """A blank crop yields no ORB keypoints at all; verify() must fall back
    to the structural comparison path rather than raising.
    """
    matcher = SignatureMatcher()

    result = matcher.verify(_blank(), [_signature_a()])

    assert result["method"] == "structural"
    assert 0.0 <= result["score"] <= 1.0
    assert result["flagged"] is True


def test_compare_featureless_crop_reports_insufficient_keypoints():
    matcher = SignatureMatcher()

    result = matcher.compare(matcher.preprocess(_blank()), matcher.preprocess(_signature_a()))

    assert result["sufficient_keypoints"] is False
    assert result["orb_score"] == 0.0
