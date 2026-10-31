"""Multiple choice by optical mark recognition: no AI involved."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np

from .exam import Box
from .ink import ink_fraction

MIN_FILL = 0.04  # share of an option box covered by student ink to count as marked
RIVAL_RATIO = 0.5  # a second option this close to the top one makes the answer ambiguous


@dataclass
class MCQReading:
    selected: str | None
    status: Literal["ok", "blank", "multiple"]
    fills: dict[str, float]


def read_mcq(ink: np.ndarray, options: dict[str, Box]) -> MCQReading:
    fills = {k: ink_fraction(ink, box) for k, box in options.items()}
    ranked = sorted(fills.items(), key=lambda kv: kv[1], reverse=True)
    top_key, top = ranked[0]
    second = ranked[1][1] if len(ranked) > 1 else 0.0
    if top < MIN_FILL:
        return MCQReading(None, "blank", fills)
    if second >= MIN_FILL and second >= RIVAL_RATIO * top:
        return MCQReading(None, "multiple", fills)
    return MCQReading(top_key, "ok", fills)
