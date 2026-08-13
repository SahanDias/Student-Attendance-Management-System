from pathlib import Path

import cv2

from app.core.storage import StorageManager
from app.services.pipeline import Pipeline
from app.services.steps.binarize import BinarizeStep
from app.services.steps.deskew import DeskewStep
from app.services.steps.denoise import DenoiseStep
from app.services.steps.grayscale import GrayscaleStep
from app.services.steps.resize import ResizeStep


def _build_steps() -> list:
    return [
        ResizeStep(order=1, target_width=400),
        GrayscaleStep(order=2),
        DenoiseStep(order=3),
        DeskewStep(order=4),
        BinarizeStep(order=5),
    ]


def test_pipeline_runs_steps_in_registered_order_and_writes_debug_images(
    synthetic_sheet, tmp_path
):
    image_path = tmp_path / "sheet.png"
    cv2.imwrite(str(image_path), synthetic_sheet())

    storage = StorageManager(root=str(tmp_path / "storage"))
    # Deliberately out of order -- Pipeline.__init__ sorts by `order`.
    steps = list(reversed(_build_steps()))
    pipeline = Pipeline(steps, storage=storage)

    result = pipeline.run(str(image_path), session_id="session-1")

    assert [step.order for step in result.steps] == [1, 2, 3, 4, 5]
    assert [step.name for step in result.steps] == [
        "resize",
        "grayscale",
        "denoise",
        "deskew",
        "binarize",
    ]
    for step_image in result.steps:
        assert Path(step_image.path).exists(), f"debug image missing for step {step_image.name}"


def test_pipeline_keeps_color_frame_aligned_with_final_binary_image(synthetic_sheet, tmp_path):
    image_path = tmp_path / "sheet.png"
    cv2.imwrite(str(image_path), synthetic_sheet())

    storage = StorageManager(root=str(tmp_path / "storage"))
    pipeline = Pipeline(_build_steps(), storage=storage)

    result = pipeline.run(str(image_path), session_id="session-2")

    assert "color_aligned" in result.context
    assert result.context["color_aligned"].shape[:2] == result.final_image.shape[:2]


def test_pipeline_invokes_progress_callback_per_step(synthetic_sheet, tmp_path):
    image_path = tmp_path / "sheet.png"
    cv2.imwrite(str(image_path), synthetic_sheet())

    storage = StorageManager(root=str(tmp_path / "storage"))
    pipeline = Pipeline(_build_steps(), storage=storage)

    calls: list[tuple[str, int, int]] = []

    def progress_callback(step_name, order, total, path):
        calls.append((step_name, order, total))

    pipeline.run(str(image_path), session_id="session-3", progress_callback=progress_callback)

    assert [c[0] for c in calls] == ["resize", "grayscale", "denoise", "deskew", "binarize"]
    assert all(total == 5 for _, _, total in calls)
