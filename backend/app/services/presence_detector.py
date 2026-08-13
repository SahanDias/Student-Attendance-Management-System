import logging

import cv2
import numpy as np

logger = logging.getLogger(__name__)


class PresenceDetector:
    """Decides whether a signature cell has been signed, by looking for pen ink
    rather than trying to read a mark. Colored ink (blue/black ballpoint, etc.)
    stands out from the near-zero-saturation printed grid/paper in the HSV
    saturation channel, while a separate dark-pixel mask catches low-saturation
    black pen/pencil strokes that saturation alone would miss. The two masks
    are combined into a single ink mask, and connectedComponentsWithStats is
    used to reject scanner noise/specks by requiring the single largest ink
    blob to clear a minimum pixel area before the cell counts as signed.

    This measures whatever array it's handed with no cropping of its own --
    it used to pad inward itself to keep the cell's own grid border out of
    the measurement, but that let the printed row rule slip in whenever the
    caller's crop ran generous (an empty cell's rule line is dark and
    near-full-width, so it alone cleared both thresholds below). Excluding
    the rule is now CellExtractor's job: it hands this class a separate,
    deliberately tight crop with no vertical expansion, built specifically
    so the rule can't appear in it (see CellExtractor.extract_signature_cells
    and its `presence_*_shrink_ratio` arguments). Callers must pass that
    tight crop here, not the generous one saved as NN_signature_col{col}.png
    for SignatureMatcher/the review queue.
    """

    def __init__(
        self,
        saturation_threshold: int = 40,
        dark_value_threshold: int = 90,
        min_ink_ratio: float = 0.02,
        min_component_area: int = 100,
    ) -> None:
        self.saturation_threshold = saturation_threshold
        self.dark_value_threshold = dark_value_threshold
        self.min_ink_ratio = min_ink_ratio
        self.min_component_area = min_component_area
        # Measured on a real sheet: signed cells run 5.06%-18.14% ink / a
        # 254-956px largest component, unsigned 0.00%-0.42% / 0-24px -- the
        # defaults above sit well inside that gap.

    def is_present(
        self, cell_bgr: np.ndarray, row_index: int | None = None
    ) -> tuple[bool, float, float]:
        """Return (present, ink_ratio, confidence) for a cropped signature cell.

        `cell_bgr` must be the TIGHT presence crop from
        CellExtractor.extract_signature_cells (its second return value), not
        the generous crop written to disk as NN_signature_col{col}.png --
        see the class docstring for why the two are no longer the same
        array.

        `row_index`, when given, is used only to label the diagnostic log
        line below -- it plays no part in the present/absent decision.
        """
        hsv = cv2.cvtColor(cell_bgr, cv2.COLOR_BGR2HSV)
        saturation = hsv[:, :, 1]
        value = hsv[:, :, 2]

        colored_ink_mask = saturation >= self.saturation_threshold
        dark_ink_mask = value <= self.dark_value_threshold
        ink_mask = np.where(colored_ink_mask | dark_ink_mask, 255, 0).astype(np.uint8)

        total_pixels = ink_mask.size
        ink_pixels = int(np.count_nonzero(ink_mask))
        ink_ratio = ink_pixels / total_pixels if total_pixels else 0.0

        num_labels, _, stats, _ = cv2.connectedComponentsWithStats(
            ink_mask, connectivity=8
        )
        largest_component_area = 0
        for label in range(1, num_labels):  # label 0 is the background
            area = int(stats[label, cv2.CC_STAT_AREA])
            if area > largest_component_area:
                largest_component_area = area

        present = (
            ink_ratio >= self.min_ink_ratio
            and largest_component_area >= self.min_component_area
        )

        logger.info(
            "PresenceDetector: row=%s ink_ratio=%.4f (threshold>=%.4f, %s) "
            "largest_component_area=%d (threshold>=%d, %s) -> %s",
            row_index if row_index is not None else "?",
            ink_ratio,
            self.min_ink_ratio,
            "pass" if ink_ratio >= self.min_ink_ratio else "fail",
            largest_component_area,
            self.min_component_area,
            "pass" if largest_component_area >= self.min_component_area else "fail",
            "PRESENT" if present else "ABSENT",
        )

        # Confidence blends both signals, each normalized against 3x its
        # pass/fail threshold so it climbs smoothly past the boundary instead
        # of jumping straight from 0 to 1 the moment a threshold is crossed.
        area_score = min(largest_component_area / (self.min_component_area * 3), 1.0)
        ratio_score = min(ink_ratio / (self.min_ink_ratio * 3), 1.0)
        confidence = float(np.clip(0.5 * area_score + 0.5 * ratio_score, 0.0, 1.0))

        return present, ink_ratio, confidence
