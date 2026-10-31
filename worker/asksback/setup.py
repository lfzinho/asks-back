"""Automatic exam setup: turn a blank test (PDF or photos) into an exam definition.

Layout comes from the printed page, with no AI: free local OCR (printed text reads
reliably) finds the numbered questions, the lettered options and the name label;
contour detection finds the tick boxes and the answer frames. Every box is in
master-page pixels, so grading and marking work as if the teacher had drawn them.

What a question *means* (the correct option, what a good answer contains) is filled
in afterwards:
  - from an answer-key copy, if the teacher uploads one (the test with the correct
    options marked; read by OMR, free);
  - by ``ModelExamAI`` (Claude or OpenRouter), which solves the questions and writes the
    rubric, marking which criteria are the answer and which are the reasoning;
  - or by ``MockExamAI`` (offline stand-in): random options and one generic criterion,
    clearly flagged, so the rest of the app can be tried.
"""

from __future__ import annotations

import hashlib
import json
import random
import re
from dataclasses import dataclass, field

import cv2
import numpy as np

from .exam import Box
from .images import crop, png_b64, resize_max, to_gray
from .ink import ink_mask
from .omr import read_mcq
from .register import Registrar

PDF_WIDTH = 1700  # rendered page width in pixels (A4 at about 200 dpi)

Q_RE = re.compile(r"^\s*(\d{1,3})\s*[.)]\s*(.*)$")
OPT_RE = re.compile(r"^\s*\(?([A-Ha-h])\s*[).:]\s*(.*)$")
PTS_RE = re.compile(r"\(\s*(\d+(?:[.,]\d+)?)\s*(?:points?|pts?|marks?|puntos?|pontos?)\s*\)", re.I)
NAME_RE = re.compile(r"^\s*(name|nombre|nome|student|alumno|aluno)\b", re.I)


# ---------- input ----------

def load_pages(data: bytes, content_type: str = "") -> list[np.ndarray]:
    """BGR page images from a PDF or an image file."""
    if content_type == "application/pdf" or data[:5] == b"%PDF-":
        import pypdfium2 as pdfium

        pdf = pdfium.PdfDocument(data)
        pages = []
        for page in pdf:
            scale = PDF_WIDTH / page.get_width()
            rgb = np.asarray(page.render(scale=scale).to_pil().convert("RGB"))
            pages.append(cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR))
        return pages
    img = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("not a PDF or an image")
    return [img]


# ---------- page layout ----------

@dataclass
class Line:
    box: Box
    text: str

    @property
    def bottom(self) -> int:
        return self.box[1] + self.box[3]


_ocr = None


def read_lines(img: np.ndarray) -> list[Line]:
    """Printed text lines, top to bottom, via RapidOCR (local, free)."""
    global _ocr
    if _ocr is None:
        from rapidocr_onnxruntime import RapidOCR

        _ocr = RapidOCR()
    result, _ = _ocr(img)
    lines = []
    for quad, text, _conf in result or []:
        xs, ys = [int(p[0]) for p in quad], [int(p[1]) for p in quad]
        lines.append(Line((min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys)), text.strip()))
    return sorted(lines, key=lambda ln: (ln.box[1] + ln.box[3] // 2, ln.box[0]))


def find_rectangles(img: np.ndarray) -> tuple[list[Box], list[Box]]:
    """(tick boxes, answer frames) printed on the page."""
    g = to_gray(img)
    bw = cv2.adaptiveThreshold(g, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY_INV, 31, 15)
    contours, _ = cv2.findContours(bw, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    H, W = g.shape
    ticks, frames = [], []
    for c in contours:
        approx = cv2.approxPolyDP(c, 0.04 * cv2.arcLength(c, True), True)
        if len(approx) != 4 or not cv2.isContourConvex(approx):
            continue
        x, y, w, h = cv2.boundingRect(approx)
        if 0.012 * W <= w <= 0.07 * W and 0.75 <= w / h <= 1.33:
            ticks.append((x, y, w, h))
        elif w >= 0.35 * W and h >= 0.03 * H:
            frames.append((x, y, w, h))
    return _dedupe(ticks), _dedupe(frames)


def _iou(a: Box, b: Box) -> float:
    x0, y0 = max(a[0], b[0]), max(a[1], b[1])
    x1, y1 = min(a[0] + a[2], b[0] + b[2]), min(a[1] + a[3], b[1] + b[3])
    inter = max(0, x1 - x0) * max(0, y1 - y0)
    return inter / float(a[2] * a[3] + b[2] * b[3] - inter)


def _dedupe(boxes: list[Box]) -> list[Box]:
    """A printed outline yields an outer and an inner contour: keep the outer one."""
    kept: list[Box] = []
    for b in sorted(boxes, key=lambda b: -b[2] * b[3]):
        if all(_iou(b, k) < 0.6 for k in kept):
            kept.append(b)
    return kept


def _union(boxes: list[Box], pad: int = 0) -> Box:
    x0 = min(b[0] for b in boxes) - pad
    y0 = min(b[1] for b in boxes) - pad
    x1 = max(b[0] + b[2] for b in boxes) + pad
    y1 = max(b[1] + b[3] for b in boxes) + pad
    return (max(0, x0), max(0, y0), x1 - max(0, x0), y1 - max(0, y0))


@dataclass
class Found:
    """A question found on a page, before its meaning is filled in."""

    number: int
    page: int
    statement: list[Line]
    options: list[tuple[str, Line]] = field(default_factory=list)
    end_y: int = 0  # where the next printed thing starts

    @property
    def text(self) -> str:
        return " ".join(ln.text for ln in self.statement)


def find_questions(pages: list[np.ndarray]) -> tuple[list[dict], dict, list[str]]:
    """(questions, extras, notes). Questions follow the app's exam schema, without
    answers or criteria. extras: title and name_region."""
    questions: list[dict] = []
    notes: list[str] = []
    extras: dict = {"title": None, "name_region": None}
    last_number = 0
    for page_no, img in enumerate(pages, start=1):
        H, W = img.shape[:2]
        lines = read_lines(img)
        ticks, frames = find_rectangles(img)
        if not lines:
            notes.append(f"Page {page_no}: no printed text found.")
            continue
        left = min(ln.box[0] for ln in lines)
        right = max(max(ln.box[0] + ln.box[2] for ln in lines), int(W * 0.85))
        line_h = int(np.median([ln.box[3] for ln in lines]))

        found: list[Found] = []
        current: Found | None = None
        for ln in lines:
            q = Q_RE.match(ln.text)
            opt = OPT_RE.match(ln.text)
            if q and int(q.group(1)) > last_number and ln.box[0] < left + 0.08 * W and q.group(2):
                if current:
                    current.end_y = ln.box[1]
                last_number = int(q.group(1))
                current = Found(last_number, page_no, [ln])
                found.append(current)
            elif current and opt and len(opt.group(2)) < 60:
                current.options.append((opt.group(1).upper(), ln))
            elif (current and not current.options
                  and 0 <= ln.box[1] - current.statement[-1].bottom < 0.9 * line_h
                  and abs(ln.box[0] - current.statement[0].box[0]) < 0.1 * W):
                current.statement.append(ln)  # the statement continues on the next line
            else:
                if current:
                    current.end_y = ln.box[1]
                    current = None
                if page_no == 1 and extras["title"] is None and not found and not NAME_RE.match(ln.text):
                    extras["title"] = ln.text
                if page_no == 1 and extras["name_region"] is None and NAME_RE.match(ln.text):
                    extras["name_region"] = _name_region(ln, lines, W)
        if current:
            current.end_y = int(H * 0.95)

        for f in found:
            questions.append(_to_question(f, ticks, frames, left, right, line_h, notes))
    if not questions:
        notes.append("No numbered questions found (expected lines like “1. …” or “1) …”).")
    return questions, extras, notes


def _name_region(label: Line, lines: list[Line], W: int) -> Box:
    x0 = label.box[0] + label.box[2] + 5
    same_row = [ln for ln in lines if ln is not label and abs(ln.box[1] - label.box[1]) < label.box[3] and ln.box[0] > x0]
    x1 = min([ln.box[0] - 10 for ln in same_row], default=int(W * 0.95))
    pad = label.box[3]
    return (x0, max(0, label.box[1] - pad), x1 - x0, label.box[3] + int(1.5 * pad))


def _to_question(f: Found, ticks: list[Box], frames: list[Box], left: int, right: int,
                 line_h: int, notes: list[str]) -> dict:
    qid = f"q{f.number}"
    text = f.text
    pts = PTS_RE.search(text)
    prompt = PTS_RE.sub("", Q_RE.match(text).group(2)).strip()
    stmt_box = _union([ln.box for ln in f.statement], pad=6)
    base = {"id": qid, "page": f.page, "prompt": prompt, "statement_region": stmt_box, "flags": []}

    letters = [k for k, _ in f.options]
    if len(f.options) >= 2 and len(set(letters)) == len(letters):
        options, option_text = {}, {}
        for letter, ln in f.options:
            x, y, w, h = ln.box
            cy = y + h / 2
            near = [t for t in ticks
                    if abs(t[1] + t[3] / 2 - cy) < max(h, t[3]) * 0.6 and x - 3 * t[2] < t[0] + t[2] <= x + 6]
            if near:  # pad the printed box a little: crosses and ticks spill over its edge
                tx, ty, tw, th = max(near, key=lambda t: t[0])
                m = round(0.17 * tw)
                options[letter] = (tx - m, ty - m, tw + 2 * m, th + 2 * m)
            else:  # no tick box: the student circles or crosses the letter itself
                letter_w = max(h, int(w / max(len(ln.text), 1) * 2))
                options[letter] = (x - 8, y - 8, letter_w + 16, h + 16)
            option_text[letter] = OPT_RE.match(ln.text).group(2).strip()
        region = _union([stmt_box, *options.values(), *(ln.box for _, ln in f.options)], pad=10)
        return {**base, "type": "mcq", "points": float(pts.group(1).replace(",", ".")) if pts else 1.0,
                "options": options, "option_text": option_text, "answer": None, "region": region}

    if f.options:
        notes.append(f"{qid}: options look odd ({', '.join(letters)}); treated as an open question.")
    top = stmt_box[1] + stmt_box[3]
    inside = [fr for fr in frames if top - line_h <= fr[1] < f.end_y]
    if inside:
        x, y, w, h = min(inside, key=lambda fr: fr[1])
        region = (x + 3, y + 3, w - 6, h - 6)
    else:
        region = (left, top + 4, right - left, f.end_y - top - 10)
    if region[3] < 1.5 * line_h:
        base["flags"].append("Very little room to answer was found below this question; check the answer area.")
        region = (left, top, right - left, max(region[3], 2 * line_h))
    return {**base, "type": "open", "points": float(pts.group(1).replace(",", ".")) if pts else 2.0,
            "region": region, "answer_key": None, "criteria": []}


# ---------- answer key copy (optional) ----------

def read_answer_key(key_images: list[np.ndarray], masters: list[np.ndarray], questions: list[dict]) -> tuple[dict, dict]:
    """(mcq answers by qid, aligned key pages by page number) from a filled-in copy."""
    registrar = Registrar(masters)
    answers, aligned_pages = {}, {}
    for img in key_images:
        reg = registrar.register(img)
        if reg is None:
            continue
        aligned_pages[reg.page] = reg.aligned
        ink = ink_mask(reg.aligned, masters[reg.page - 1])
        for q in questions:
            if q["page"] == reg.page and q["type"] == "mcq":
                reading = read_mcq(ink, q["options"])
                if reading.status == "ok":
                    answers[q["id"]] = reading.selected
    return answers, aligned_pages


# ---------- meaning: answers and rubric ----------

class MockExamAI:
    """Offline stand-in for ModelExamAI: guesses, and says so."""

    name = "mock"

    def complete(self, questions: list[dict], masters, key_pages: dict, style: str, language: str) -> None:
        for q in questions:
            rng = random.Random(hashlib.sha256(f"{q['id']}{q['prompt']}".encode()).hexdigest())
            if q["type"] == "mcq" and q["answer"] is None:
                q["answer"] = rng.choice(sorted(q["options"]))
                q["flags"].append("[MOCK] Correct option guessed at random. Upload an answer key, or run the worker with an AI key.")
            elif q["type"] == "open":
                q["criteria"] = [{"id": "correct", "points": q["points"],
                                  "description": "The answer is correct and complete."}]
                q["flags"].append("[MOCK] Generic rubric. With an AI key, the worker writes real criteria from the question.")


SETUP_SYSTEM = """You prepare a teacher's paper test for automatic grading and follow-up questions.
You get the blank test pages, a list of the questions found on them (statement, options, points),
optionally crops of the teacher's answer-key copy, and the teacher's grading style.
For each question:
- multiple choice: give the correct option letter (keep the one from the answer key if given);
- open answer: write a short model answer and 1 to 4 rubric criteria. Each criterion is checkable
  as met / not met from the student's writing; their points must add up to the question's points.
  Mark each criterion's `kind`: "answer" for the result itself, "reasoning" for the justification
  or explanation behind it. Give 2 to 5 `look_for` words or short phrases that show it is met.
  Follow the teacher's grading style (partial credit, penalties as negative points).
Write descriptions in the feedback language. If a question is ambiguous or you are unsure, say so in `note`."""

SETUP_SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["questions"],
    "properties": {"questions": {"type": "array", "items": {
        "type": "object", "additionalProperties": False,
        "required": ["id", "answer", "answer_key", "criteria", "note"],
        "properties": {
            "id": {"type": "string"},
            "answer": {"type": ["string", "null"]},
            "answer_key": {"type": ["string", "null"]},
            "criteria": {"type": "array", "items": {
                "type": "object", "additionalProperties": False,
                "required": ["id", "points", "description", "kind", "look_for"],
                "properties": {"id": {"type": "string"}, "points": {"type": "number"}, "description": {"type": "string"},
                               "kind": {"type": "string", "enum": ["answer", "reasoning"]},
                               "look_for": {"type": "array", "items": {"type": "string"}}}}},
            "note": {"type": "string"},
        }}}},
}


class ModelExamAI:
    """Solves the questions and writes the rubric in one model request per exam."""

    def __init__(self, backend: str):
        self.name = backend

    def complete(self, questions: list[dict], masters, key_pages: dict, style: str, language: str) -> None:
        from .llm import ask_json

        content: list[dict] = []
        for i, m in enumerate(masters, start=1):
            content += [{"type": "text", "text": f"Blank page {i}:"},
                        {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": png_b64(resize_max(m, 1600))}}]
        for q in questions:
            if q["type"] == "open" and q["page"] in key_pages:
                content += [{"type": "text", "text": f"Teacher's answer-key copy for {q['id']}:"},
                            {"type": "image", "source": {"type": "base64", "media_type": "image/png",
                                                         "data": png_b64(crop(key_pages[q["page"]], q["region"]))}}]
        listing = [{k: q.get(k) for k in ("id", "type", "points", "prompt", "option_text", "answer")} for q in questions]
        content.append({"type": "text", "text": (
            f"Feedback language: {language}\nTeacher's grading style: {style or '(none given)'}\n"
            f"Questions found:\n{json.dumps(listing, ensure_ascii=False, indent=1)}")})
        by_id = {r["id"]: r for r in ask_json(self.name, SETUP_SYSTEM, content, SETUP_SCHEMA, "exam_setup")["questions"]}
        for q in questions:
            r = by_id.get(q["id"])
            if r is None:
                q["flags"].append("The AI did not return this question; check it.")
                continue
            if r["note"]:
                q["flags"].append(r["note"])
            if q["type"] == "mcq":
                if q["answer"] is None and r["answer"] in q["options"]:
                    q["answer"] = r["answer"]
                    q["flags"].append("Correct option chosen by the AI (no answer key); check it.")
            else:
                q["answer_key"] = r["answer_key"]
                q["criteria"] = _fit_points(r["criteria"], q["points"])


def _fit_points(criteria: list[dict], points: float) -> list[dict]:
    """Scale the positive criteria so they add up to the question's points."""
    positive = sum(c["points"] for c in criteria if c["points"] > 0)
    if positive > 0 and abs(positive - points) > 1e-6:
        criteria = [{**c, "points": round(c["points"] * points / positive, 2) if c["points"] > 0 else c["points"]}
                    for c in criteria]
    seen, out = set(), []
    for i, c in enumerate(criteria):
        cid = c["id"] if c["id"] not in seen else f"{c['id']}{i}"
        seen.add(cid)
        out.append({**c, "id": cid})
    return out or [{"id": "correct", "points": points, "description": "The answer is correct and complete."}]


def build_exam(test_pages: list[np.ndarray], key_images: list[np.ndarray], ai, *,
               style: str = "", language: str = "English") -> dict:
    """Everything the exam document needs except the stored page paths."""
    questions, extras, notes = find_questions(test_pages)
    key_answers, key_pages = read_answer_key(key_images, test_pages, questions) if key_images else ({}, {})
    for q in questions:
        if q["type"] == "mcq" and q["id"] in key_answers:
            q["answer"] = key_answers[q["id"]]
    if key_images and not key_pages:
        notes.append("The answer-key copy did not match any page of the test.")
    missing = [q["id"] for q in questions if q["type"] == "mcq" and q["page"] in key_pages and q["answer"] is None]
    if missing:
        notes.append(f"No single marked option on the answer key for {', '.join(missing)}.")
    ai.complete(questions, test_pages, key_pages, style, language)
    return {"title": extras["title"], "name_region": extras["name_region"], "questions": questions,
            "notes": notes, "key_used": bool(key_pages), "ai": ai.name}
