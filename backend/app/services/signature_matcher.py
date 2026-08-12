import logging

import cv2
import numpy as np

logger = logging.getLogger(__name__)


class SignatureMatcher:
    """Compares two signature-cell crops.

    Two independent scores are computed for every comparison: ORB keypoint
    matching, and a coarser structural comparison (Hu moments plus ink
    density/aspect ratio). ORB is only *eligible* to win when both crops
    clear `min_matches` keypoints -- below that, its ratio (good matches /
    smaller keypoint set) is measured on too little signal to mean
    anything -- but clearing that floor is not the same as ORB actually
    matching well: a thin, sparse pen stroke can hand ORB plenty of
    keypoints (each one just an endpoint or bend in the curve) while the
    ratio test still rejects nearly all of them as ambiguous, since a
    binarized stroke's local neighborhoods are self-similar in a way real
    photographs aren't. When that happens, ORB's own numeric result is
    simply low, not invalid, so the higher of the two scores wins rather
    than ORB winning by default whenever it was eligible to run at all.

    This is a lightweight heuristic meant to flag candidates for a human
    to look at -- not a forensic or legally authoritative signature
    verification.
    """

    CANVAS_WIDTH = 200
    CANVAS_HEIGHT = 100

    def __init__(
        self,
        nfeatures: int = 500,
        ratio: float = 0.75,
        min_matches: int = 10,
        saturation_threshold: int = 40,
        dark_value_threshold: int = 90,
        similarity_threshold: float = 0.6,
    ) -> None:
        self.nfeatures = nfeatures
        self.ratio = ratio
        self.min_matches = min_matches
        self.saturation_threshold = saturation_threshold
        self.dark_value_threshold = dark_value_threshold
        self.similarity_threshold = similarity_threshold
        self._orb = cv2.ORB_create(nfeatures=self.nfeatures)
        self._matcher = cv2.BFMatcher(cv2.NORM_HAMMING)

    def _ink_mask(self, cell_bgr: np.ndarray) -> np.ndarray:
        """Same HSV-saturation + dark-pixel ink isolation as PresenceDetector."""
        hsv = cv2.cvtColor(cell_bgr, cv2.COLOR_BGR2HSV)
        saturation = hsv[:, :, 1]
        value = hsv[:, :, 2]
        colored_ink_mask = saturation >= self.saturation_threshold
        dark_ink_mask = value <= self.dark_value_threshold
        return np.where(colored_ink_mask | dark_ink_mask, 255, 0).astype(np.uint8)

    def preprocess(self, cell_bgr: np.ndarray) -> np.ndarray:
        """Isolate ink, crop to its bounding box, deskew and normalize onto a
        fixed canvas. ORB is not scale/translation invariant enough on its
        own to compare raw crops of differing offset and size, so
        normalizing geometry first is essential.
        """
        mask = self._ink_mask(cell_bgr)
        canvas = np.zeros((self.CANVAS_HEIGHT, self.CANVAS_WIDTH), dtype=np.uint8)

        ys, xs = np.nonzero(mask)
        if xs.size == 0:
            return canvas

        x1, x2 = xs.min(), xs.max() + 1
        y1, y2 = ys.min(), ys.max() + 1
        cropped = mask[y1:y2, x1:x2]

        points = cv2.findNonZero(cropped)
        rect = cv2.minAreaRect(points)
        angle = rect[-1]
        # OpenCV's minAreaRect angle convention jumps between -90..0
        # depending on box orientation; normalize to a small correction
        # rather than rotating the stroke onto its side.
        if angle < -45:
            angle += 90

        h, w = cropped.shape
        rotation = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
        deskewed = cv2.warpAffine(cropped, rotation, (w, h), flags=cv2.INTER_NEAREST, borderValue=0)

        ys2, xs2 = np.nonzero(deskewed)
        if xs2.size == 0:
            return canvas
        x1b, x2b = xs2.min(), xs2.max() + 1
        y1b, y2b = ys2.min(), ys2.max() + 1
        tight = deskewed[y1b:y2b, x1b:x2b]

        tight_h, tight_w = tight.shape
        scale = min(self.CANVAS_WIDTH / tight_w, self.CANVAS_HEIGHT / tight_h)
        new_w = max(1, int(round(tight_w * scale)))
        new_h = max(1, int(round(tight_h * scale)))
        resized = cv2.resize(tight, (new_w, new_h), interpolation=cv2.INTER_NEAREST)

        x_off = (self.CANVAS_WIDTH - new_w) // 2
        y_off = (self.CANVAS_HEIGHT - new_h) // 2
        canvas[y_off : y_off + new_h, x_off : x_off + new_w] = resized

        _, binarized = cv2.threshold(canvas, 0, 255, cv2.THRESH_BINARY)
        return binarized

    def descriptors(self, image: np.ndarray) -> tuple[list | None, np.ndarray | None]:
        keypoints, desc = self._orb.detectAndCompute(image, None)
        if desc is None or len(keypoints) < 2:
            return None, None
        return keypoints, desc

    def compare(self, img_a: np.ndarray, img_b: np.ndarray) -> dict:
        kp_a, desc_a = self.descriptors(img_a)
        kp_b, desc_b = self.descriptors(img_b)

        if desc_a is None or desc_b is None:
            return {"orb_score": 0.0, "match_count": 0, "sufficient_keypoints": False}

        matches = self._matcher.knnMatch(desc_a, desc_b, k=2)
        good = []
        for pair in matches:
            if len(pair) < 2:
                continue
            m, n = pair
            if m.distance < self.ratio * n.distance:
                good.append(m)

        smaller_set = min(len(kp_a), len(kp_b))
        orb_score = min(len(good) / smaller_set, 1.0) if smaller_set else 0.0
        sufficient = len(kp_a) >= self.min_matches and len(kp_b) >= self.min_matches

        return {
            "orb_score": orb_score,
            "match_count": len(good),
            "sufficient_keypoints": sufficient,
        }

    def structural_score(self, img_a: np.ndarray, img_b: np.ndarray) -> float:
        """Coarse shape comparison, always computed by similarity() alongside
        the ORB score: Hu-moment shape distance blended with ink-density and
        aspect-ratio agreement.
        """

        def features(image: np.ndarray) -> tuple[np.ndarray, float, float]:
            hu = cv2.HuMoments(cv2.moments(image)).flatten()
            # Hu moments span many orders of magnitude raw; log-scale them
            # so no single moment dominates the L2 distance below.
            hu = -np.sign(hu) * np.log10(np.abs(hu) + 1e-30)
            ys, xs = np.nonzero(image)
            density = float(np.count_nonzero(image)) / image.size
            aspect = (xs.max() - xs.min() + 1) / (ys.max() - ys.min() + 1) if xs.size else 0.0
            return hu, density, aspect

        hu_a, density_a, aspect_a = features(img_a)
        hu_b, density_b, aspect_b = features(img_b)

        hu_distance = float(np.linalg.norm(hu_a - hu_b))
        hu_score = 1.0 / (1.0 + hu_distance)

        density_score = 1.0 - min(abs(density_a - density_b) / max(density_a, density_b, 1e-6), 1.0)
        aspect_score = 1.0 - min(abs(aspect_a - aspect_b) / max(aspect_a, aspect_b, 1e-6), 1.0)

        return float(np.clip(0.5 * hu_score + 0.25 * density_score + 0.25 * aspect_score, 0.0, 1.0))

    def similarity(self, img_a: np.ndarray, img_b: np.ndarray) -> tuple[float, str]:
        """Compute both scores and pick the higher one, rather than trusting
        ORB by default whenever it was merely eligible to run. The
        structural score is always computed; the ORB score only competes
        when `sufficient_keypoints` says both crops had enough keypoints for
        its ratio to be meaningful at all -- but among comparisons that
        clear that floor, ORB still frequently loses (see class docstring),
        so its eligibility is necessary, not sufficient, for it to be
        chosen.
        """
        result = self.compare(img_a, img_b)
        structural = self.structural_score(img_a, img_b)

        if result["sufficient_keypoints"] and result["orb_score"] >= structural:
            score, method = result["orb_score"], "orb"
        else:
            score, method = structural, "structural"

        logger.info(
            "SignatureMatcher: orb_score=%.4f (sufficient_keypoints=%s, match_count=%d) "
            "structural_score=%.4f -> chosen=%s score=%.4f",
            result["orb_score"],
            result["sufficient_keypoints"],
            result["match_count"],
            structural,
            method,
            score,
        )

        return score, method

    def verify(self, candidate_bgr: np.ndarray, reference_bgrs: list[np.ndarray]) -> dict:
        candidate = self.preprocess(candidate_bgr)

        scores: list[float] = []
        methods: list[str] = []
        for reference_bgr in reference_bgrs:
            reference = self.preprocess(reference_bgr)
            score, method = self.similarity(candidate, reference)
            scores.append(score)
            methods.append(method)

        if not scores:
            return {
                "score": 0.0,
                "mean_score": 0.0,
                "method": "none",
                "reference_count": 0,
                "flagged": True,
            }

        best_index = int(np.argmax(scores))
        best_score = scores[best_index]
        return {
            "score": best_score,
            "mean_score": float(np.mean(scores)),
            "method": methods[best_index],
            "reference_count": len(reference_bgrs),
            "flagged": best_score < self.similarity_threshold,
        }
