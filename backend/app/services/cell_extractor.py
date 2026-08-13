import logging

import cv2
import numpy as np

from app.core.storage import StorageManager
from app.models.schemas import Student

Box = tuple[int, int, int, int]

logger = logging.getLogger(__name__)


class CellExtractor:
    """Crops a single column (typically the signature column) out of the
    deskew-aligned color frame, using the cell grid found by GridDetector.
    """

    def __init__(
        self,
        session_id: str,
        storage: StorageManager | None = None,
        horizontal_shrink_ratio: float = 0.06,
        vertical_shrink_ratio: float = 0.04,
        vertical_expansion_ratio: float = 0.15,
        presence_horizontal_shrink_ratio: float = 0.10,
        presence_vertical_shrink_ratio: float = 0.10,
        signature_col: int = -1,
        save_debug_images: bool = True,
    ) -> None:
        self.session_id = session_id
        self.storage = storage or StorageManager()
        # "Enable this by default for now", mirroring GridDetector: crops
        # spanning a row boundary have been reported on real sheets, so the
        # 07a_crop_regions.png overlay stays on until that's been root-caused
        # and fixed, not opt-in.
        self.save_debug_images = save_debug_images
        # GENEROUS crop -- signature matching / the review queue -- saved to
        # disk as NN_signature_col{col}.png. Kept deliberately small:
        # signatures routinely overflow their cell, so trimming too
        # aggressively (this used to be a single 5% shrink on every side)
        # cuts off the strokes signature comparison actually needs.
        self.horizontal_shrink_ratio = horizontal_shrink_ratio
        self.vertical_shrink_ratio = vertical_shrink_ratio
        # Ascenders/descenders routinely cross the printed row rule into
        # the neighbouring row, so the vertical crop is allowed to extend
        # past the row's own boundary by this fraction (of the row's own
        # height) above and below, independent of -- and applied after --
        # the inward vertical_shrink_ratio trim above. Clamped to the
        # image's own bounds in extract_signature_cells.
        self.vertical_expansion_ratio = vertical_expansion_ratio
        # TIGHT crop -- PresenceDetector only, never written to disk. Shrunk
        # inward on every side and never expanded past the row's own
        # boundary, unlike the generous crop above: PresenceDetector's
        # ink_ratio/largest-component check treats the printed row rule
        # (dark, near-full-width) the same as a real signature stroke, so
        # this crop must stay clear of it entirely rather than relying on
        # PresenceDetector to filter it out after the fact. 10% was chosen
        # to clear the rule with margin on every real sheet measured so far
        # without eating into a genuine signature's ink.
        self.presence_horizontal_shrink_ratio = presence_horizontal_shrink_ratio
        self.presence_vertical_shrink_ratio = presence_vertical_shrink_ratio
        self.signature_col = signature_col

    @staticmethod
    def validate_alignment(rows: list[list[Box]], students: list[Student]) -> None:
        """Raise before extraction if the detected row count and the parsed
        student count disagree. Silently zipping mismatched lists would map
        student N's row to student N+1 (or silently drop trailing students)
        with no indication anything went wrong.
        """
        if len(rows) != len(students):
            raise ValueError(
                f"Row/student count mismatch: detected {len(rows)} table "
                f"row(s) but info.xml lists {len(students)} student(s)"
            )

    def extract_signature_cells(
        self,
        color_aligned: np.ndarray,
        rows: list[list[Box]],
    ) -> tuple[list[np.ndarray], list[np.ndarray]]:
        """Crop the signature column out of each row, producing TWO separate
        crops per row for two consumers with opposite requirements:

        - The GENEROUS crop (`horizontal_shrink_ratio`/`vertical_shrink_ratio`
          shrunk inward, then `vertical_expansion_ratio` expanded back out
          past the row's own top/bottom) is written to disk as
          NN_signature_col{col}.png and returned as the first list. This is
          what SignatureMatcher and the review queue use -- signatures
          routinely overflow their cell, both sideways and via ascenders/
          descenders crossing the printed row rule, so this crop
          deliberately reaches past the row's own boundary to avoid slicing
          off a stroke.
        - The TIGHT crop (`presence_horizontal_shrink_ratio`/
          `presence_vertical_shrink_ratio` shrunk inward, never expanded) is
          written to disk as NN_presence_col{col}.png (so it can be
          inspected independently of the generous crop) and returned as the
          second list. This is what PresenceDetector must measure: the
          generous crop's deliberate overshoot pulls the neighbouring row's
          printed rule into frame, and that rule -- dark, near-full-width --
          clears PresenceDetector's ink_ratio and largest-component
          thresholds on its own, marking an empty cell present. The tight
          crop stays inside the row's own boundary on every side so the
          rule can never appear in it.

        `color_aligned` must be the same deskew-aligned color frame the grid
        boxes were detected from (Pipeline.run's context["color_aligned"]) --
        cropping from any other frame will not line up with the ink.

        Returns (signature_crops, presence_crops), both in row order.
        """
        image_height, image_width = color_aligned.shape[:2]
        signature_crops: list[np.ndarray] = []
        presence_crops: list[np.ndarray] = []
        crop_regions: list[tuple[int, Box, Box]] = []

        # Rows are built by GridDetector by crossing consecutive entries of
        # its own detected `ys` (row rule positions): row i's own box starts
        # at ys[i] and is ys[i+1] - ys[i] tall, identically for every column
        # in that row. Reconstructing ys here -- rather than threading it
        # through from GridDetector -- means this diagnostic reflects the
        # exact row boundaries these particular crops were cut against,
        # after header-dropping/validation/column-count filtering have all
        # already run.
        ys = [row[0][1] for row in rows if row] + (
            [rows[-1][0][1] + rows[-1][0][3]] if rows and rows[-1] else []
        )
        logger.info("CellExtractor: ys (row line positions) = %s", ys)

        for row_index, row in enumerate(rows):
            if not (-len(row) <= self.signature_col < len(row)):
                continue
            col_index = self.signature_col % len(row)

            x, y, w, h = row[col_index]

            # GENEROUS crop: signature matching / review queue.
            shrink_x = int(round(w * self.horizontal_shrink_ratio))
            shrink_y = int(round(h * self.vertical_shrink_ratio))
            expand_y = int(round(h * self.vertical_expansion_ratio))
            sig_x1 = max(x + shrink_x, 0)
            sig_x2 = min(x + w - shrink_x, image_width)
            sig_y1 = max(y + shrink_y - expand_y, 0)
            sig_y2 = min(y + h - shrink_y + expand_y, image_height)

            # TIGHT crop: presence detection only. Inward on every side,
            # never expanded, so it cannot reach the printed row rule.
            pres_shrink_x = int(round(w * self.presence_horizontal_shrink_ratio))
            pres_shrink_y = int(round(h * self.presence_vertical_shrink_ratio))
            pres_x1 = max(x + pres_shrink_x, 0)
            pres_x2 = min(x + w - pres_shrink_x, image_width)
            pres_y1 = max(y + pres_shrink_y, 0)
            pres_y2 = min(y + h - pres_shrink_y, image_height)

            logger.info(
                "CellExtractor: row %d cell_bbox=(x=%d, y=%d, x2=%d, y2=%d) "
                "signature_crop_bbox=(x=%d, y=%d, x2=%d, y2=%d) "
                "presence_crop_bbox=(x=%d, y=%d, x2=%d, y2=%d)",
                row_index,
                x,
                y,
                x + w,
                y + h,
                sig_x1,
                sig_y1,
                sig_x2,
                sig_y2,
                pres_x1,
                pres_y1,
                pres_x2,
                pres_y2,
            )

            signature_crop = color_aligned[sig_y1:sig_y2, sig_x1:sig_x2]
            presence_crop = color_aligned[pres_y1:pres_y2, pres_x1:pres_x2]
            signature_crops.append(signature_crop)
            presence_crops.append(presence_crop)
            crop_regions.append(
                (row_index, (sig_x1, sig_y1, sig_x2, sig_y2), (pres_x1, pres_y1, pres_x2, pres_y2))
            )

            path = self.storage.step_path(
                self.session_id, row_index, f"signature_col{col_index}.png"
            )
            cv2.imwrite(path, signature_crop)

            presence_path = self.storage.step_path(
                self.session_id, row_index, f"presence_col{col_index}.png"
            )
            cv2.imwrite(presence_path, presence_crop)

        if self.save_debug_images:
            self._save_crop_region_debug_image(color_aligned, crop_regions)

        return signature_crops, presence_crops

    def _save_crop_region_debug_image(
        self,
        color_aligned: np.ndarray,
        crop_regions: list[tuple[int, Box, Box]],
    ) -> None:
        """Diagnostic for crops that straddle a row boundary, and for
        confirming the presence-detection fix: draws every committed
        GENEROUS signature-matching crop rectangle in green, and its paired
        TIGHT presence-detection crop in blue, over a copy of the same
        deskew-aligned colour frame the crops themselves came from, labelled
        with its row index. Because the printed rule lines are still visible
        in this colour frame: a green box visibly enclosing a rule line
        through its middle points at the row's own boundary being misplaced
        or the expansion ratio being too generous; the blue box should never
        enclose one -- if it does, `presence_*_shrink_ratio` isn't tight
        enough. Does not change any crop geometry -- overlay only.
        """
        try:
            directory = self.storage.root / "steps" / self.session_id
            directory.mkdir(parents=True, exist_ok=True)

            canvas = color_aligned.copy()
            for row_index, (sx1, sy1, sx2, sy2), (px1, py1, px2, py2) in crop_regions:
                cv2.rectangle(canvas, (sx1, sy1), (sx2, sy2), (0, 255, 0), 2)
                cv2.rectangle(canvas, (px1, py1), (px2, py2), (255, 0, 0), 2)
                cv2.putText(
                    canvas,
                    str(row_index),
                    (sx1, max(sy1 - 6, 12)),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.5,
                    (0, 255, 0),
                    1,
                    cv2.LINE_AA,
                )
            cv2.imwrite(str(directory / "07a_crop_regions.png"), canvas)
        except Exception:  # noqa: BLE001 - debug aid only, must never break extraction
            logger.warning("CellExtractor: failed to save crop region debug image", exc_info=True)
