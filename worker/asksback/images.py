"""Image helpers shared by the pipeline stages."""

from __future__ import annotations

import base64
from pathlib import Path

import cv2
import numpy as np

from .exam import Box

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp", ".webp"}


def load_image(path: Path) -> np.ndarray:
    """Load as BGR. cv2.imread applies EXIF orientation, which matters for phone photos."""
    img = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError(f"cannot read image {path}")
    return img


def list_images(folder: Path) -> list[Path]:
    return sorted(p for p in folder.iterdir() if p.suffix.lower() in IMAGE_SUFFIXES)


def to_gray(img: np.ndarray) -> np.ndarray:
    return img if img.ndim == 2 else cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)


def normalize_illumination(gray: np.ndarray) -> np.ndarray:
    """Flatten shadows and lighting gradients so paper is ~255 everywhere.

    The paper background is estimated with a max filter (removes thin dark ink)
    followed by a median blur, then the image is divided by it.
    """
    k = max(15, (min(gray.shape) // 60) | 1)
    bg = cv2.dilate(gray, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k)))
    bg = cv2.medianBlur(bg, k if k <= 255 else 255)
    return cv2.divide(gray, bg, scale=255)


def resize_max(img: np.ndarray, max_side: int) -> tuple[np.ndarray, float]:
    """Downscale so the longest side is <= max_side. Returns (image, scale)."""
    s = min(1.0, max_side / max(img.shape[:2]))
    if s == 1.0:
        return img, 1.0
    return cv2.resize(img, None, fx=s, fy=s, interpolation=cv2.INTER_AREA), s


def crop(img: np.ndarray, box: Box, pad: int = 0) -> np.ndarray:
    x, y, w, h = box
    H, W = img.shape[:2]
    x0, y0 = max(0, x - pad), max(0, y - pad)
    x1, y1 = min(W, x + w + pad), min(H, y + h + pad)
    return img[y0:y1, x0:x1]


def png_b64(img: np.ndarray) -> str:
    ok, buf = cv2.imencode(".png", img)
    if not ok:
        raise ValueError("png encode failed")
    return base64.standard_b64encode(buf.tobytes()).decode("ascii")
