"""Class insights: what the class got wrong, grouped into misconceptions, and what to teach next.
The misconceptions found here feed the course's misconception bank, which the G4 trigger uses
on the next exam.

Input is the graded (and possibly teacher-edited) results of every student for one exam.
Code computes the per-question statistics and a baseline grouping (missed criterion, wrong
option). With an AI grader, one text-only request groups the wrong answers into
misconceptions and suggests a short teaching plan. Students are sent as S1, S2, ... and
never by name; the counts and student lists are checked in code against the real results.
"""

from __future__ import annotations

import json
import re

from . import llm

PROMPT_VERSION = "insights-v2"
MAX_EXAMPLES = 3

SYSTEM = """You help a teacher decide what to reteach after a test.
You get, for each question, the rubric and the answers of the students who lost points: what they wrote \
(transcribed from handwriting), which criteria they missed and why, and the corrections given. Multiple-choice \
questions come with how many students picked each wrong option.

Group the wrong answers into misconceptions: the same underlying misunderstanding or error pattern, \
not just the same wrong result. Be concrete and specific to what the students actually wrote \
("added numerators and denominators: 3/4 + 1/2 = 4/6"), not generic ("fraction errors").
- One misconception belongs to one question. List every student id that shows it, and only those.
- Skip one-off slips that only one student made, unless they reveal something worth reteaching.
- `example_quote` is a short, verbatim piece of one student's work that shows the error.
- `teaching_tip` is one or two sentences: a concrete activity, example or explanation for the next lesson.
- `plan` is 2 to 4 short priorities for the next lesson, most important first, based on how many \
students are affected and how fundamental the error is.
Write plain text only (no HTML or Markdown), in the language the teacher asks for."""

SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["misconceptions", "plan"],
    "properties": {
        "misconceptions": {"type": "array", "items": {
            "type": "object", "additionalProperties": False,
            "required": ["question_id", "title", "explanation", "student_ids", "example_quote", "teaching_tip"],
            "properties": {
                "question_id": {"type": "string"},
                "title": {"type": "string"},
                "explanation": {"type": "string"},
                "student_ids": {"type": "array", "items": {"type": "string"}},
                "example_quote": {"type": "string"},
                "teaching_tip": {"type": "string"},
            }}},
        "plan": {"type": "array", "items": {"type": "string"}},
    },
}


def _lost_points(r: dict) -> bool:
    return r.get("score") is not None and r["score"] < (r.get("maxPoints") or 0) - 1e-6


def question_stats(questions: list[dict], subs: list[dict]) -> list[dict]:
    out = []
    for q in questions:
        scores = [s["results"][q["id"]]["score"] for s in subs
                  if s.get("results", {}).get(q["id"], {}).get("score") is not None]
        pts = q.get("points") or 0
        out.append({
            "id": q["id"], "type": q["type"], "points": pts, "prompt": q.get("prompt") or "",
            "graded": len(scores),
            "mean": round(sum(scores) / len(scores) / pts, 3) if scores and pts else None,
            "full": round(sum(1 for v in scores if v >= pts - 1e-6) / len(scores), 3) if scores else None,
        })
    return out


def baseline(questions: list[dict], subs: list[dict]) -> list[dict]:
    """Group students by missed criterion (open) or wrong option (multiple choice). No AI."""
    groups = []
    for q in questions:
        qid = q["id"]
        if q["type"] == "mcq":
            by_option: dict[str, list[str]] = {}
            for s in subs:
                r = s.get("results", {}).get(qid) or {}
                sel = (r.get("mcq") or {}).get("selected")
                if sel and sel != q.get("answer"):
                    by_option.setdefault(sel, []).append(s["id"])
            for opt, ids in by_option.items():
                text = (q.get("option_text") or {}).get(opt)
                groups.append({"question": qid, "title": f"Chose {opt} instead of {q.get('answer')}",
                               "explanation": f"Option {opt}: {text}" if text else "", "studentIds": ids,
                               "quote": "", "tip": ""})
        else:
            desc = {c["id"]: c["description"] for c in q.get("criteria", [])}
            by_criterion: dict[str, list[str]] = {}
            for s in subs:
                r = s.get("results", {}).get(qid) or {}
                if not _lost_points(r):
                    continue
                for c in r.get("criteria") or []:
                    if not c.get("met") and (c.get("points") or 0) > 0:
                        by_criterion.setdefault(c["criterion_id"], []).append(s["id"])
            for cid, ids in by_criterion.items():
                groups.append({"question": qid, "title": f"Missed: {desc.get(cid, cid)}", "explanation": "",
                               "studentIds": ids, "quote": "", "tip": ""})
    return groups


def _ai_input(questions: list[dict], subs: list[dict], language: str) -> tuple[str, dict[str, str]]:
    """Text for the model, plus the S-number -> submission id map. Names are never included."""
    alias = {f"S{i}": s["id"] for i, s in enumerate(subs, start=1)}
    back = {v: k for k, v in alias.items()}
    lines = [f"Write in: {language}", f"Students who took the test: {len(subs)}", ""]
    for q in questions:
        qid, pts = q["id"], q.get("points") or 0
        lines.append(f"## Question {qid} ({q['type']}, {pts:g} points)")
        if q.get("prompt"):
            lines.append(f"Statement: {q['prompt']}")
        if q["type"] == "mcq":
            lines.append(f"Correct option: {q.get('answer')}")
            for opt, text in (q.get("option_text") or {}).items():
                lines.append(f"  {opt}) {text}")
            picks: dict[str, list[str]] = {}
            for s in subs:
                sel = ((s.get("results", {}).get(qid) or {}).get("mcq") or {}).get("selected")
                if sel and sel != q.get("answer"):
                    picks.setdefault(sel, []).append(back[s["id"]])
            for opt, ids in sorted(picks.items()):
                lines.append(f"Picked {opt}: {', '.join(ids)}")
            if not picks:
                lines.append("Nobody picked a wrong option.")
        else:
            if q.get("answer_key"):
                lines.append(f"Answer key: {q['answer_key']}")
            for c in q.get("criteria", []):
                lines.append(f"Criterion `{c['id']}` ({c['points']:+g}): {c['description']}")
            wrong = [s for s in subs if _lost_points(s.get("results", {}).get(qid) or {})]
            full = sum(1 for s in subs if (s.get("results", {}).get(qid) or {}).get("score") == pts)
            lines.append(f"Full marks: {full} student(s). Lost points: {len(wrong)}.")
            for s in wrong:
                r = s["results"][qid]
                wrote = " ".join(t.get("text", "") for t in r.get("transcription") or []) or "(no transcription)"
                missed = "; ".join(f"{c['criterion_id']}: {c.get('reason', '')}" for c in r.get("criteria") or []
                                   if not c.get("met"))
                marks = "; ".join(a.get("message", "") for a in r.get("annotations") or [] if a.get("message"))
                lines.append(f"- {back[s['id']]} ({r['score']:g}/{pts:g}) wrote: {wrote}")
                if missed:
                    lines.append(f"  missed: {missed}")
                if marks:
                    lines.append(f"  corrections: {marks}")
        lines.append("")
    return "\n".join(lines), alias


def _plain_text(t: str, names: dict[str, str] | None = None) -> str:
    """Clean model text for the teacher: no HTML, no plan tucked into a tip (the plan has its own field),
    no list numbering (the page numbers the plan), and S1, S2... replaced by the students' names."""
    t = re.sub(r"<br\s*/?>|/n|\\n", "\n", t or "", flags=re.I)
    t = re.split(r"\n\s*(?:\*\*)?(?:Plan|Lesson plan)\s*:", t, maxsplit=1, flags=re.I)[0]
    t = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", t)).strip()
    t = re.sub(r"^(?:\d+[.)]|[-*•])\s+", "", t)
    t = re.sub(r"^S\d+\s+wrote:\s*", "", t)
    if names:
        t = re.sub(r"\bS(\d+)\b", lambda m: names.get(m.group(0), m.group(0)), t)
    return t


def _check(raw: dict, questions: list[dict], subs: list[dict], alias: dict[str, str]) -> tuple[list[dict], list[str]]:
    """Keep only misconceptions on real questions, with students who really lost points there."""
    by_q = {q["id"]: q for q in questions}
    by_id = {s["id"]: s for s in subs}
    names = {a: by_id.get(sid, {}).get("studentName") or "a student" for a, sid in alias.items()}
    out = []
    for m in raw.get("misconceptions", []):
        q = by_q.get(m.get("question_id"))
        if q is None:
            continue
        ids = []
        for a in m.get("student_ids", []):
            sid = alias.get(a.strip().upper())
            if sid is None or sid in ids:
                continue
            r = next((s for s in subs if s["id"] == sid), {}).get("results", {}).get(q["id"]) or {}
            wrong = ((r.get("mcq") or {}).get("selected") not in (None, q.get("answer"))) if q["type"] == "mcq" \
                else _lost_points(r)
            if wrong:
                ids.append(sid)
        if ids:
            out.append({"question": q["id"], "title": _plain_text(m["title"], names),
                        "explanation": _plain_text(m["explanation"], names), "studentIds": ids,
                        "quote": _plain_text(m["example_quote"], names), "tip": _plain_text(m["teaching_tip"], names)})
    return out, [t for t in (_plain_text(p, names) for p in raw.get("plan", [])) if t][:4]


def build_insights(exam: dict, subs: list[dict], ai: str) -> dict:
    """Insights document for one exam. `ai` is the grader kind: mock, openrouter or claude."""
    questions = exam.get("questions") or []
    subs = [s for s in subs if s.get("results")]
    doc = {"students": len(subs), "questions": question_stats(questions, subs), "plan": [], "notes": [],
           "ai": ai, "promptVersion": PROMPT_VERSION}
    groups = baseline(questions, subs)
    if ai in ("openrouter", "claude") and subs:
        text, alias = _ai_input(questions, subs, exam.get("language") or "English")
        try:
            raw = llm.ask_json(ai, SYSTEM, text, SCHEMA, "class_insights")
            groups, doc["plan"] = _check(raw, questions, subs, alias)
        except Exception as e:  # noqa: BLE001 - fall back to the plain grouping
            doc["ai"] = "baseline"
            doc["notes"].append(f"The AI analysis failed ({str(e)[:200]}); showing missed criteria instead.")
    elif ai == "mock":
        doc["notes"].append("[mock] Grouped by missed criterion only. Run the worker with a model "
                            "to group the answers into misconceptions with teaching tips.")
    for g in groups:
        g["count"] = len(g["studentIds"])
        g["examples"] = g["studentIds"][:MAX_EXAMPLES]
    order = {q["id"]: i for i, q in enumerate(questions)}
    doc["misconceptions"] = sorted(groups, key=lambda g: (-g["count"], order.get(g["question"], 0)))
    if not doc["plan"]:
        doc["plan"] = [f"{g['question'].upper()}: {g['title']} ({g['count']} students)"
                       for g in doc["misconceptions"][:3] if g["count"] > 1]
    return doc


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:40] or "misconception"


def grow_bank(bank: list[dict], groups: list[dict]) -> tuple[list[dict], list[str]]:
    """Add this class's misconceptions to the course bank. Only groups the model found (they have a
    quote of real student work) are added; groups by missed criterion are not misconceptions."""
    entries = [dict(e) for e in bank]
    titles = {e["title"].lower() for e in entries}
    added = []
    for g in groups:
        if not g.get("quote") or g["title"].lower() in titles:
            continue
        entry = {"id": _slug(g["title"]), "question": g["question"], "title": g["title"], "phrases": [g["quote"]],
                 "classmate_claim": None, "concept": None, "source": "class", "students": g.get("count", 0)}
        while entry["id"] in {e["id"] for e in entries}:
            entry["id"] += "-2"
        entries.append(entry)
        titles.add(g["title"].lower())
        added.append(entry["id"])
    return entries, added
