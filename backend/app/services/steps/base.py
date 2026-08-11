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

    