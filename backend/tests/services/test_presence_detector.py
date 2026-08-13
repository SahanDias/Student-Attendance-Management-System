import numpy as np
import cv2

from app.services.presence_detector import PresenceDetector

CELL_HEIGHT = 80
CELL_WIDTH = 130


def _blank_cell() -> np.ndarray:
    return np.full((CELL_HEIGHT, CELL_WIDTH, 3), 255, dtype=np.uint8)


def test_is_present_blank_white_cell_is_absent():
    detector = PresenceDetector()

    present, ink_ratio, confidence = detector.is_present(_blank_cell())

    assert present is False
    assert ink_ratio == 0.0
    assert 0.0 <= confidence <= 1.0


def test_is_present_heavy_ink_cell_is_present():
    cell = _blank_cell()
    cv2.rectangle(cell, (10, 10), (CELL_WIDTH - 10, CELL_HEIGHT - 10), (10, 10, 10), thickness=-1)
    detector = PresenceDetector()

    present, ink_ratio, confidence = detector.is_present(cell)

    assert present is True
    assert ink_ratio > detector.min_ink_ratio
    assert 0.0 <= confidence <= 1.0


def test_is_present_small_noise_speck_is_absent():
    """A handful of dark pixels clears neither the ink-ratio nor the
    connected-component area threshold, so it must not register as signed.
    """
    cell = _blank_cell()
    cv2.rectangle(cell, (5, 5), (8, 8), (0, 0, 0), thickness=-1)
    detector = PresenceDetector()

    present, ink_ratio, confidence = detector.is_present(cell)

    assert present is False
    assert 0.0 <= confidence <= 1.0


def test_is_present_confidence_always_in_unit_range():
    detector = PresenceDetector()
    cases = [_blank_cell()]
    heavy = _blank_cell()
    cv2.rectangle(heavy, (0, 0), (CELL_WIDTH, CELL_HEIGHT), (0, 0, 0), thickness=-1)
    cases.append(heavy)

    for cell in cases:
        _, _, confidence = detector.is_present(cell)
        assert 0.0 <= confidence <= 1.0
