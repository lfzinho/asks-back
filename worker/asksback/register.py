"""Align a student photo onto the blank master page it came from.

No markers are printed on the paper, so alignment uses the printed content
itself: SIFT features on the master and the photo, matched with a ratio test,
then a RANSAC homography. The master with the most inliers is the page number.
An ECC pass then refines the alignment to sub-pixel level.
"""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

from .images import normalize_illumination, resize_max, to_gray

WORK_SIDE = 1600  # feature matching resolution
MIN_INLIERS = 40


@dataclass
class _Features:
    keypoints: np.ndarray  # Nx2 in work-resolution pixels
    descriptors: np.ndarray
    scale: float  # work / full
    shape: tuple[int, int]  # full-res (h, w)
    work_gray: np.ndarray


@dataclass
class Registration:
    page: int  # 1-based
    homography: np.ndarray  # maps full-res student pixels to full-res master pixels
    inliers: int
    runner_up_inliers: int
    ecc_refined: bool
    aligned: np.ndarray  # student image warped into the master frame (BGR)


class Registrar:
    def __init__(self, masters: list[np.ndarray]):
        self._sift = cv2.SIFT_create(nfeatures=6000)
        self._matcher = cv2.FlannBasedMatcher({"algorithm": 1, "trees": 5}, {"checks": 64})
        self.masters = masters
        self._master_feats = [self._features(m) for m in masters]

    def _features(self, img: np.ndarray) -> _Features:
        small, s = resize_max(img, WORK_SIDE)
        gray = normalize_illumination(to_gray(small))
        kps, desc = self._sift.detectAndCompute(gray, None)
        pts = np.float32([k.pt for k in kps]) if kps else np.zeros((0, 2), np.float32)
        return _Features(pts, desc, s, img.shape[:2], gray)

    def _match(self, a: _Features, b: _Features) -> tuple[np.ndarray | None, int]:
        """Homography from a (work res) to b (work res) and its inlier count."""
        if a.descriptors is None or b.descriptors is None or len(a.keypoints) < 8 or len(b.keypoints) < 8:
            return None, 0
        pairs = self._matcher.knnMatch(a.descriptors, b.descriptors, k=2)
        good = [m for m, n in (p for p in pairs if len(p) == 2) if m.distance < 0.75 * n.distance]
        if len(good) < 8:
            return None, 0
        src = a.keypoints[[m.queryIdx for m in good]]
        dst = b.keypoints[[m.trainIdx for m in good]]
        H, mask = cv2.findHomography(src, dst, cv2.RANSAC, 4.0, maxIters=5000, confidence=0.999)
        if H is None:
            return None, 0
        return H, int(mask.sum())

    def register(self, student: np.ndarray) -> Registration | None:
        sf = self._features(student)
        scored = []
        for i, mf in enumerate(self._master_feats):
            H, n = self._match(sf, mf)
            scored.append((n, i, H))
        scored.sort(key=lambda t: t[0], reverse=True)
        inliers, idx, H_small = scored[0]
        runner_up = scored[1][0] if len(scored) > 1 else 0
        if H_small is None or inliers < MIN_INLIERS:
            return None
        mf = self._master_feats[idx]

        # Lift the work-resolution homography to full resolution.
        S_s = np.diag([sf.scale, sf.scale, 1.0])
        S_m = np.diag([mf.scale, mf.scale, 1.0])
        H = np.linalg.inv(S_m) @ H_small @ S_s
        H, refined = self._refine_ecc(student, H, mf)

        master = self.masters[idx]
        aligned = cv2.warpPerspective(
            student, H, (master.shape[1], master.shape[0]),
            flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=(255, 255, 255),
        )
        return Registration(idx + 1, H, inliers, runner_up, refined, aligned)

    def _refine_ecc(self, student: np.ndarray, H: np.ndarray, mf: _Features) -> tuple[np.ndarray, bool]:
        """Polish H with ECC at work resolution. Keeps H unchanged if ECC fails or wanders off."""
        s = mf.scale
        S = np.diag([s, s, 1.0])
        h, w = mf.work_gray.shape
        warped = cv2.warpPerspective(
            normalize_illumination(to_gray(student)), S @ H, (w, h),
            borderMode=cv2.BORDER_CONSTANT, borderValue=255,
        )
        W = np.eye(3, dtype=np.float32)
        try:
            _, W = cv2.findTransformECC(
                mf.work_gray.astype(np.float32), warped.astype(np.float32), W, cv2.MOTION_HOMOGRAPHY,
                (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 60, 1e-5), None, 5,
            )
        except cv2.error:
            return H, False
        # Reject large corrections: the feature homography is already close.
        corners = np.float32([[0, 0], [w, 0], [w, h], [0, h]]).reshape(-1, 1, 2)
        moved = cv2.perspectiveTransform(corners, W.astype(np.float64))
        if np.abs(moved - corners).max() > 0.02 * max(w, h):
            return H, False
        # warped(x) = student(H^-1 S^-1 x); ECC gives refined(x) = warped(W x).
        W_full = np.linalg.inv(S) @ W.astype(np.float64) @ S
        return np.linalg.inv(W_full) @ H, True
