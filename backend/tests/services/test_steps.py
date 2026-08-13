import cv2
import numpy as np

from app.services.steps.binarize import BinarizeStep
from app.services.steps.deskew import DeskewStep
from app.services.steps.denoise import DenoiseStep
from app.services.steps.grayscale import GrayscaleStep
from app.services.steps.resize import ResizeStep


def _color_image(height=300, width=400) -> np.ndarray:
    rng = np.random.default_rng(42)
    return rng.integers(0, 256, size=(height, width, 3), dtype=np.uint8)


def test_resize_step_scales_to_target_width_preserving_aspect_ratio():
    step = ResizeStep(order=1, target_width=200)
    image = _color_image(height=300, width=400)

    output = step.apply(image, {})

    assert output.shape[1] == 200
    assert output.shape[0] == 150  # 300 * (200/400)
    assert output.dtype == np.uint8
    assert output.ndim == 3


def test_grayscale_step_produces_single_channel_output():
    step = GrayscaleStep(order=2)
    image = _color_image()

    output = step.apply(image, {})

    assert output.ndim == 2
    assert output.shape == (300, 400)
    assert output.dtype == np.uint8


def test_denoise_step_preserves_shape_and_dtype():
    step = DenoiseStep(order=3)
    image = _color_image()

    output = step.apply(image, {})

    assert output.shape == image.shape
    assert output.dtype == np.uint8


def test_binarize_step_output_is_strictly_two_valued():
    step = BinarizeStep(order=5)
    image = _color_image()

    output = step.apply(image, {})

    assert output.ndim == 2
    assert output.dtype == np.uint8
    assert set(np.unique(output).tolist()).issubset({0, 255})


def test_binarize_step_stores_otsu_comparison_in_context():
    step = BinarizeStep(order=5)
    image = _color_image()
    context: dict = {}

    step.apply(image, context)

    assert "otsu_image" in context
    assert set(np.unique(context["otsu_image"]).tolist()).issubset({0, 255})


def _synthetic_grid(rows=5, cols=4, cell_w=150, cell_h=80, margin=40) -> np.ndarray:
    width = margin * 2 + cell_w * cols
    height = margin * 2 + cell_h * rows
    canvas = np.full((height, width, 3), 255, dtype=np.uint8)
    xs = [margin + c * cell_w for c in range(cols + 1)]
    ys = [margin + r * cell_h for r in range(rows + 1)]
    for y in ys:
        cv2.line(canvas, (xs[0], y), (xs[-1], y), (0, 0, 0), 2)
    for x in xs:
        cv2.line(canvas, (x, ys[0]), (x, ys[-1]), (0, 0, 0), 2)
    return canvas


def test_deskew_step_detects_known_rotation_within_tolerance():
    image = _synthetic_grid()
    height, width = image.shape[:2]
    center = (width / 2.0, height / 2.0)

    known_angle_degrees = 3.0
    rotation_matrix = cv2.getRotationMatrix2D(center, known_angle_degrees, 1.0)
    rotated = cv2.warpAffine(
        image, rotation_matrix, (width, height),
        flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE,
    )

    step = DeskewStep(order=4)
    context: dict = {}
    output = step.apply(rotated, context)

    # The correction angle must counter the applied rotation, within one
    # coarse search step (0.5 degrees) of tolerance.
    assert abs(context["deskew_angle"] - (-known_angle_degrees)) < 1.0
    assert context["deskew_matrix"] is not None
    assert output.shape == rotated.shape


def test_deskew_step_skips_rotation_when_already_aligned():
    image = _synthetic_grid()
    step = DeskewStep(order=4)
    context: dict = {}

    output = step.apply(image, context)

    # Whichever of the two skip conditions fires (negligible angle, or best
    # score not meaningfully better than the unrotated baseline), an already
    # -aligned grid must come back untouched rather than getting a spurious
    # rotation applied.
    assert context["deskew_matrix"] is None
    assert np.array_equal(output, image)
