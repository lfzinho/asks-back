"""The mediation ladder for one follow-up question, as a small state machine over a plain dict.

    N0 (the trigger's question) -> reply -> all targets met? done
                                         -> otherwise N1 hint -> reply -> ... -> N3 hint -> reply -> done
    met with help (N1..N3)  -> one unaided transfer question -> reply -> done
    G3 (clarification) asks once: clarifying is not helping, so it gets no hints.

Each target criterion records the level at which the student first met it; scoring.py turns
those levels into points. The item holds the rubric targets, so it is stored with the teacher's
copy only; the student sees `messages`.
"""

from __future__ import annotations

import time

from .config import settings
from .followup import Context, write
from .judge import judge


def context(item: dict, question: dict, language: str = "English") -> Context:
    return Context(question=question, answer=item["answer"], trigger=item["trigger"], type=item["type"],
                   targets=item["targets"], misconception=item.get("misconceptionEntry"), reason=item["reason"],
                   history=[{"role": m["role"], "text": m["text"]} for m in item["messages"]], language=language)


def _say(item: dict, level, ctx: Context, backend: str) -> None:
    out = write(level, ctx, backend)
    item["messages"].append({"role": "tutor", "level": level, "kind": _kind(level), "text": out["text"],
                             "source": out["source"], "at": time.time()})
    item.setdefault("checks", []).append({"level": level, "source": out["source"], "attempts": out.get("attempts", []),
                                          "problems": out.get("problems", [])})


def _kind(level) -> str:
    return {0: "question", 1: "hint", 2: "hint", 3: "hint", "transfer": "transfer"}[level]


def start(candidate: dict, question: dict, answer: str, bank_entry: dict | None, backend: str = "mock",
          language: str = "English") -> dict:
    """A new item with its N0 question already written."""
    item = {
        "question": candidate["question"], "trigger": candidate["trigger"], "type": candidate["type"],
        "name": candidate["name"], "reason": candidate["reason"], "impact": candidate["impact"],
        "targets": candidate["targets"], "misconception": candidate.get("misconception"),
        "misconceptionEntry": bank_entry, "answer": answer, "quote": candidate.get("quote", ""),
        "level": 0, "phase": "ladder", "met": {}, "transfer": None, "reached": None, "messages": [],
    }
    _say(item, 0, context(item, question, language), backend)
    return item


def reply(item: dict, text: str, question: dict, backend: str = "mock", cfg: dict | None = None,
          language: str = "English") -> dict:
    """Record the student's reply and move the ladder on. Returns the judgment."""
    cfg = settings(cfg)
    ctx = context(item, question, language)
    level = item["level"]
    item["messages"].append({"role": "student", "level": level if item["phase"] == "ladder" else "transfer",
                             "kind": "reply", "text": text.strip(), "at": time.time()})
    if item["phase"] == "transfer":
        j = judge(text, ctx, transfer=True, backend=backend)
        item["transfer"] = all(j["met"].values())
        item["phase"] = "done"
        item.setdefault("judgments", []).append({"level": "transfer", **j})
        return j

    j = judge(text, ctx, backend=backend)
    item.setdefault("judgments", []).append({"level": level, **j})
    for cid, ok in j["met"].items():
        if ok and cid not in item["met"]:
            item["met"][cid] = level
    if all(t in item["met"] for t in item["targets"]):
        item["reached"] = level
        if level > 0 and item["trigger"] != "G3":
            item["phase"] = "transfer"
            _say(item, "transfer", context(item, question, language), backend)
        else:
            item["phase"] = "done"
    elif item["trigger"] == "G3" or level >= min(3, cfg["max_hints"]):
        item["phase"] = "done"
    else:
        item["level"] = level + 1
        _say(item, item["level"], context(item, question, language), backend)
    return j


def expire(item: dict) -> None:
    """The reply window closed: whatever was not reached stays not reached."""
    if item["phase"] != "done":  # a success before the transfer question stands; the transfer stays unknown
        item["phase"] = "done"
        item["expired"] = True


def done(item: dict) -> bool:
    return item["phase"] == "done"
