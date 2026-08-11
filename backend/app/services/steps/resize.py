from typing import Any

import cv2
import numpy as np

from app.services.steps.base import PipelineStep


class ResizeStep(PipelineStep):
    """Resizes the source image to a fixed width of 2000px, preserving aspect
    ratio, using cv2.resize. Attendance sheets are photographed at varying
    distances and camera resolutions; normalizing to a known width means every
    later step (bilateral filter kernel size, adaptive-threshold block size,
    cell-grid detection) can use fixed pixel-scale parameters instead of having
    to adapt to arbitrary input dimensions.
    """

    name = "resize"
    TARGET_WIDTH = 2000

    def __init__(self, order: int, target_width: int = TARGET_WIDTH) -> None:
        super().__init__(order)
        self.target_width = target_width

    def apply(self, image: np.ndarray, context: dict[str, Any]) -> np.ndarray:
        height, width = image.shape[:2]
        scale = self.target_width / float(width)
        new_size = (self.target_width, int(round(height * scale)))
        interpolation = cv2.INTER_AREA if scale < 1 else cv2.INTER_LINEAR
        return cv2.resize(image, new_size, interpolation=interpolation)
