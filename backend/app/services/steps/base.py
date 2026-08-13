from abc import ABC, abstractmethod
from typing import Any

import cv2
import numpy as np

from app.core.storage import StorageManager


class PipelineStep(ABC):
    """Base class for a single stage in the attendance-sheet image pipeline."""

    name: str
    order: int

    def __init__(self, order: int) -> None:
        self.order = order

    @abstractmethod
    def apply(self, image: np.ndarray, context: dict[str, Any]) -> np.ndarray:
        """Apply this step's transformation to `image` and return the result.

        `context` is shared and mutated across all steps in a pipeline run, so a
        step can stash intermediate data (e.g. an alternate thresholding result)
        for later steps or for reporting/debugging.
        """
        raise NotImplementedError

    def save_visual(
        self, image: np.ndarray, session_id: str, storage: StorageManager
    ) -> str:
        """Write this step's output image as a PNG via StorageManager and return
        the path (relative to the project root) it was written to."""
        relative_path = storage.step_path(session_id, self.order, f"{self.name}.png")
        cv2.imwrite(relative_path, image)
        return relative_path
