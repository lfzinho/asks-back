"""Decide where the written answer is not enough evidence: the five follow-up triggers.

Works on plain dicts (an exam's questions and one student's graded results), so the worker,
the demo seed and the tests share it. Each candidate has an *impact*: how many points its
follow-up could change. One trigger is kept per question, then the largest impacts, up to
the per-student limit.
"""

from __future__ import annotations

import re
import statistics
from dataclasses import asdict, dataclass

from .config import TRIGGER_ORDER, TRIGGERS, settings
from .text import mentions, quote_of


@dataclass
class Candidate:
    question: str
    trigger: str  # G1..G5
    reason: str  # for the teacher
    impact: float  # points the follow-up could change
    targets: list[str]  # criterion ids the follow-up is about ("transfer" for G5)
    misconception: str | None = None  # bank id, for G4
    quote: str = ""  # what the student wrote, to quote back

    def to_dict(self) -> dict:
        return {**asdict(self), "type": TRIGGERS[self.trigger]["type"], "name": TRIGGERS[self.trigger]["name"]}


def answer_text(result: dict) -> str:
    return " ".join(t.get("text", "") for t in result.get("transcription") or []).strip()


# ---------- G5: style against the student's own baseline ----------

FEATURE_FLOOR = {"word_length": 0.6, "sentence_length": 4.0, "long_words": 0.08, "variety": 0.1, "punctuation": 0.1}
FEATURE_NAMES = {"word_length": "longer words", "sentence_length": "longer sentences", "long_words": "more long words",
                 "variety": "a richer vocabulary", "punctuation": "more elaborate punctuation"}


def style_features(text: str) -> dict | None:
    # Tokens of 14+ letters are almost always words that OCR ran together, not real vocabulary.
    ws = [w for w in re.findall(r"[A-Za-zÀ-ÿ]+", text) if len(w) < 14]
    if len(ws) < 5:
        return None
    sentences = [s for s in re.split(r"(?<=[.!?])\s+(?=[A-Z])", text) if s.strip()] or [text]  # "e.g. x" stays one
    return {
        "word_length": sum(len(w) for w in ws) / len(ws),
        "sentence_length": len(ws) / len(sentences),
        "long_words": sum(1 for w in ws if len(w) >= 8) / len(ws),
        "variety": len({w.lower() for w in ws}) / len(ws),
        "punctuation": len(re.findall(r"[,;:()]", text)) / len(ws),
    }


def style_outliers(texts: dict[str, str], cfg: dict) -> dict[str, list[str]]:
    """Answers whose style is far from the same student's other answers: qid -> features that stand out."""
    feats = {qid: f for qid, t in texts.items() if (f := style_features(t))}
    out = {}
    for qid, f in feats.items():
        others = [g for k, g in feats.items() if k != qid]
        if len(others) < 2:
            continue
        far = []
        for name, value in f.items():
            vals = [g[name] for g in others]
            spread = max(statistics.pstdev(vals), FEATURE_FLOOR[name])
            if (value - statistics.mean(vals)) / spread >= cfg["style_z"]:  # only "more elaborate than usual"
                far.append(name)
        if len(far) >= cfg["style_min_features"]:
            out[qid] = far
    return out


# ---------- all candidates ----------

def candidates(questions: list[dict], results: dict[str, dict], bank: list[dict], cfg: dict | None = None) -> list[Candidate]:
    cfg = settings(cfg)
    texts = {q["id"]: answer_text(results.get(q["id"]) or {}) for q in questions if q.get("type") == "open"}
    outliers = style_outliers(texts, cfg)
    out: list[Candidate] = []
    for q in questions:
        r = results.get(q["id"]) or {}
        if q.get("type") != "open" or r.get("score") is None:
            continue
        qid, pts, score = q["id"], float(q.get("points") or 0), float(r["score"])
        text = texts.get(qid, "")
        if not text:
            continue
        quote = quote_of(text)
        crit = {c["id"]: c for c in q.get("criteria") or []}
        met = {c["criterion_id"]: bool(c.get("met")) for c in r.get("criteria") or []}
        unmet = [cid for cid, c in crit.items() if c.get("points", 0) > 0 and not met.get(cid)]
        answers = [cid for cid, c in crit.items() if c.get("kind", "answer") == "answer" and c.get("points", 0) > 0]
        reasoning = [cid for cid, c in crit.items() if c.get("kind") == "reasoning" and c.get("points", 0) > 0]
        missing = max(0.0, pts - score)

        # G1: the answer is right but the reasoning is not on the paper.
        g1 = False
        if answers and all(met.get(cid) for cid in answers):
            unmet_reasoning = [cid for cid in reasoning if not met.get(cid)]
            if unmet_reasoning or r.get("justification") in ("missing", "generic"):
                g1 = True
                targets = unmet_reasoning or reasoning or answers
                impact = sum(crit[c]["points"] for c in unmet_reasoning) or pts / 2
                why = "no reasoning" if r.get("justification") == "missing" else "only a generic reason"
                out.append(Candidate(qid, "G1", f"Right answer, {why} on paper.", impact, targets, quote=quote))

        # G2: some criteria met, not all.
        if not g1 and 0 < score < pts and unmet:
            names = ", ".join(crit[c]["description"].rstrip(".").lower() for c in unmet[:2])
            out.append(Candidate(qid, "G2", f"Partial answer: missing {names}.", missing, unmet, quote=quote))

        # G3: the grade depends on interpretation.
        conf = cfg["confidence_values"].get(r.get("confidence") or "high", 0.9)
        if conf < cfg["confidence_threshold"] and score < pts:  # at full marks a clarification changes nothing
            reason = (r.get("confidenceReason") or "").removeprefix("[mock] ") or "the grader was not sure"
            out.append(Candidate(qid, "G3", f"Ambiguous: {reason}.", missing or round(pts * (1 - conf), 2),
                                 unmet or list(crit), quote=quote))

        # G4: the answer matches a catalogued misconception.
        found = [m for m in bank if m.get("question") in (None, qid) and
                 (m["id"] in (r.get("misconceptions") or []) or (m.get("phrases") and mentions(text, m["phrases"])))]
        if found:
            m = found[0]
            out.append(Candidate(qid, "G4", f"Matches a known misconception: {m['title'].rstrip('.').lower()}.",
                                 missing or pts / 2, unmet or list(crit), misconception=m["id"], quote=quote))

        # G5: the style is far from the student's other answers. Verify understanding, never accuse.
        if qid in outliers and score > 0:
            feats = " and ".join(FEATURE_NAMES[f] for f in outliers[qid][:2])
            out.append(Candidate(qid, "G5", f"Written differently from this student's other answers ({feats}); "
                                 "worth checking the understanding behind it.", score, ["transfer"], quote=quote))
    return out


def select(cands: list[Candidate], cfg: dict | None = None) -> list[Candidate]:
    """One trigger per question (largest impact, ties by trigger order), then the top questions by impact."""
    cfg = settings(cfg)
    rank = {t: i for i, t in enumerate(TRIGGER_ORDER)}
    best: dict[str, Candidate] = {}
    for c in sorted(cands, key=lambda c: (-c.impact, rank[c.trigger])):
        best.setdefault(c.question, c)
    chosen = sorted(best.values(), key=lambda c: (-c.impact, rank[c.trigger]))
    return chosen[: cfg["max_questions"]]


def detect(questions: list[dict], results: dict[str, dict], bank: list[dict], cfg: dict | None = None
           ) -> tuple[list[Candidate], list[Candidate]]:
    """(selected follow-ups, every candidate found). The teacher sees both."""
    allc = candidates(questions, results, bank, cfg)
    return select(allc, cfg), allc
