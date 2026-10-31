"""Isolate the student's handwriting and split it into numbered boxes.

ink = (dark or colored pixels on the aligned student page)
      minus (everything printed on the blank master, slightly dilated).
The boxes are what the grader refers to by number, so error highlights come
from these exact pixel coordinates and never from the model.
"""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

from .exam import Box
from .images import normalize_illumination, to_gray

DARK_THRESHOLD = 185  # on illumination-normalized gray, paper is ~255
MASTER_THRESHOLD = 215
MAX_BOXES = 60  # above this, fall back to line-level boxes


@dataclass
class InkBox:
    id: int
    box: Box  # in the coordinates of the image it was computed on
    line: int


def _printed_mask(master: np.ndarray) -> np.ndarray:
    g = normalize_illumination(to_gray(master))
    mask = (g < MASTER_THRESHOLD).astype(np.uint8)
    k = max(3, round(0.0025 * max(master.shape[:2])))
    return cv2.dilate(mask, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k)))


def _colored(img: np.ndarray) -> np.ndarray:
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    return (hsv[..., 1] > 70) & (hsv[..., 2] < 235)


def ink_mask(aligned: np.ndarray, master: np.ndarray) -> np.ndarray:
    """uint8 mask (0/255) of handwriting on the aligned student page."""
    g = normalize_illumination(to_gray(aligned))
    student = (g < DARK_THRESHOLD) | _colored(aligned)
    printed = _printed_mask(master).astype(bool) | _colored(master)
    ink = (student & ~printed).astype(np.uint8) * 255
    # Removing printed lines also cuts the handwriting that crosses them. Bridge those
    # cuts across the line (not along it), only inside printed areas.
    k = 2 * max(3, round(0.0025 * max(master.shape[:2]))) + 1
    bridged = (cv2.morphologyEx(ink, cv2.MORPH_CLOSE, np.ones((k, 1), np.uint8))
               | cv2.morphologyEx(ink, cv2.MORPH_CLOSE, np.ones((1, k), np.uint8)))
    ink = np.where(printed & (bridged > 0), 255, ink).astype(np.uint8)
    ink = cv2.morphologyEx(ink, cv2.MORPH_OPEN, np.ones((2, 2), np.uint8))
    # Drop specks smaller than a pen dot.
    min_area = max(6, int(2e-6 * ink.size))
    n, labels, stats, _ = cv2.connectedComponentsWithStats(ink, connectivity=8)
    keep = np.zeros(n, bool)
    keep[1:] = stats[1:, cv2.CC_STAT_AREA] >= min_area
    return np.where(keep[labels], 255, 0).astype(np.uint8)


def _components(mask: np.ndarray) -> list[Box]:
    n, _, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    return [tuple(int(v) for v in stats[i, :4]) for i in range(1, n)]


def _union(boxes: list[Box]) -> Box:
    x0 = min(b[0] for b in boxes)
    y0 = min(b[1] for b in boxes)
    x1 = max(b[0] + b[2] for b in boxes)
    y1 = max(b[1] + b[3] for b in boxes)
    return (x0, y0, x1 - x0, y1 - y0)


def _group_lines(boxes: list[Box], letter_h: float) -> list[list[Box]]:
    """Group pieces of ink into text lines, top to bottom, each sorted left to right.

    Letter-sized pieces seed the lines; small pieces (dots, dashes, stroke fragments)
    then join the line they sit in, or the nearest one.
    """
    lines: list[list[Box]] = []
    spans: list[list[float]] = []
    for b in sorted(boxes, key=lambda b: -b[3]):
        cy = b[1] + b[3] / 2
        hit = next((i for i, (y0, y1) in enumerate(spans) if y0 <= cy <= y1), None)
        if hit is None and b[3] < 0.5 * letter_h and spans:
            dist = [min(abs(cy - y0), abs(cy - y1)) / max(letter_h, y1 - y0) for y0, y1 in spans]
            if min(dist) <= 1.0:
                hit = int(np.argmin(dist))
        if hit is None:
            lines.append([b])
            spans.append([b[1], b[1] + b[3]])
        else:
            lines[hit].append(b)
            spans[hit] = [min(spans[hit][0], b[1]), max(spans[hit][1], b[1] + b[3])]
    for line in lines:
        line.sort(key=lambda b: b[0])
    lines.sort(key=lambda line: min(b[1] for b in line))
    return lines


def _split_words(line: list[Box], gap: float) -> list[Box]:
    """Merge horizontally consecutive pieces closer than `gap` into words."""
    words = [[line[0]]]
    right = line[0][0] + line[0][2]
    for b in line[1:]:
        if b[0] - right > gap:
            words.append([b])
        else:
            words[-1].append(b)
        right = max(right, b[0] + b[2])
    return [_union(w) for w in words]


def _merge_stacked(boxes: list[Box], letter_h: float) -> list[Box]:
    """Rejoin pieces of one symbol split horizontally (a stroke that ran along a printed
    line is lost with it): boxes that overlap in x, are separated by a tiny vertical gap,
    and together are no taller than one letter (so two touching lines stay apart)."""
    boxes = list(boxes)
    merged = True
    while merged:
        merged = False
        for i in range(len(boxes)):
            for j in range(i + 1, len(boxes)):
                a, b = boxes[i], boxes[j]
                overlap = min(a[0] + a[2], b[0] + b[2]) - max(a[0], b[0])
                gap = max(a[1], b[1]) - min(a[1] + a[3], b[1] + b[3])
                height = max(a[1] + a[3], b[1] + b[3]) - min(a[1], b[1])
                if overlap >= 0.5 * min(a[2], b[2]) and gap <= 0.3 * letter_h and height <= 1.3 * letter_h:
                    boxes[i] = _union([a, b])
                    del boxes[j]
                    merged = True
                    break
            if merged:
                break
    return boxes


def word_boxes(mask: np.ndarray) -> list[InkBox]:
    """Word-sized boxes over the handwriting in `mask`, numbered in reading order."""
    comps = [b for b in _components(mask) if b[2] * b[3] >= 20]
    if not comps:
        return []
    # Letter height: upper quartile, since dots, dashes and broken strokes pull the median down.
    letter_h = float(np.percentile([b[3] for b in comps], 75))
    comps = _merge_stacked(comps, letter_h)
    lines = []
    for line in _group_lines(comps, letter_h):
        line_h = float(np.percentile([b[3] for b in line], 75))
        lines.append(_split_words(line, 0.45 * min(line_h, letter_h)))
    if sum(len(line) for line in lines) > MAX_BOXES:
        lines = [[_union(line)] for line in lines]
    out: list[InkBox] = []
    for li, line in enumerate(lines, start=1):
        for b in line:
            out.append(InkBox(len(out) + 1, b, li))
    return out


def ink_fraction(mask: np.ndarray, box: Box, shrink: float = 0.0) -> float:
    x, y, w, h = box
    dx, dy = int(w * shrink), int(h * shrink)
    sub = mask[y + dy : y + h - dy, x + dx : x + w - dx]
    return float((sub > 0).mean()) if sub.size else 0.0
