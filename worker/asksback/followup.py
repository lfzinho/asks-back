"""Write follow-up questions and hints, and check them against the quality checklist.

The question *type* is fixed by the trigger (every student flagged by G1 gets a justification
question); the *content* is adapted to what the student wrote. Each generated text is checked
by rules (and, with a model, by a short second pass); a failing text is regenerated, and after
two failures replaced by the trigger's template, which always passes.

Levels: 0 is the question itself, 1 an implicit hint, 2 a conceptual hint, 3 an explicit hint.
"transfer" is the unaided "what would change if...?" question asked after success with help.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from . import llm
from .text import mentions, normalize, quote_of

# Never in student- or teacher-facing text (the G5 rule), plus words that tell the student they failed.
BANNED = ["cheat", "cheating", "cheated", "plagiarism", "plagiarize", "plagiarized", "ai generated", "ai-generated",
          "copied", "copy from", "you were wrong", "you are wrong", "your answer is wrong", "is incorrect", "your mistake",
          "you made a mistake", "error in your", "you failed"]
CLOSED_STARTS = ("do", "does", "did", "is", "are", "was", "were", "can", "could", "would", "will", "have", "has",
                 "should", "shall", "am", "isn't", "aren't", "don't", "doesn't")
OPEN_WORDS = ("why", "how", "what", "which", "explain", "describe", "tell", "walk me", "in your own words", "where",
              "when")
MAX_WORDS = 70
REGENERATIONS = 2

TEMPLATES = {
    # N0 per question type. {quote} is the student's own words.
    "justification": 'You wrote "{quote}". What makes that true? Walk me through the reasoning behind it.',
    "elaboration": 'You wrote "{quote}". What else would you add so the answer covers the whole question?',
    "clarification": 'You wrote "{quote}". When you say "{term}", what exactly do you mean?',
    "misconception": 'You wrote "{quote}". A classmate said that {claim}. What would you tell them, and why?',
    "transfer": 'You wrote "{quote}". {transfer}',
}
GENERIC_HINTS = [
    'Re-read what you wrote: "{quote}". Which part of the question does it not cover yet?',
    "Think about this idea: {concept}.",
    "Here is a model to start from: {model} Now, in your own words, how does that answer the question?",
]
TRANSFER_HINTS = [  # G5: the target is the transfer question itself
    'Re-read your own answer: "{quote}". Which part of it applies to this new situation?',
    "Think about the key idea of the question, {concept}, and apply it to this new situation.",
    "Here is a model to start from: {model} Now, how does that idea play out in this new situation?",
]
GENERIC_TRANSFER = "Imagine a slightly different version of this question. What would change in your answer, and why?"


@dataclass
class Context:
    """Everything a follow-up text may depend on. Rubric details never reach the student unless a hint uses them."""
    question: dict  # exam question (prompt, answer_key, criteria, transfer)
    answer: str  # what the student wrote
    trigger: str  # G1..G5
    type: str  # justification | elaboration | clarification | misconception | transfer
    targets: list[str]  # criterion ids the follow-up is about
    misconception: dict | None = None  # bank entry, for G4
    reason: str = ""  # why the trigger fired
    history: list[dict] = field(default_factory=list)  # [{role, text}] so far
    language: str = "English"

    @property
    def target_criteria(self) -> list[dict]:
        return [c for c in self.question.get("criteria") or [] if c["id"] in self.targets]

    def giveaway_terms(self) -> list[str]:
        """Answer terms the student has not used yet: a question at N0/N1 must not contain them."""
        terms = [t for c in self.target_criteria for t in c.get("look_for") or []]
        claim = (self.misconception or {}).get("classmate_claim") or ""  # the claim itself is the G4 question
        return [t for t in terms if len(normalize(t)) >= 4 and not mentions(self.answer, [t]) and not mentions(claim, [t])]


# ---------- the checklist, as rules ----------

def check(text: str, level: int | str, ctx: Context) -> list[str]:
    """Problems with a follow-up text; an empty list means it passes."""
    problems = []
    t = normalize(text)
    if not t:
        return ["empty"]
    hit = [w for w in BANNED if f" {normalize(w)} " in f" {t} "]
    if hit:
        problems.append(f"not benevolent: uses {', '.join(hit)}")
    if len(t.split()) > MAX_WORDS:
        problems.append("too long")
    if text.count("?") > 1:
        problems.append("more than one question (one idea per question)")
    if level in (0, "transfer") and "?" not in text:
        problems.append("does not ask anything")
    if "?" in text:  # hints may be statements; anything asked must be open
        last = [s for s in re.split(r"(?<=[.!?])\s+", text.strip()) if "?" in s]
        ask = normalize(last[-1] if last else text)
        if ask and ask.split()[0] in CLOSED_STARTS and not any(w in ask for w in OPEN_WORDS):
            problems.append("closed: can be answered with yes or no")
    if level in (0, 1):
        leaked = [w for w in ctx.giveaway_terms() if mentions(text, [w])]
        if leaked:
            problems.append(f"gives the answer away: {', '.join(leaked[:3])}")
    if level == 0 and ctx.answer.strip():
        if not _quotes(text, ctx.answer):
            problems.append("not contextual: does not quote the student's answer")
    return problems


def _quotes(text: str, answer: str) -> bool:
    """Contains at least three consecutive words of the answer (or all of it, if shorter)."""
    a, t = normalize(answer).split(), f" {normalize(text)} "
    n = min(3, len(a))
    return any(f" {' '.join(a[i:i + n])} " in t for i in range(len(a) - n + 1))


# ---------- templates (offline, and the fallback for every backend) ----------

def template(level: int | str, ctx: Context) -> str:
    quote = quote_of(ctx.answer)
    if level == 0:
        m = ctx.misconception or {}
        transfer = (ctx.question.get("transfer") or {}).get("prompt") or GENERIC_TRANSFER
        term = _ambiguous_term(ctx) or quote
        return TEMPLATES[ctx.type].format(quote=quote, term=term, transfer=transfer,
                                          claim=m.get("classmate_claim") or (m.get("title") or "").lower())
    if level == "transfer":
        return (ctx.question.get("transfer") or {}).get("prompt") or GENERIC_TRANSFER
    if ctx.targets == ["transfer"]:
        first = (ctx.question.get("criteria") or [{}])[0]
        return TRANSFER_HINTS[level - 1].format(quote=quote, concept=(first.get("description") or "").rstrip(".").lower(),
                                                model=ctx.question.get("answer_key") or "")
    authored = [c["hints"][level - 1] for c in ctx.target_criteria if len(c.get("hints") or []) >= level]
    if ctx.misconception and level == 2 and ctx.misconception.get("concept"):
        return f"Think about {ctx.misconception['concept']}."
    if authored:
        return authored[0]
    first = (ctx.target_criteria or ctx.question.get("criteria") or [{}])[0]
    return GENERIC_HINTS[level - 1].format(quote=quote, concept=(first.get("description") or "").rstrip(".").lower(),
                                           model=ctx.question.get("answer_key") or first.get("description") or "")


def _ambiguous_term(ctx: Context) -> str | None:
    from .grader import VAGUE

    t = normalize(ctx.answer)
    return next((v for v in VAGUE if re.search(rf"\b{v}\b", t)), None)


# ---------- model generation ----------

SYSTEM = """You write one short follow-up message to a student after a written exam, on behalf of their teacher.
The follow-up exists because the written answer was not enough evidence of what the student understands.

Rules (all of them, always):
- Benevolent: neutral, warm tone. Never suggest the student was wrong, careless or dishonest. Never mention \
copying, cheating, plagiarism or AI tools.
- Necessary: ask only about what would change the score or the diagnosis (the target criteria).
- Contextual: at level 0, quote a few of the student's own words, in quotation marks.
- Open: the student must not be able to answer with yes or no. End with a "why/how/what" question.
- No giveaways: at levels 0 and 1, do not state or hint at the expected answer, and do not use the \
answer's key terms unless the student already used them.
- One idea: exactly one question mark.
- At most 45 words. Write in the language given. Plain text, no lists.

The question type is fixed by the trigger:
- justification (G1): ask for the reasoning behind a correct answer.
- elaboration (G2): ask for the part of the answer that is missing, without saying what it is.
- clarification (G3): ask what a specific, ambiguous word or phrase in the answer means.
- misconception (G4): present the misconception as something "a classmate said" and ask what they would tell them and why.
- transfer (G5, and the transfer check): a "what would change if...?" variation of the question.

Levels of help (the mediation ladder):
- level 1, implicit hint: direct the student's attention to part of their own answer or the question, without naming the concept.
- level 2, conceptual hint: name the concept that matters, without giving the answer.
- level 3, explicit hint: offer a model or worked step, then ask the student to finish the reasoning.
- transfer: a new, unaided "what would change if...?" question on the same idea.
The teacher may provide a suggested text for the level; adapt it to this student's answer and conversation."""

SCHEMA = {"type": "object", "additionalProperties": False, "required": ["text"], "properties": {"text": {"type": "string"}}}

CHECK_SYSTEM = """You review one follow-up message a teacher's assistant wants to send to a student. Answer two questions:
benevolent: is the tone neutral and kind, with no suggestion that the student was wrong, careless or dishonest?
necessary: does it ask only about what the target criteria need, nothing unrelated?"""
CHECK_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["benevolent", "necessary", "note"],
                "properties": {"benevolent": {"type": "boolean"}, "necessary": {"type": "boolean"},
                               "note": {"type": "string"}}}


def _prompt(level: int | str, ctx: Context, problems: list[str]) -> str:
    q = ctx.question
    lines = [f"Language: {ctx.language}", f"Question: {q.get('prompt') or '(see the exam)'}",
             f"Model answer (for you only): {q.get('answer_key') or '(none)'}",
             "Target criteria (what the follow-up is about):"]
    lines += [f"- {c['description']}" for c in ctx.target_criteria] or ["- the whole answer"]
    lines += [f"Student's written answer: \"{ctx.answer}\"", f"Trigger: {ctx.trigger} ({ctx.reason})",
              f"Question type: {ctx.type}", f"Level: {level}"]
    if ctx.misconception:
        lines.append(f"Misconception: {ctx.misconception['title']}. As a classmate's claim: "
                     f"{ctx.misconception.get('classmate_claim') or ctx.misconception['title']}")
    suggestion = template(level, ctx)
    lines.append(f"Teacher's suggested text: {suggestion}")
    if ctx.history:
        lines.append("Conversation so far:")
        lines += [f"{'Student' if m['role'] == 'student' else 'You'}: {m['text']}" for m in ctx.history[-6:]]
    if problems:
        lines.append("Your previous attempt failed these checks; fix them: " + "; ".join(problems))
    return "\n".join(lines)


def write(level: int | str, ctx: Context, backend: str = "mock") -> dict:
    """The follow-up text for this level, with how it was produced and the checks it passed."""
    tried: list[dict] = []
    if backend in ("claude", "openrouter"):
        problems: list[str] = []
        for _ in range(1 + REGENERATIONS):
            try:
                text = llm.ask_json(backend, SYSTEM, _prompt(level, ctx, problems), SCHEMA, "followup", fast=True)["text"]
            except llm.ModelError as e:
                tried.append({"text": None, "problems": [f"model error: {str(e)[:120]}"]})
                break
            text = " ".join(text.split())
            problems = check(text, level, ctx)
            if not problems:
                problems = _model_check(text, ctx, backend)
            tried.append({"text": text, "problems": problems})
            if not problems:
                return {"text": text, "source": backend, "attempts": tried}
    text = template(level, ctx)
    problems = check(text, level, ctx)
    return {"text": text, "source": "template", "attempts": tried, "problems": problems}


def _model_check(text: str, ctx: Context, backend: str) -> list[str]:
    targets = "; ".join(c["description"] for c in ctx.target_criteria) or "the whole answer"
    try:
        r = llm.ask_json(backend, CHECK_SYSTEM, f"Target criteria: {targets}\nMessage: {text}", CHECK_SCHEMA,
                         "followup_check", fast=True)
    except llm.ModelError:
        return []  # the rule checks already passed; a failed review is not a reason to block
    out = []
    if not r["benevolent"]:
        out.append(f"not benevolent ({r['note']})")
    if not r["necessary"]:
        out.append(f"not necessary ({r['note']})")
    return out
