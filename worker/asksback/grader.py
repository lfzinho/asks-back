"""Grade open answers against the rubric: the real score, plus the signals that decide follow-ups.

The model gets the answer crop twice (clean, and with numbered boxes drawn on the handwriting),
the teacher's rubric and the course's misconception bank. It returns, as schema-checked JSON:
which criteria are met, which box numbers hold mistakes, how sure it is, whether the reasoning
is present, and which catalogued misconceptions the answer shows. Points are added up here in
code, not by the model, so the same criteria always give the same score.

`OfflineGrader` is the `mock` stand-in: local OCR reads the handwriting and each criterion is
met when its `look_for` terms appear. No network, no key, clearly labelled.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import cv2
import numpy as np
from pydantic import BaseModel, ValidationError

from . import llm
from .exam import Box, Exam, Question
from .images import crop, png_b64
from .ink import InkBox, word_boxes
from .text import mentions, normalize

PROMPT_VERSION = "grade-v2"
CROP_PAD = 12
VIEW_SIDE = 1400


# ---------- model output ----------

class BoxReading(BaseModel):
    box_id: int
    text: str


class CriterionCheck(BaseModel):
    criterion_id: str
    met: bool
    evidence_box_ids: list[int]
    reason: str


class Mark(BaseModel):
    box_ids: list[int]
    severity: Literal["error", "note"]
    message: str


class OpenGrade(BaseModel):
    transcription: list[BoxReading]
    criteria: list[CriterionCheck]
    marks: list[Mark]
    feedback: str
    confidence: Literal["high", "medium", "low"]
    confidence_reason: str
    justification: Literal["present", "generic", "missing"]
    misconceptions: list[str]  # ids from the misconception bank that the answer shows
    needs_teacher: bool
    needs_teacher_reason: str


def _obj(props: dict, required: list[str] | None = None) -> dict:
    return {"type": "object", "properties": props, "required": required or list(props), "additionalProperties": False}


_INT_LIST = {"type": "array", "items": {"type": "integer"}}
OUTPUT_SCHEMA = _obj({
    "transcription": {"type": "array", "items": _obj({"box_id": {"type": "integer"}, "text": {"type": "string"}})},
    "criteria": {"type": "array", "items": _obj({
        "criterion_id": {"type": "string"},
        "met": {"type": "boolean"},
        "evidence_box_ids": _INT_LIST,
        "reason": {"type": "string"},
    })},
    "marks": {"type": "array", "items": _obj({
        "box_ids": _INT_LIST,
        "severity": {"type": "string", "enum": ["error", "note"]},
        "message": {"type": "string"},
    })},
    "feedback": {"type": "string"},
    "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
    "confidence_reason": {"type": "string"},
    "justification": {"type": "string", "enum": ["present", "generic", "missing"]},
    "misconceptions": {"type": "array", "items": {"type": "string"}},
    "needs_teacher": {"type": "boolean"},
    "needs_teacher_reason": {"type": "string"},
})

SYSTEM = """You grade one handwritten answer from a paper exam on behalf of the student's teacher. \
The teacher reviews every grade you give.

You receive the question, the teacher's rubric as a list of criteria, the course's bank of known \
misconceptions, and two images of the same answer area: a clean crop, and a copy where each piece of \
handwriting has a magenta box with a number. Printed text on the page is not boxed.

How to grade:
- First transcribe each numbered box exactly as written, including mistakes. Do not correct the \
student's work while transcribing. If a box is unreadable, write "[illegible]".
- Decide each rubric criterion independently, as met or not met, following the criterion text and \
the teacher's style notes literally. Cite the box numbers that support each decision. Return every \
criterion id exactly once. Criteria of kind "reasoning" need the reasoning to be on the paper: a correct \
result alone does not meet them.
- Do not add points, totals or criteria of your own. Points are computed from your criterion decisions.
- In `marks`, point at the box numbers where something is wrong ("error") or worth a remark ("note").
- `feedback` is two or three neutral sentences for the teacher, in the language the teacher asks for.
- `confidence`: how sure you are of the criterion decisions. Use "medium" or "low" when the decision \
depends on how a word or phrase is interpreted (for example a vague term that could mean two things), \
when handwriting is hard to read, or when work is crossed out. Say why in `confidence_reason`.
- `justification`: "present" if the answer explains why, "generic" if the explanation is a vague \
phrase that would fit any answer, "missing" if there is only a result.
- `misconceptions`: the ids of bank entries this answer clearly shows. Only use ids from the bank; \
return an empty list when none applies.
- Judge what is on the paper, not what the student probably meant."""


# ---------- answer view ----------

@dataclass
class AnswerView:
    clean: np.ndarray  # answer crop, scaled for the model
    numbered: np.ndarray  # same crop with numbered boxes
    boxes: list[InkBox]  # in master-page coordinates
    ocr_hints: dict[int, str] = field(default_factory=dict)


def _draw_numbered(img: np.ndarray, boxes: list[tuple[int, Box]]) -> np.ndarray:
    out = img.copy()
    color = (255, 0, 255)
    font, fs, th = cv2.FONT_HERSHEY_SIMPLEX, 0.55, 1
    for num, (x, y, w, h) in boxes:
        cv2.rectangle(out, (x - 2, y - 2), (x + w + 2, y + h + 2), color, 2)
        label = str(num)
        (tw, tht), _ = cv2.getTextSize(label, font, fs, th)
        ty = y - 4 if y - tht - 8 >= 0 else y + h + tht + 6
        cv2.rectangle(out, (x - 2, ty - tht - 4), (x + tw + 4, ty + 3), color, -1)
        cv2.putText(out, label, (x + 1, ty), font, fs, (255, 255, 255), th, cv2.LINE_AA)
    return out


def prepare_answer(aligned: np.ndarray, ink: np.ndarray, q: Question) -> AnswerView:
    x, y, w, h = q.region
    ox, oy = max(0, x - CROP_PAD), max(0, y - CROP_PAD)
    clean = crop(aligned, q.region, CROP_PAD)
    local = word_boxes(crop(ink, q.region, CROP_PAD))

    f = min(2.0, VIEW_SIDE / max(clean.shape[:2]))
    scaled = cv2.resize(clean, None, fx=f, fy=f, interpolation=cv2.INTER_AREA if f < 1 else cv2.INTER_CUBIC)
    sboxes = [(b.id, tuple(round(v * f) for v in b.box)) for b in local]
    numbered = _draw_numbered(scaled, sboxes)
    page_boxes = [InkBox(b.id, (b.box[0] + ox, b.box[1] + oy, b.box[2], b.box[3]), b.line) for b in local]
    return AnswerView(scaled, numbered, page_boxes)


# ---------- grading ----------

@dataclass
class GradeOutcome:
    grade: OpenGrade | None
    score: float | None
    flags: list[str]
    cached: bool = False


def compute_score(q: Question, grade: OpenGrade) -> tuple[float, list[str]]:
    flags = []
    returned = {c.criterion_id: c for c in grade.criteria}
    unknown = set(returned) - {c.id for c in q.criteria}
    missing = [c.id for c in q.criteria if c.id not in returned]
    if unknown:
        flags.append(f"unknown criteria returned: {sorted(unknown)}")
    if missing:
        flags.append(f"criteria not decided: {missing}")
    pts = sum(c.points for c in q.criteria if c.id in returned and returned[c.id].met)
    return min(max(pts, 0.0), q.points), flags


def rubric_text(exam: Exam, q: Question) -> str:
    lines = [
        f"Exam: {exam.name}",
        f"Write `feedback` and mark messages in: {exam.language}",
        "",
        "Teacher's grading style:",
        exam.grading_style.strip() or "(none given)",
        "",
        f"Question {q.id} ({q.points:g} points).",
    ]
    if q.prompt:
        lines += ["Question statement:", q.prompt.strip()]
    if q.answer_key:
        lines += ["", "Teacher's answer key:", q.answer_key.strip()]
    lines += ["", "Rubric criteria (decide each one):"]
    for c in q.criteria:
        kind = "penalty" if c.points < 0 else "points"
        lines.append(f"- id `{c.id}` ({c.points:+g} {kind} when met, kind: {c.kind}): {c.description}")
    return "\n".join(lines)


def bank_text(bank: list[dict]) -> str:
    if not bank:
        return "Misconception bank for this question: (empty)"
    lines = ["Misconception bank for this question:"]
    for m in bank:
        lines.append(f"- id `{m['id']}`: {m['title']}" + (f" (typical wording: {'; '.join(m.get('phrases') or [])})"
                                                           if m.get("phrases") else ""))
    return "\n".join(lines)


class ModelGrader:
    """Grades with a real model (backend "claude" or "openrouter")."""

    def __init__(self, exam: Exam, masters: list[np.ndarray], backend: str):
        self.exam = exam
        self.masters = masters
        self.backend = backend

    def grade(self, q: Question, view: AnswerView, bank: list[dict] = ()) -> GradeOutcome:
        blocks: list[dict] = [{"type": "text", "text": rubric_text(self.exam, q) + "\n\n" + bank_text(list(bank))}]
        if q.statement_region:
            stmt = crop(self.masters[q.page - 1], q.statement_region, 6)
            blocks += [{"type": "text", "text": "The printed question statement, from the blank exam:"},
                       {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": png_b64(stmt)}}]
        box_list = ", ".join(str(b.id) for b in view.boxes) or "(no handwriting detected)"
        blocks += [
            {"type": "text", "text": "Image 1: the student's answer area (clean)."},
            {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": png_b64(view.clean)}},
            {"type": "text", "text": "Image 2: the same area with numbered boxes on the handwriting."},
            {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": png_b64(view.numbered)}},
            {"type": "text", "text": f"Numbered boxes in image 2: {box_list}.\nGrade this answer."},
        ]
        try:
            data = llm.ask_json(self.backend, SYSTEM + f"\n\n(prompt {PROMPT_VERSION})", blocks, OUTPUT_SCHEMA, "grade")
            grade = OpenGrade.model_validate(data)
        except (llm.ModelError, ValidationError) as e:
            return GradeOutcome(None, None, [f"grading failed: {str(e)[:300]}"])
        known = {m["id"] for m in bank}
        grade.misconceptions = [m for m in grade.misconceptions if m in known]
        score, flags = compute_score(q, grade)
        return GradeOutcome(grade, score, flags)


# ---------- offline stand-in ----------

_ocr = None


def read_handwriting(img: np.ndarray) -> list[tuple[str, float]]:
    """Lines of text in an answer crop with their OCR confidence, top to bottom (RapidOCR, local)."""
    global _ocr
    if _ocr is None:
        from rapidocr_onnxruntime import RapidOCR

        _ocr = RapidOCR()
    result, _ = _ocr(img)
    # Group fragments into lines by vertical center (handwritten lines slope), then read left to right.
    frags = sorted(((sum(p[1] for p in box) / 4, min(p[0] for p in box), max(p[1] for p in box) - min(p[1] for p in box),
                     text, float(conf)) for box, text, conf in result or []))
    lines: list[list] = []
    for f in frags:
        if lines and abs(f[0] - lines[-1][-1][0]) < 0.6 * max(f[2], lines[-1][-1][2]):
            lines[-1].append(f)
        else:
            lines.append([f])
    out = []
    for line in lines:
        line.sort(key=lambda f: f[1])
        out.append((" ".join(f[3] for f in line), min(f[4] for f in line)))
    return out


class OfflineGrader:
    """`mock` grader: reads the handwriting with local OCR and meets a criterion when its `look_for`
    terms appear. Deterministic and free; every decision says it came from the offline grader."""

    def __init__(self, cache_dir: Path | None = None):
        self.cache_dir = cache_dir

    def grade(self, q: Question, view: AnswerView, bank: list[dict] = ()) -> GradeOutcome:
        key = hashlib.sha256(png_b64(view.clean).encode()).hexdigest()[:20]
        cache = self.cache_dir / f"ocr-{key}.json" if self.cache_dir else None
        if cache and cache.exists():
            lines = [tuple(x) for x in json.loads(cache.read_text())]
        else:
            lines = read_handwriting(view.clean) if view.boxes else []
            if cache:
                cache.parent.mkdir(parents=True, exist_ok=True)
                cache.write_text(json.dumps(lines))
        return offline_grade(q, [t for t, _ in lines], [c for _, c in lines], view.boxes, bank)


def offline_grade(q: Question, lines: list[str], confidences: list[float], boxes: list[InkBox] = (),
                  bank: list[dict] = ()) -> GradeOutcome:
    """The offline grading rule, on already transcribed lines (also used for typed text)."""
    text = " ".join(lines)
    by_line: dict[int, list[int]] = {}
    for b in boxes:
        by_line.setdefault(b.line, []).append(b.id)
    transcription = [BoxReading(box_id=(by_line.get(i + 1) or [i + 1])[0], text=t) for i, t in enumerate(lines)]
    criteria = []
    for c in q.criteria:
        met = mentions(text, c.look_for or _content_words(c.description))
        criteria.append(CriterionCheck(criterion_id=c.id, met=met, evidence_box_ids=[],
                                       reason=f"[mock] {'found' if met else 'did not find'} the expected terms"))
    found = [m["id"] for m in bank if m.get("phrases") and mentions(text, m["phrases"])]
    reasoning = [c for c in q.criteria if c.kind == "reasoning"]
    if not reasoning:
        justification = "present" if len(normalize(text).split()) >= 8 else "missing"
    else:
        met_reasoning = [c for c, d in zip(q.criteria, criteria) if c.kind == "reasoning" and d.met]
        words = len(normalize(text).split())
        justification = "present" if met_reasoning else ("generic" if words >= 6 else "missing")
    low_ocr = bool(confidences) and min(confidences) < 0.6
    vague = _vague_terms(text)
    confidence = "low" if low_ocr else ("medium" if vague else "high")
    reason = ("[mock] some handwriting was hard to read" if low_ocr else
              f"[mock] '{vague}' can be read in more than one way" if vague else "")
    grade = OpenGrade(
        transcription=transcription, criteria=criteria, marks=[],
        feedback="[mock] Offline grade from local OCR and the rubric's look-for terms.",
        confidence=confidence, confidence_reason=reason, justification=justification, misconceptions=found,
        needs_teacher=not lines, needs_teacher_reason="[mock] no handwriting could be read" if not lines else "",
    )
    score, flags = compute_score(q, grade)
    return GradeOutcome(grade, score, flags)


STOP = set("a an the of to in on for and or with is are be it its this that as by at from e.g. eg each one "
           "shows names gives states correct answer answers".split())
# Words whose meaning depends on what they refer to; a short answer that leans on one is worth clarifying.
VAGUE = ["half", "part of", "some of", "smaller", "bigger", "kind of", "sort of", "basically", "the thing"]


def _content_words(description: str) -> list[str]:
    return [w for w in re.findall(r"[a-zA-Z()]{4,}", description.lower()) if w not in STOP][:4]


def _vague_terms(text: str) -> str | None:
    """The first vague term in a short answer (under 25 words), if any."""
    t = normalize(text)
    if len(t.split()) >= 25:
        return None
    return next((v for v in VAGUE if re.search(rf"\b{v}\b", t)), None)
