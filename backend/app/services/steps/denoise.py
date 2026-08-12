from typing import Any

import cv2
import numpy as np

from app.services.steps.base import PipelineStep


class DenoiseStep(PipelineStep):
    """Smooths sensor and paper-texture noise with a bilateral filter, which
    averages each pixel's neighborhood weighted by both spatial distance and
    intensity similarity -- unlike a plain Gaussian blur, it preserves strong
    edges (handwriting strokes, grid lines) while flattening low-contrast
    texture noise. If the bilateral filter fails (e.g. on an unsupported dtype
    or channel layout), a median blur is used as a fallback, which removes
    salt-and-pepper noise by replacing each pixel with the median value of its
    neighborhood.
    """

    name = "denoise"

    def apply(self, image: np.ndarray, context: dict[str, Any]) -> np.ndarray:
        try:
            return cv2.bilateralFilter(image, d=9, sigmaColor=75, sigmaSpace=75)
        except cv2.error:
            return cv2.medianBlur(image, 5)
