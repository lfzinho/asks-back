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


def result_doc(r: QuestionResult | dict) -> dict:
    """The stored form of one graded answer (Firestore and the follow-up stage use this shape)."""
    r = r if isinstance(r, dict) else r.to_dict()
    d = r.get("detail") or {}
    annotations = [{"kind": a["kind"], "box": list(a["box"]), "label": a.get("label", ""), "message": a.get("message", "")}
                   for a in r.get("annotations") or []]
    return {
        "question": r["question"],
        "type": r["type"],
        "maxPoints": r["max_points"],
        "score": r["score"],
        "status": r["status"],
        "flags": r.get("flags") or [],
        "feedback": d.get("feedback", ""),
        "annotations": annotations,
        "criteria": d.get("criteria", []),
        "transcription": d.get("transcription", []),
        "confidence": d.get("confidence"),
        "confidenceReason": d.get("confidence_reason", ""),
        "justification": d.get("justification"),
        "misconceptions": d.get("misconceptions", []),
        "mcq": {k: d[k] for k in ("selected", "reading", "fills", "answer") if k in d} or None,
    }
