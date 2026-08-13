import cv2
import numpy as np

from app.services.grid_detector import GridDetector


def _binary_grid(rows=4, cols=4, cell_w=150, cell_h=80, margin=40) -> tuple:
    """A plain binarized grid (dark rule lines on a white background,
    following the BinarizeStep convention) with no header row.
    """
    width = margin * 2 + cell_w * cols
    height = margin * 2 + cell_h * rows
    canvas = np.full((height, width), 255, dtype=np.uint8)
    xs = [margin + c * cell_w for c in range(cols + 1)]
    ys = [margin + r * cell_h for r in range(rows + 1)]
    for y in ys:
        cv2.line(canvas, (xs[0], y), (xs[-1], y), 0, 2)
    for x in xs:
        cv2.line(canvas, (x, ys[0]), (x, ys[-1]), 0, 2)
    return canvas, xs, ys


def _binary_grid_with_header(
    data_rows=4, cols=4, cell_w=150, header_h=40, data_h=80, margin=40
) -> np.ndarray:
    """A grid whose first row is a shorter header, filled with short
    vertical tick marks (mimicking printed column titles) rather than a
    solid block -- a full block would smear into the row's own border lines
    when read as a horizontal-line projection and merge the two.
    """
    width = margin * 2 + cell_w * cols
    height = margin * 2 + header_h + data_h * data_rows
    canvas = np.full((height, width), 255, dtype=np.uint8)
    xs = [margin + c * cell_w for c in range(cols + 1)]
    ys = [margin, margin + header_h]
    for _ in range(data_rows):
        ys.append(ys[-1] + data_h)

    for y in ys:
        cv2.line(canvas, (xs[0], y), (xs[-1], y), 0, 2)
    for x in xs:
        cv2.line(canvas, (x, ys[0]), (x, ys[-1]), 0, 2)

    for c in range(cols):
        cx0 = xs[c]
        for tick in range(5):
            tx = cx0 + 15 + tick * 20
            cv2.line(canvas, (tx, ys[0] + 10), (tx, ys[1] - 10), 0, 2)

    return canvas


def test_detect_synthetic_grid_finds_known_row_and_column_count():
    image, xs, ys = _binary_grid(rows=4, cols=4)
    detector = GridDetector()

    rows = detector.detect(image)

    assert len(rows) == 4
    assert all(len(row) == 4 for row in rows)


def test_drop_header_rows_fires_on_synthetic_header():
    image = _binary_grid_with_header(data_rows=4, cols=4)
    detector = GridDetector(header_rows=1)

    rows = detector.detect(image)
    assert len(rows) == 5  # header + 4 data rows, before dropping

    data_only = detector.drop_header_rows(rows, expected_row_count=4)

    assert len(data_only) == 4


def test_detect_blank_image_returns_empty_without_raising():
    blank = np.full((400, 600), 255, dtype=np.uint8)
    detector = GridDetector()

    rows = detector.detect(blank)

    assert rows == []


def test_drop_header_rows_keeps_all_rows_when_none_available_to_compare():
    detector = GridDetector(header_rows=1)

    result = detector.drop_header_rows([], expected_row_count=None)

    assert result == []
