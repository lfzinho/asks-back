"""Plain text helpers shared by grading, triggers, question checks and reply judging."""

from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher


def normalize(text: str) -> str:
    """Lower case, no accents, punctuation turned into spaces: "O(log n)!" -> "o log n"."""
    t = unicodedata.normalize("NFKD", text or "")
    t = "".join(ch for ch in t if not unicodedata.combining(ch)).lower()
    return " ".join(re.sub(r"[^a-z0-9]+", " ", t).split())


def mentions(text: str, terms: list[str]) -> bool:
    """True when any of the terms appears in the text, ignoring case and punctuation.

    Tolerant of what OCR does to handwriting: words run together ("mustbesorted") and single
    letters misread ("erashes" for "crashes"). Short terms must match as whole words."""
    norm = normalize(text)
    padded, squashed, tokens = f" {norm} ", norm.replace(" ", ""), norm.split()
    for term in terms:
        t = normalize(term)
        if not t:
            continue
        if f" {t} " in padded:
            return True
        if len(t.replace(" ", "")) >= 4 and t.replace(" ", "") in squashed:
            return True
        if " " not in t and len(t) >= 5 and any(
                abs(len(w) - len(t)) <= 1 and SequenceMatcher(None, w, t).ratio() >= 0.85 for w in tokens):
            return True
    return False


def words(text: str) -> list[str]:
    return normalize(text).split()


def quote_of(answer: str, max_words: int = 8) -> str:
    """A short verbatim piece of the student's answer to quote back to them."""
    clean = " ".join((answer or "").split())
    parts = [p.strip() for p in re.split(r"(?<=[.;!?])\s+", clean) if p.strip()]
    first = parts[0] if parts else clean
    ws = first.split()
    return " ".join(ws[:max_words]).rstrip(",;:.") + ("…" if len(ws) > max_words else "")
