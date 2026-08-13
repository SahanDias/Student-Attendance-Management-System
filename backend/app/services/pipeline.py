from dataclasses import dataclass
from typing import Any, Callable

import cv2
import numpy as np

from app.core.storage import StorageManager
from app.models.schemas import StepImage
from app.services.steps.base import PipelineStep
from app.services.steps.deskew import DeskewStep

ProgressCallback = Callable[[str, int, int, str], None]


@dataclass
class PipelineResult:
    final_image: np.ndarray
    context: dict[str, Any]
    steps: list[StepImage]


class Pipeline:
    """Runs an ordered sequence of PipelineStep instances over a source image,
    persisting a numbered PNG snapshot of each step's output for auditing.
    """

    def __init__(
        self, steps: list[PipelineStep], storage: StorageManager | None = None
    ) -> None:
        self.steps = sorted(steps, key=lambda step: step.order)
        self.storage = storage or StorageManager()

    def run(
        self,
        image_path: str,
        session_id: str,
        progress_callback: ProgressCallback | None = None,
    ) -> PipelineResult:
        image = cv2.imread(image_path)
        if image is None:
            raise ValueError(f"Could not read image at {image_path}")

        context: dict[str, Any] = {}
        step_images: list[StepImage] = []
        total = len(self.steps)

        for step in self.steps:
            image = step.apply(image, context)
            path = step.save_visual(image, session_id, self.storage)
            step_images.append(StepImage(name=step.name, order=step.order, path=path))
            if progress_callback is not None:
                progress_callback(step.name, step.order, total, path)

            if step.name == "resize":
                context["color_resized"] = image.copy()

            if step.name == "deskew":
                # DeskewStep only ever sees the grayscale branch, so the still
                # -color "color_resized" frame has to be warped through the
                # identical transform here or grid coordinates (computed later
                # from the deskewed grayscale/binary branch) won't line up
                # with cell crops taken from an unrotated color frame.
                deskew_matrix = context.get("deskew_matrix")
                color_resized = context["color_resized"]
                if deskew_matrix is not None:
                    height, width = color_resized.shape[:2]
                    context["color_aligned"] = cv2.warpAffine(
                        color_resized,
                        deskew_matrix,
                        (width, height),
                        flags=DeskewStep.INTERPOLATION_FLAG,
                        borderMode=DeskewStep.BORDER_MODE,
                    )
                else:
                    context["color_aligned"] = color_resized

        assert context["color_aligned"].shape[:2] == image.shape[:2], (
            f"color_aligned {context['color_aligned'].shape[:2]} does not match "
            f"the final binary image {image.shape[:2]}"
        )

        return PipelineResult(final_image=image, context=context, steps=step_images)
