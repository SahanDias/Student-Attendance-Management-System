from typing import Any

import cv2
import numpy as np

from app.services.steps.base import PipelineStep


class BinarizeStep(PipelineStep):
    """Converts the grayscale image to a binary (black/white) image using
    adaptive Gaussian thresholding: the cutoff for each pixel is computed from
    a Gaussian-weighted average of its local neighborhood minus a constant `C`,
    so the threshold tracks local lighting instead of one fixed value -- this
    is what makes it robust to shadows and uneven illumination across a
    scanned sheet. A global Otsu threshold (a single cutoff chosen to minimize
    intra-class intensity variance over the whole image) is also computed and
    stored in `context["otsu_image"]` purely for comparison/reporting; the
    adaptive result is what the pipeline carries forward.
    """

    name = "binarize"
    BLOCK_SIZE = 35
    C = 11

    def apply(self, image: np.ndarray, context: dict[str, Any]) -> np.ndarray:
        gray = (
            cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image
        )

        adaptive = cv2.adaptiveThreshold(
            gray,
            255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY,
            self.BLOCK_SIZE,
            self.C,
        )

        otsu = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)[1]
        context["otsu_image"] = otsu

        return adaptive
