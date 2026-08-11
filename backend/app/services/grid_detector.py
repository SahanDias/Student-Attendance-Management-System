import logging
from collections import Counter

import cv2
import numpy as np

from app.core.storage import StorageManager

Box = tuple[int, int, int, int]

logger = logging.getLogger(__name__)


class GridDetector:
    """Locates the table's cell grid in a binarized attendance sheet by
    finding the printed rule lines' *positions* via projection-profile peaks,
    rather than trying to recover each cell as its own contour.

    Contour-based cell finding is fragile on photographs: a rule that's
    faint, skewed by a fraction of a degree, or interrupted by a smudge
    breaks the enclosed-region assumption contour detection depends on, and
    either merges cells together or drops them. Projecting the horizontal
    and vertical line masks down to 1-D sums and finding the peaks in those
    sums is far more forgiving -- a rule only has to contribute *some*
    signal at roughly the right position, not form an unbroken enclosing
    shape. Row/column line positions are recovered independently and then
    crossed to build the cell grid directly, instead of discovering cells as
    connected regions.
    """

    def __init__(
        self,
        horizontal_kernel_scale: int = 25,
        vertical_kernel_scale: int = 40,
        horizontal_threshold_fraction: float = 0.25,
        vertical_threshold_fraction: float = 0.20,
        peak_group_distance: int = 10,
        min_cols: int = 4,
        storage: StorageManager | None = None,
        save_debug_images: bool = True,
    ) -> None:
        self.horizontal_kernel_scale = horizontal_kernel_scale
        self.vertical_kernel_scale = vertical_kernel_scale
        # Column rules are printed far fainter than row rules on these
        # sheets -- on a real sheet, a 0.20 threshold recovered all 6 column
        # boundaries while 0.30 found only 4, so the vertical threshold must
        # stay lower than the horizontal one.
        self.horizontal_threshold_fraction = horizontal_threshold_fraction
        self.vertical_threshold_fraction = vertical_threshold_fraction
        self.peak_group_distance = peak_group_distance
        self.min_cols = min_cols
        self.storage = storage or StorageManager()
        # "Enable this by default for now": debug saving is on unconditionally
        # until this has been proven against enough real sheets, so a bad
        # detection can be inspected without re-running anything.
        self.save_debug_images = save_debug_images

    def detect(self, binary_image: np.ndarray, session_id: str = "debug") -> list[list[Box]]:
        """Return rows[row][col] of (x, y, w, h) cell boxes, top-to-bottom and
        left-to-right. Rows whose column count doesn't match the modal column
        count across all detected rows are discarded as misdetections.

        `binary_image` is expected to follow the pipeline's BinarizeStep
        convention: printed lines/ink are dark (0) on a light (255)
        background.

        `session_id` names the debug-image subfolder under storage; neither
        current caller (app/api/routes/sheets.py, cli/sams.py) threads a real
        session id through to this method, so it defaults to a fixed
        "debug" folder that's always overwritten -- forward-compatible with
        a caller passing a real one later, functional today without needing
        either of those files changed.
        """
        height, width = binary_image.shape[:2]

        inverted = cv2.bitwise_not(binary_image)

        # 1. Horizontal mask: isolate long horizontal runs (row rules), then
        # dilate a little to bridge tiny gaps a printed rule leaves behind.
        horizontal_kernel_length = max(width // self.horizontal_kernel_scale, 1)
        horizontal_open_kernel = cv2.getStructuringElement(
            cv2.MORPH_RECT, (horizontal_kernel_length, 1)
        )
        horizontal_lines = cv2.morphologyEx(
            inverted, cv2.MORPH_OPEN, horizontal_open_kernel, iterations=1
        )
        horizontal_dilate_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 1))
        horizontal_lines = cv2.dilate(horizontal_lines, horizontal_dilate_kernel, iterations=1)

        # 2. Vertical mask: same idea for column rules.
        vertical_kernel_length = max(height // self.vertical_kernel_scale, 1)
        vertical_open_kernel = cv2.getStructuringElement(
            cv2.MORPH_RECT, (1, vertical_kernel_length)
        )
        vertical_lines = cv2.morphologyEx(
            inverted, cv2.MORPH_OPEN, vertical_open_kernel, iterations=1
        )
        vertical_dilate_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, 5))
        vertical_lines = cv2.dilate(vertical_lines, vertical_dilate_kernel, iterations=1)

        grid = cv2.add(horizontal_lines, vertical_lines)

        # 3. Project each mask down to a 1-D profile and find the printed
        # rules as peaks in it: row rules show up as peaks in the row-sum of
        # the horizontal mask, column rules as peaks in the column-sum of
        # the vertical mask.
        hp = horizontal_lines.sum(axis=1).astype(np.float64)
        vp = vertical_lines.sum(axis=0).astype(np.float64)

        ys = self._find_line_positions(hp, self.horizontal_threshold_fraction)
        xs = self._find_line_positions(vp, self.vertical_threshold_fraction)

        logger.info("GridDetector: detected ys (row lines) = %s", ys)
        logger.info("GridDetector: detected xs (column lines) = %s", xs)

        # 4. Cross the row and column line positions to build cells directly
        # from consecutive line pairs -- no contour search needed.
        rows: list[list[Box]] = []
        for i in range(len(ys) - 1):
            y = ys[i]
            h = ys[i + 1] - y
            row: list[Box] = [
                (xs[j], y, xs[j + 1] - xs[j], h) for j in range(len(xs) - 1)
            ]
            rows.append(row)

        rows = self._filter_by_column_count(rows)

        if self.save_debug_images:
            self._save_debug_images(
                session_id, horizontal_lines, vertical_lines, grid, binary_image, rows
            )

        return rows

    def _find_line_positions(self, projection: np.ndarray, threshold_fraction: float) -> list[int]:
        """Recover line positions from a 1-D projection profile: keep
        indices exceeding `threshold_fraction` of the profile's peak, then
        collapse consecutive indices within `peak_group_distance` pixels of
        each other into a single line position (their mean) -- a real
        printed rule lights up a whole band of indices, not just one.
        """
        max_val = projection.max() if projection.size else 0.0
        if max_val <= 0:
            return []

        threshold = threshold_fraction * max_val
        indices = np.flatnonzero(projection > threshold)
        if indices.size == 0:
            return []

        groups: list[list[int]] = []
        current = [int(indices[0])]
        for idx in indices[1:]:
            idx = int(idx)
            if idx - current[-1] <= self.peak_group_distance:
                current.append(idx)
            else:
                groups.append(current)
                current = [idx]
        groups.append(current)

        return [int(round(sum(group) / len(group))) for group in groups]

    def _filter_by_column_count(self, rows: list[list[Box]]) -> list[list[Box]]:
        candidates = [row for row in rows if len(row) >= self.min_cols]
        if not candidates:
            if rows:
                logger.warning(
                    "GridDetector: discarded all %d detected row(s); none had "
                    "at least min_cols=%d columns",
                    len(rows),
                    self.min_cols,
                )
            return []

        modal_count = Counter(len(row) for row in candidates).most_common(1)[0][0]
        filtered = [row for row in candidates if len(row) == modal_count]

        discarded = len(rows) - len(filtered)
        if discarded:
            logger.info(
                "GridDetector: discarded %d row(s) not matching the modal "
                "column count of %d",
                discarded,
                modal_count,
            )

        return filtered

    def _save_debug_images(
        self,
        session_id: str,
        horizontal_lines: np.ndarray,
        vertical_lines: np.ndarray,
        grid: np.ndarray,
        binary_image: np.ndarray,
        rows: list[list[Box]],
    ) -> None:
        try:
            directory = self.storage.root / "steps" / session_id
            directory.mkdir(parents=True, exist_ok=True)

            cv2.imwrite(str(directory / "06a_hlines.png"), horizontal_lines)
            cv2.imwrite(str(directory / "06b_vlines.png"), vertical_lines)
            cv2.imwrite(str(directory / "06c_grid.png"), grid)

            canvas = (
                cv2.cvtColor(binary_image, cv2.COLOR_GRAY2BGR)
                if binary_image.ndim == 2
                else binary_image.copy()
            )
            for row in rows:
                for x, y, w, h in row:
                    cv2.rectangle(canvas, (x, y), (x + w, y + h), (0, 255, 0), 2)
            cv2.imwrite(str(directory / "06d_cells.png"), canvas)
        except Exception:  # noqa: BLE001 - debug aid only, must never break detection
            logger.warning("GridDetector: failed to save debug images", exc_info=True)