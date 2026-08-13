import logging
import statistics
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
        boundary_strip_half_width: int = 3,
        boundary_presence_ratio: float = 0.5,
        header_rows: int = 1,
        header_height_diff_ratio: float = 0.25,
        header_ink_multiplier: float = 1.3,
        header_cv_threshold: float = 0.5,
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
        # Used by row validation: a global column boundary only counts as
        # real for a given row if a vertical rule is actually drawn within
        # that row's own y-band, sampled in a +/-3px strip around the
        # boundary's x position and requiring it to be set for at least 50%
        # of the row's height.
        self.boundary_strip_half_width = boundary_strip_half_width
        self.boundary_presence_ratio = boundary_presence_ratio
        self.header_rows = header_rows
        # Used by drop_header_rows to decide whether a header is actually
        # still present in the rows detect() returned: _validate_rows's run
        # selection already strips a header that forms its own separate run
        # (see _validate_rows), so this only fires when a header happens to
        # share its confirmed-boundary run with the data rows. Three signals
        # vote independently (header wins on 2-of-3) rather than any single
        # absolute ink level deciding it -- a fixed ink threshold calibrated
        # on one sheet doesn't hold up on sheets with heavier signatures.
        self.header_height_diff_ratio = header_height_diff_ratio
        self.header_ink_multiplier = header_ink_multiplier
        self.header_cv_threshold = header_cv_threshold
        self.min_cols = min_cols
        self.storage = storage or StorageManager()
        # "Enable this by default for now": debug saving is on unconditionally
        # until this has been proven against enough real sheets, so a bad
        # detection can be inspected without re-running anything.
        self.save_debug_images = save_debug_images
        # Cached by detect() so drop_header_rows -- called separately by
        # callers after detect() returns -- can compare header vs data ink
        # density without needing its signature changed to take the image.
        self._last_binary_image: np.ndarray | None = None

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
        self._last_binary_image = binary_image

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

        rows = self._validate_rows(rows, xs, vertical_lines)
        rows = self._filter_by_column_count(rows)

        if self.save_debug_images:
            self._save_debug_images(
                session_id, horizontal_lines, vertical_lines, grid, binary_image, rows
            )

        return rows

    def drop_header_rows(
        self, rows: list[list[Box]], expected_row_count: int | None = None
    ) -> list[list[Box]]:
        """Remove the sheet's leading header row(s) (column titles, etc.) --
        but only if one is actually still present. _validate_rows's run
        selection (see _validate_rows) already strips a header that forms
        its own separate confirmed-boundary run before detect() returns, so
        unconditionally slicing here would then cut the first real data row
        instead. A header only reaches this method when it happened to stay
        adjacent to the data rows and got selected as part of the same run.

        Decided by voting across three signals, dropping when at least two
        agree -- no single signal is trusted alone, because a fixed ink
        threshold calibrated on one sheet's handwriting doesn't generalize
        to sheets with heavier or lighter signatures:

        1. Row height: the header differs from the data rows' median height
           by more than `header_height_diff_ratio`.
        2. Cell-fill uniformity: every cell in a header row holds printed
           text, so per-cell ink ratios are all similarly non-trivial (low
           coefficient of variation); a data row's signature cell varies
           wildly against its other cells, including near-zero when unsigned
           (high coefficient of variation). This is scale-free -- it doesn't
           care how much ink is on the page, only how uneven it is within a
           row -- so it holds up regardless of how heavily a sheet's
           students sign.
        3. Relative ink: the header's mean ink ratio exceeds
           `header_ink_multiplier` times the *median* (not mean) of the data
           rows' per-row means, so one heavily-signed data row can't skew
           the comparison the header is judged against.

        If `expected_row_count` is given (the number of students listed in
        info.xml), a hard guard runs last: however the vote came out, if
        more rows survive than that count, leading rows are dropped until
        they match, since detect() must never hand back more rows than
        info.xml has students for.
        """
        logger.info(
            "GridDetector: rows before drop_header_rows (header_rows=%d) = %s",
            self.header_rows,
            [(row[0][1], row[0][1] + row[0][3]) for row in rows],
        )

        result = self._drop_header_by_vote(rows)
        result = self._enforce_expected_row_count(result, expected_row_count)

        logger.info(
            "GridDetector: rows after drop_header_rows = %s",
            [(row[0][1], row[0][1] + row[0][3]) for row in result],
        )
        return result

    def _drop_header_by_vote(self, rows: list[list[Box]]) -> list[list[Box]]:
        if len(rows) <= self.header_rows:
            logger.info(
                "GridDetector: drop_header_rows -- only %d row(s) available, "
                "nothing to compare against; keeping all rows",
                len(rows),
            )
            return rows

        header_candidates = rows[: self.header_rows]
        data_rows = rows[self.header_rows :]

        # Signal 1: row height vs the data rows' median.
        header_height = statistics.median(row[0][3] for row in header_candidates)
        data_height = statistics.median(row[0][3] for row in data_rows)
        height_diff_ratio = (
            abs(header_height - data_height) / data_height if data_height else 0.0
        )
        height_signal = height_diff_ratio > self.header_height_diff_ratio

        cv_signal = False
        ink_signal = False
        header_cv: float | None = None
        header_ink: float | None = None
        data_ink_median: float | None = None

        if self._last_binary_image is not None:
            image = self._last_binary_image

            header_row_ratios = [
                self._row_cell_ink_ratios(row, image) for row in header_candidates
            ]

            # Signal 2: per-row coefficient of variation across cells --
            # unitless, so it doesn't depend on how much ink is on the page
            # overall, only on how uneven it is within a single row.
            header_cvs = [
                self._coefficient_of_variation(ratios)
                for ratios in header_row_ratios
                if ratios
            ]
            header_cv = statistics.mean(header_cvs) if header_cvs else None
            cv_signal = header_cv is not None and header_cv < self.header_cv_threshold

            # Signal 3: header's mean ink vs the MEDIAN (not mean) of the
            # data rows' per-row means, so one heavily-signed data row can't
            # drag the comparison point up.
            header_row_means = [
                statistics.mean(ratios) for ratios in header_row_ratios if ratios
            ]
            header_ink = statistics.mean(header_row_means) if header_row_means else None

            data_row_means = [
                statistics.mean(ratios)
                for ratios in (
                    self._row_cell_ink_ratios(row, image) for row in data_rows
                )
                if ratios
            ]
            data_ink_median = (
                statistics.median(data_row_means) if data_row_means else None
            )

            ink_signal = (
                header_ink is not None
                and data_ink_median is not None
                and data_ink_median > 0
                and header_ink > data_ink_median * self.header_ink_multiplier
            )

        votes = sum([height_signal, cv_signal, ink_signal])
        drop = votes >= 2

        logger.info(
            "GridDetector: drop_header_rows signals -- "
            "height: diff_ratio=%.3f threshold=%.2f triggered=%s | "
            "cell-fill CV: value=%s threshold=%.2f triggered=%s | "
            "relative ink: header=%s data_median=%s multiplier=%.2f "
            "triggered=%s -- votes=%d/3 -> %s",
            height_diff_ratio,
            self.header_height_diff_ratio,
            height_signal,
            f"{header_cv:.3f}" if header_cv is not None else "unavailable",
            self.header_cv_threshold,
            cv_signal,
            f"{header_ink:.3f}" if header_ink is not None else "unavailable",
            f"{data_ink_median:.3f}" if data_ink_median is not None else "unavailable",
            self.header_ink_multiplier,
            ink_signal,
            votes,
            "DROP header" if drop else "KEEP all rows",
        )

        return data_rows if drop else rows

    def _enforce_expected_row_count(
        self, rows: list[list[Box]], expected_row_count: int | None
    ) -> list[list[Box]]:
        """Hard guard, applied after the vote: detect() must never hand back
        more rows than info.xml has students for. If the vote (or the
        absence of a header at all) still leaves too many, the excess is
        assumed to be leading rows -- a header the vote missed, or leftover
        table furniture -- and dropped from the top until the counts match.
        """
        if expected_row_count is None or len(rows) <= expected_row_count:
            return rows

        drop_count = len(rows) - expected_row_count
        logger.warning(
            "GridDetector: drop_header_rows fallback -- %d row(s) still "
            "exceed expected student count %d after voting; dropping %d "
            "more leading row(s)",
            len(rows),
            expected_row_count,
            drop_count,
        )
        return rows[drop_count:]

    @staticmethod
    def _row_cell_ink_ratios(row: list[Box], binary_image: np.ndarray) -> list[float]:
        """Fraction of dark (ink) pixels in each of the row's cells.
        `binary_image` follows the pipeline's BinarizeStep convention: ink
        is dark (0) on a light (255) background.
        """
        ratios: list[float] = []
        for x, y, w, h in row:
            cell = binary_image[y : y + h, x : x + w]
            if cell.size == 0:
                continue
            ink_pixels = int(np.count_nonzero(cell < 128))
            ratios.append(ink_pixels / cell.size)
        return ratios

    @staticmethod
    def _coefficient_of_variation(values: list[float]) -> float:
        """Std-dev / mean of `values` -- unitless, so it measures how UNEVEN
        the values are relative to each other regardless of their absolute
        scale. 0 for fewer than 2 values or an all-zero mean (nothing to
        compare).
        """
        if len(values) < 2:
            return 0.0
        mean = statistics.mean(values)
        if mean == 0:
            return 0.0
        return statistics.pstdev(values) / mean

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

    def _validate_rows(
        self, rows: list[list[Box]], xs: list[int], vertical_lines: np.ndarray
    ) -> list[list[Box]]:
        """Two tables of different width on the same page (e.g. a 5-column
        student table above a 3-column lecturer table) produce rows that all
        inherit the *same* column count, because cells are built by crossing
        one global xs/ys grid rather than being discovered per-row -- so the
        modal-column-count filter alone can no longer tell them apart.

        This checks, per row, which of the global column boundaries actually
        have a vertical rule drawn within that row's own y-band (rather than
        just being a boundary that happens to apply to some other row on the
        page), then keeps only the largest contiguous run of rows that agree
        on how many of those boundaries are real. A second, narrower table
        forms its own shorter run of rows with a different confirmed count
        and gets dropped.
        """
        total_detected = len(rows)
        height, width = vertical_lines.shape[:2]

        counted: list[tuple[list[Box], int]] = []
        for row_index, row in enumerate(rows):
            if not row:
                logger.info(
                    "GridDetector: row %d is empty, dropped by validation", row_index
                )
                continue
            y0 = row[0][1]
            y1 = y0 + row[0][3]
            band_height = y1 - y0
            if band_height <= 0:
                logger.info(
                    "GridDetector: row %d y-range (%d, %d) has non-positive "
                    "height, dropped by validation",
                    row_index,
                    y0,
                    y1,
                )
                continue

            confirmed = 0
            for x in xs:
                x_lo = max(x - self.boundary_strip_half_width, 0)
                x_hi = min(x + self.boundary_strip_half_width + 1, width)
                strip = vertical_lines[y0:y1, x_lo:x_hi]
                if strip.size == 0:
                    continue
                set_rows = int(np.count_nonzero(np.any(strip > 0, axis=1)))
                if set_rows / band_height >= self.boundary_presence_ratio:
                    confirmed += 1

            logger.info(
                "GridDetector: row %d y-range (%d, %d) confirmed-boundary "
                "count = %d",
                row_index,
                y0,
                y1,
                confirmed,
            )

            if confirmed >= self.min_cols:
                counted.append((row, confirmed))
            else:
                logger.info(
                    "GridDetector: row %d y-range (%d, %d) dropped by "
                    "validation -- confirmed-boundary count %d < min_cols=%d",
                    row_index,
                    y0,
                    y1,
                    confirmed,
                    self.min_cols,
                )

        if not counted:
            logger.warning(
                "GridDetector: %d row(s) detected, none survived boundary "
                "validation (min_cols=%d)",
                total_detected,
                self.min_cols,
            )
            return []

        # Largest contiguous run of GEOMETRICALLY adjacent rows: a run
        # continues as long as each row's top edge sits exactly on the
        # previous row's bottom edge, regardless of how their confirmed
        # counts compare -- a single row's count dropping by one (e.g. a
        # signature crossing a column rule) must not fracture an otherwise
        # unbroken table. Only an actual gap (a row rejected outright by the
        # min_cols floor above, and therefore absent from `counted`) breaks
        # a run.
        runs: list[list[list[Box]]] = [[counted[0][0]]]
        run_confirmed_counts: list[list[int]] = [[counted[0][1]]]
        for row, count in counted[1:]:
            prev_row = runs[-1][-1]
            prev_y1 = prev_row[0][1] + prev_row[0][3]
            row_y0 = row[0][1]
            if row_y0 == prev_y1:
                runs[-1].append(row)
                run_confirmed_counts[-1].append(count)
            else:
                runs.append([row])
                run_confirmed_counts.append([count])

        for run, counts in zip(runs, run_confirmed_counts):
            run_y_start = run[0][0][1]
            run_y_end = run[-1][0][1] + run[-1][0][3]
            logger.info(
                "GridDetector: run of %d row(s), confirmed-boundary counts "
                "= %s, y-range (%d, %d)",
                len(run),
                counts,
                run_y_start,
                run_y_end,
            )

        best_run = max(runs, key=len)

        for run, counts in zip(runs, run_confirmed_counts):
            if run is best_run:
                continue
            run_y_start = run[0][0][1]
            run_y_end = run[-1][0][1] + run[-1][0][3]
            logger.info(
                "GridDetector: dropped run of %d row(s) (confirmed-boundary "
                "counts = %s, y-range (%d, %d)) -- not the largest "
                "contiguous run",
                len(run),
                counts,
                run_y_start,
                run_y_end,
            )

        y_start = best_run[0][0][1]
        y_end = best_run[-1][0][1] + best_run[-1][0][3]
        logger.info(
            "GridDetector: %d row(s) detected, %d survived validation "
            "(y-range %d to %d)",
            total_detected,
            len(best_run),
            y_start,
            y_end,
        )

        return best_run

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