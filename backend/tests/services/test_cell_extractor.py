import numpy as np
import pytest

from app.core.storage import StorageManager
from app.services.cell_extractor import CellExtractor
from app.models.schemas import Student


def _expected_bounds(box, image_width, image_height, extractor):
    """Mirrors CellExtractor.extract_signature_cells's own arithmetic, so
    tests can assert against it without re-deriving crops from pixels.
    """
    x, y, w, h = box

    shrink_x = int(round(w * extractor.horizontal_shrink_ratio))
    shrink_y = int(round(h * extractor.vertical_shrink_ratio))
    expand_y = int(round(h * extractor.vertical_expansion_ratio))
    sig = (
        max(x + shrink_x, 0),
        max(y + shrink_y - expand_y, 0),
        min(x + w - shrink_x, image_width),
        min(y + h - shrink_y + expand_y, image_height),
    )

    pres_shrink_x = int(round(w * extractor.presence_horizontal_shrink_ratio))
    pres_shrink_y = int(round(h * extractor.presence_vertical_shrink_ratio))
    pres = (
        max(x + pres_shrink_x, 0),
        max(y + pres_shrink_y, 0),
        min(x + w - pres_shrink_x, image_width),
        min(y + h - pres_shrink_y, image_height),
    )
    return sig, pres


def _make_image(width=680, height=440) -> np.ndarray:
    return np.full((height, width, 3), 255, dtype=np.uint8)


def test_extract_signature_cells_generous_crop_contains_tight_crop(tmp_path):
    image = _make_image()
    # A single interior row, comfortably away from every image edge so
    # clamping never kicks in -- isolates the pure containment property.
    row = [(40, 120, 150, 80), (190, 120, 150, 80), (340, 120, 150, 80), (490, 120, 150, 80)]
    rows = [row]

    storage = StorageManager(root=str(tmp_path))
    extractor = CellExtractor("session-1", storage=storage, signature_col=-1)

    signature_crops, presence_crops = extractor.extract_signature_cells(image, rows)

    box = row[-1]  # signature_col=-1 -> last column
    sig, pres = _expected_bounds(box, image.shape[1], image.shape[0], extractor)
    sig_x1, sig_y1, sig_x2, sig_y2 = sig
    pres_x1, pres_y1, pres_x2, pres_y2 = pres

    assert sig_x1 <= pres_x1 and pres_x2 <= sig_x2
    assert sig_y1 <= pres_y1 and pres_y2 <= sig_y2

    assert signature_crops[0].shape[:2] == (sig_y2 - sig_y1, sig_x2 - sig_x1)
    assert presence_crops[0].shape[:2] == (pres_y2 - pres_y1, pres_x2 - pres_x1)


def test_extract_signature_cells_edge_row_stays_within_image_bounds(tmp_path):
    image = _make_image(width=680, height=200)
    # Row 0 sits flush against the top edge -- the generous crop's vertical
    # expansion would push above y=0 without clamping.
    top_row = [(40, 0, 150, 80), (190, 0, 150, 80), (340, 0, 150, 80), (490, 0, 150, 80)]
    rows = [top_row]

    storage = StorageManager(root=str(tmp_path))
    extractor = CellExtractor("session-2", storage=storage, signature_col=-1)

    signature_crops, presence_crops = extractor.extract_signature_cells(image, rows)

    box = top_row[-1]
    sig, pres = _expected_bounds(box, image.shape[1], image.shape[0], extractor)
    sig_x1, sig_y1, sig_x2, sig_y2 = sig

    assert sig_y1 == 0  # clamped, not a negative/wrapped index
    assert signature_crops[0].size > 0
    assert presence_crops[0].size > 0
    assert signature_crops[0].shape[:2] == (sig_y2 - sig_y1, sig_x2 - sig_x1)


def test_validate_alignment_raises_on_row_student_count_mismatch():
    rows = [[(0, 0, 10, 10)], [(0, 10, 10, 10)]]
    students = [Student(index="1", name="A", batch="", row_no=1)]

    with pytest.raises(ValueError, match="Row/student count mismatch"):
        CellExtractor.validate_alignment(rows, students)


def test_validate_alignment_passes_when_counts_match():
    rows = [[(0, 0, 10, 10)]]
    students = [Student(index="1", name="A", batch="", row_no=1)]

    CellExtractor.validate_alignment(rows, students)  # must not raise
