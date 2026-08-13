import logging
from typing import Any

import cv2
import numpy as np

from app.core.storage import StorageManager
from app.services.steps.base import PipelineStep

logger = logging.getLogger(__name__)


class DeskewStep(PipelineStep):
    """Corrects small rotational skew from uneven scanning or hand-held photos.

    The previous approach (cv2.HoughLinesP, taking the median angle of
    near-horizontal segments) fails on real photos because the surviving
    segments are BIMODAL: one cluster sits on the printed table rules (the
    correct signal), another sits on the desk edge / page boundary (noise
    at a different angle), typically in roughly equal numbers. The median of
    a bimodal distribution lands between the two clusters rather than in
    either one -- on a real sheet this produced +1.95 degrees when the true
    correction was -1.90 degrees, the opposite sign, which rotated the page
    the wrong way and roughly doubled its skew instead of fixing it.

    This replaces angle *estimation* with angle *search*: score(angle)
    rotates the page by that candidate angle, binarizes it, extracts
    horizontal structure via morphological opening, and takes the peak of
    the row-sum projection of that mask. A correctly deskewed table's rules
    line up into full-width rows, producing a tall, narrow peak; a skewed
    table smears that same ink across many rows, flattening the peak. The
    angle that maximizes this peak is trusted directly -- there's no
    Hough-segment classification step left to be fooled by non-table
    structure, because non-table edges don't organize into the same
    full-width horizontal bands the printed grid does.

    A coarse sweep across the full plausible range is followed by a fine
    sweep around the coarse winner, trading a bit of resolution in the
    coarse pass for speed. If the best score found isn't meaningfully
    better than the unrotated baseline, no table structure was found and
    rotation is skipped rather than risking a confident-looking wrong
    answer.
    """

    name = "deskew"
    SKIP_THRESHOLD_DEGREES = 0.3
    MIN_SCORE_RATIO = 2.0
    COARSE_RANGE_DEGREES = 6.0
    COARSE_STEP_DEGREES = 0.5
    FINE_RANGE_DEGREES = 0.5
    FINE_STEP_DEGREES = 0.1
    ADAPTIVE_BLOCK_SIZE = 31
    ADAPTIVE_C = 10
    HORIZONTAL_KERNEL_DIVISOR = 25
    SEARCH_INTERPOLATION_FLAG = cv2.INTER_LINEAR
    FINAL_INTERPOLATION_FLAG = cv2.INTER_CUBIC
    # Alias for FINAL_INTERPOLATION_FLAG: app/services/pipeline.py warps the
    # still-color frame through this same transform outside of apply() (see
    # its "deskew" branch) and reads INTERPOLATION_FLAG/BORDER_MODE directly
    # off the class rather than duplicating these values.
    INTERPOLATION_FLAG = cv2.INTER_CUBIC
    BORDER_MODE = cv2.BORDER_REPLICATE
    # BORDER_REPLICATE during the search smears the frame's own edge pixels
    # across the corner wedges a rotation exposes, and that smear is long
    # and axis-aligned enough to survive the horizontal-line opening below
    # -- producing a fake "table structure" peak that grows with the angle
    # regardless of what the frame actually contains. A constant white fill
    # matches a real page's blank margin and stays inert at every angle.
    SEARCH_BORDER_MODE = cv2.BORDER_CONSTANT
    SEARCH_BORDER_VALUE = 255

    def __init__(
        self,
        order: int,
        adaptive_block_size: int = ADAPTIVE_BLOCK_SIZE,
        adaptive_c: int = ADAPTIVE_C,
        coarse_range_degrees: float = COARSE_RANGE_DEGREES,
    ) -> None:
        super().__init__(order)
        # Configurable via the Settings page's PROCESSING group ("Adaptive
        # threshold block size/constant" and "Deskew search range in
        # degrees") -- these three tune this step's own internal angle-search
        # scoring, not the pipeline's separate BinarizeStep.
        self.adaptive_block_size = adaptive_block_size
        self.adaptive_c = adaptive_c
        self.coarse_range_degrees = coarse_range_degrees

    def apply(self, image: np.ndarray, context: dict[str, Any]) -> np.ndarray:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image
        height, width = gray.shape[:2]
        center = (width / 2.0, height / 2.0)

        baseline_score = self._score(gray, 0.0, center)

        coarse_angles = self._angle_range(
            0.0, self.coarse_range_degrees, self.COARSE_STEP_DEGREES
        )
        coarse_best_angle, _ = self._search(gray, coarse_angles, center)

        fine_angles = self._angle_range(
            coarse_best_angle, self.FINE_RANGE_DEGREES, self.FINE_STEP_DEGREES
        )
        best_angle, best_score = self._search(gray, fine_angles, center)

        context["deskew_angle"] = best_angle
        logger.info(
            "deskew: chosen angle %.2f degrees (score %.1f, score(0.0) %.1f)",
            best_angle,
            best_score,
            baseline_score,
        )

        if abs(best_angle) < self.SKIP_THRESHOLD_DEGREES:
            context["deskew_matrix"] = None
            return image

        if best_score < self.MIN_SCORE_RATIO * baseline_score:
            logger.info(
                "deskew: skipping rotation - best score %.1f is less than %.1fx the "
                "unrotated baseline score %.1f; no table structure found",
                best_score,
                self.MIN_SCORE_RATIO,
                baseline_score,
            )
            context["deskew_matrix"] = None
            return image

        rotation_matrix = cv2.getRotationMatrix2D(center, best_angle, 1.0)
        context["deskew_matrix"] = rotation_matrix

        return cv2.warpAffine(
            image,
            rotation_matrix,
            (width, height),
            flags=self.FINAL_INTERPOLATION_FLAG,
            borderMode=self.BORDER_MODE,
        )

    @staticmethod
    def _angle_range(center: float, span: float, step: float) -> list[float]:
        """Inclusive [center - span, center + span] in `step` increments,
        built from integer offsets rather than float accumulation so the
        endpoints land exactly rather than drifting by a fraction of a step.
        """
        steps = int(round(span / step))
        return [round(center + offset * step, 10) for offset in range(-steps, steps + 1)]

    def _search(
        self, gray: np.ndarray, angles: list[float], center: tuple[float, float]
    ) -> tuple[float, float]:
        best_angle = 0.0
        best_score = -1.0
        for angle in angles:
            score = self._score(gray, angle, center)
            if score > best_score:
                best_angle, best_score = angle, score
        return best_angle, best_score

    def _score(self, gray: np.ndarray, angle: float, center: tuple[float, float]) -> float:
        """Higher is better: the peak row-sum of the rotated frame's
        horizontal-line mask. A correctly deskewed table concentrates its
        rules into full-width rows (a tall peak); a skewed one spreads that
        same ink across many partial rows (a flat, low peak).
        """
        height, width = gray.shape[:2]
        rotation_matrix = cv2.getRotationMatrix2D(center, angle, 1.0)
        rotated = cv2.warpAffine(
            gray,
            rotation_matrix,
            (width, height),
            flags=self.SEARCH_INTERPOLATION_FLAG,
            borderMode=self.SEARCH_BORDER_MODE,
            borderValue=self.SEARCH_BORDER_VALUE,
        )

        binary = cv2.adaptiveThreshold(
            rotated,
            255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY,
            self.adaptive_block_size,
            self.adaptive_c,
        )
        inverted = cv2.bitwise_not(binary)

        kernel_length = max(width // self.HORIZONTAL_KERNEL_DIVISOR, 1)
        horizontal_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (kernel_length, 1))
        horizontal_lines = cv2.morphologyEx(
            inverted, cv2.MORPH_OPEN, horizontal_kernel, iterations=1
        )

        row_sums = horizontal_lines.sum(axis=1)
        return float(row_sums.max()) if row_sums.size else 0.0

    def save_visual(self, image: np.ndarray, session_id: str, storage: StorageManager) -> str:
        path = super().save_visual(image, session_id, storage)

        # step_path() always formats as "{order:02d}_{name}" (with an
        # underscore), which can't produce the "04a_..." sub-step name asked
        # for -- so this is written the same way step_path builds its
        # directory, just without going through it for the filename. Nothing
        # is drawn on top: there are no Hough segments left to annotate, so
        # this is just the rotated (or, if skipped, unrotated) result again.
        directory = storage.root / "steps" / session_id
        directory.mkdir(parents=True, exist_ok=True)
        debug_path = directory / f"{self.order:02d}a_deskew_lines.png"
        cv2.imwrite(str(debug_path), image)

        return path
