"""Per-question result records written to results.json."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

from .exam import Box


@dataclass
class Annotation:
    kind: str  # "correct" | "wrong" | "expected" | "error" | "note" | "flag"
    box: Box  # master-page coordinates
    label: str = ""  # short tag drawn on the page (mark number)
    message: str = ""


@dataclass
class QuestionResult:
    student: str
    question: str
    type: str
    max_points: float
    score: float | None  # None = could not grade, teacher must decide
    status: str  # "graded" | "needs_teacher" | "missing_page" | "not_graded"
    detail: dict = field(default_factory=dict)
    annotations: list[Annotation] = field(default_factory=list)
    flags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)
