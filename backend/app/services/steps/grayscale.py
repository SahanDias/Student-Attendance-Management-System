from typing import Any

import cv2
import numpy as np

from app.services.steps.base import PipelineStep


class GrayscaleStep(PipelineStep):
    """Converts the BGR image to single-channel grayscale via cv2.cvtColor
    (COLOR_BGR2GRAY), which reduces each pixel to a luminosity-weighted sum
    of its channels (0.299*R + 0.587*G + 0.114*B). Attendance-sheet detection
    only cares about ink vs. paper contrast, not color, and every thresholding
    step downstream requires a single-channel input.
    """

    name = "grayscale"

    def apply(self, image: np.ndarray, context: dict[str, Any]) -> np.ndarray:
        return cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
