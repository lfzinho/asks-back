"""From photos to graded answers, for one exam folder or one student at a time.

exam_dir/
  exam.yaml
  master/...            blank exam pages (paths listed in exam.yaml)
  students/<id>/*.jpg   photos of that student's pages, any order

The worker uses `grade_pages` per student; `run` grades a whole folder offline into results.json.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np

from .exam import Exam, Question
from .grader import AnswerView, GradeOutcome, prepare_answer
from .images import list_images, load_image
from .ink import ink_mask
from .omr import read_mcq
from .register import Registrar
from .results import Annotation, QuestionResult


def mcq_result(sid: str, q: Question, ink) -> QuestionResult:
    reading = read_mcq(ink, q.options)
    detail = {"selected": reading.selected, "reading": reading.status,
              "fills": {k: round(v, 3) for k, v in reading.fills.items()}, "answer": q.answer}
    anns: list[Annotation] = []
    if reading.status == "multiple":
        for k, v in reading.fills.items():
            if v > 0:
                anns.append(Annotation("flag", q.options[k], message="several options marked"))
        return QuestionResult(sid, q.id, "mcq", q.points, None, "needs_teacher", detail, anns,
                              ["more than one option looks marked"])
    correct = reading.selected == q.answer
    if reading.selected:
        anns.append(Annotation("correct" if correct else "wrong", q.options[reading.selected]))
    if not correct:
        anns.append(Annotation("expected", q.options[q.answer], message=f"correct answer: {q.answer}"))
    flags = ["no option looks marked"] if reading.status == "blank" else []
    return QuestionResult(sid, q.id, "mcq", q.points, q.points if correct else 0.0, "graded", detail, anns, flags)


def open_result(sid: str, q: Question, view: AnswerView, outcome: GradeOutcome | None) -> QuestionResult:
    detail: dict = {"boxes": [{"id": b.id, "box": b.box, "line": b.line} for b in view.boxes]}
    if outcome is None:
        return QuestionResult(sid, q.id, "open", q.points, None, "not_graded", detail)
    flags = list(outcome.flags)
    g = outcome.grade
    if g is None:
        return QuestionResult(sid, q.id, "open", q.points, None, "needs_teacher", detail, [], flags)

    by_id = {b.id: b.box for b in view.boxes}
    points = {c.id: c.points for c in q.criteria}
    detail.update({
        "transcription": [t.model_dump() for t in g.transcription],
        "criteria": [{**c.model_dump(), "points": points.get(c.criterion_id)} for c in g.criteria],
        "feedback": g.feedback,
        "confidence": g.confidence,
        "confidence_reason": g.confidence_reason,
        "justification": g.justification,
        "misconceptions": g.misconceptions,
        "needs_teacher_reason": g.needs_teacher_reason,
    })
    anns: list[Annotation] = []
    for i, m in enumerate(g.marks, start=1):
        boxes = [by_id[b] for b in m.box_ids if b in by_id]
        if len(boxes) < len(m.box_ids):
            flags.append(f"mark {i} refers to unknown boxes {[b for b in m.box_ids if b not in by_id]}")
        if not boxes:
            continue
        x0 = min(b[0] for b in boxes)
        y0 = min(b[1] for b in boxes)
        x1 = max(b[0] + b[2] for b in boxes)
        y1 = max(b[1] + b[3] for b in boxes)
        anns.append(Annotation(m.severity, (x0, y0, x1 - x0, y1 - y0), str(i), m.message))
    status = "needs_teacher" if (g.needs_teacher or flags) else "graded"
    return QuestionResult(sid, q.id, "open", q.points, outcome.score, status, detail, anns, flags)


def grade_pages(sid: str, exam: Exam, masters: list[np.ndarray], aligned: dict[int, np.ndarray], grader,
                bank_for=lambda qid: []) -> list[QuestionResult]:
    """Grade one student's aligned pages (page number -> image). `bank_for(qid)` gives the misconceptions."""
    inks = {p: (img, ink_mask(img, masters[p - 1])) for p, img in aligned.items()}
    out = []
    for q in exam.questions:
        if q.page not in inks:
            out.append(QuestionResult(sid, q.id, q.type, q.points, None, "missing_page",
                                      flags=[f"page {q.page} was not captured"]))
        elif q.type == "mcq":
            out.append(mcq_result(sid, q, inks[q.page][1]))
        else:
            img, ink = inks[q.page]
            view = prepare_answer(img, ink, q)
            out.append(open_result(sid, q, view, grader.grade(q, view, bank_for(q.id)) if grader else None))
    return out


def register_photos(paths: list[Path], registrar: Registrar) -> tuple[dict[int, np.ndarray], list[dict]]:
    """Align every photo; keep the strongest match per page."""
    best: dict[int, object] = {}
    log = []
    for path in paths:
        reg = registrar.register(load_image(path))
        log.append({"file": path.name, "page": reg.page if reg else None, "inliers": reg.inliers if reg else 0})
        if reg is not None and (reg.page not in best or best[reg.page].inliers < reg.inliers):
            best[reg.page] = reg
    return {p: r.aligned for p, r in best.items()}, log


def run(exam_dir: Path, out_dir: Path, grader=None, bank_for=lambda qid: []) -> dict:
    t0 = time.time()
    exam = Exam.load(exam_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    masters = [load_image(p) for p in exam.page_paths()]
    registrar = Registrar(masters)
    registrations, results = {}, []
    for d in sorted(d for d in (exam_dir / "students").iterdir() if d.is_dir()):
        aligned, log = register_photos(list_images(d), registrar)
        registrations[d.name] = log
        results += grade_pages(d.name, exam, masters, aligned, grader, bank_for)
    summary = {"exam": exam.name, "students": len(registrations), "seconds": round(time.time() - t0, 1)}
    (out_dir / "results.json").write_text(json.dumps({
        "summary": summary, "registrations": registrations, "results": [r.to_dict() for r in results],
    }, indent=2, default=str))
    return summary
