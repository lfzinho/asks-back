"""Judge one student reply: which target criteria it meets. The model only says met / not met;
the ladder and scoring decide what that is worth."""

from __future__ import annotations

from . import llm
from .followup import Context
from .text import mentions, normalize

SYSTEM = """You judge one short written reply from a student in a follow-up conversation after an exam.
You get the exam question, the model answer, the criteria the follow-up is about, the conversation so far
and the student's latest reply. For each criterion, decide if the conversation now shows the student
meets it: the student must state the idea in their own reply (repeating a hint word for word does not
count, but reasoning from a hint does). Ignore spelling and grammar. If the reply agrees with a stated
misconception, the criteria it contradicts are not met. Keep `reason` to one neutral sentence for the teacher."""

SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["criteria", "reason"],
    "properties": {
        "criteria": {"type": "array", "items": {
            "type": "object", "additionalProperties": False, "required": ["id", "met"],
            "properties": {"id": {"type": "string"}, "met": {"type": "boolean"}}}},
        "reason": {"type": "string"},
    },
}

AGREES = ["i agree", "they are right", "he is right", "she is right", "yes it does", "yes they are", "yes", "true"]
DISAGREES = ["not", "disagree", "no", "isnt", "doesnt", "wrong", "only"]


def targets_for(ctx: Context, transfer: bool) -> list[dict]:
    """The criteria to judge: the item's targets, or the transfer question as a single pseudo-criterion."""
    if transfer or ctx.targets == ["transfer"]:
        t = ctx.question.get("transfer") or {}
        return [{"id": "transfer", "description": f"Answers correctly: {t.get('prompt') or 'the transfer question'}",
                 "look_for": t.get("look_for") or []}]
    return ctx.target_criteria


def judge(reply: str, ctx: Context, *, transfer: bool = False, backend: str = "mock") -> dict:
    """{"met": {criterion id: bool}, "reason": str, "source": backend}"""
    crit = targets_for(ctx, transfer)
    if not normalize(reply):
        return {"met": {c["id"]: False for c in crit}, "reason": "No reply.", "source": "rule"}
    if backend in ("claude", "openrouter"):
        try:
            return _model_judge(reply, ctx, crit, backend)
        except llm.ModelError as e:
            out = _offline_judge(reply, ctx, crit)
            out["reason"] += f" (model unavailable: {str(e)[:80]})"
            return out
    return _offline_judge(reply, ctx, crit)


def _offline_judge(reply: str, ctx: Context, crit: list[dict]) -> dict:
    met = {c["id"]: mentions(reply, c.get("look_for") or []) for c in crit}
    if ctx.misconception and mentions(reply, AGREES) and not mentions(reply, DISAGREES):
        met = {k: False for k in met}  # agreeing with the classmate's claim keeps the misconception
    found = [c["id"] for c in crit if met[c["id"]]]
    return {"met": met, "source": "mock",
            "reason": f"[mock] found the expected terms for {', '.join(found)}." if found
            else "[mock] did not find the expected terms."}


def _model_judge(reply: str, ctx: Context, crit: list[dict], backend: str) -> dict:
    q = ctx.question
    lines = [f"Question: {q.get('prompt') or ''}", f"Model answer: {q.get('answer_key') or '(none)'}",
             f"Student's written answer on the exam: \"{ctx.answer}\""]
    if ctx.misconception:
        lines.append(f"Misconception being discussed: {ctx.misconception['title']}")
    lines.append("Criteria to decide:")
    lines += [f"- id `{c['id']}`: {c['description']}" for c in crit]
    lines.append("Conversation so far:")
    lines += [f"{'Student' if m['role'] == 'student' else 'Tutor'}: {m['text']}" for m in ctx.history[-8:]]
    lines.append(f"Student's latest reply: \"{reply}\"")
    data = llm.ask_json(backend, SYSTEM, "\n".join(lines), SCHEMA, "judge", fast=True)
    given = {c["id"]: bool(c["met"]) for c in data["criteria"]}
    return {"met": {c["id"]: given.get(c["id"], False) for c in crit}, "reason": data["reason"], "source": backend}
