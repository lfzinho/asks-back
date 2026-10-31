"""The three scores and the profile. Plain arithmetic over the graded results and the follow-up
items: no model is involved here, so the same conversation always gives the same numbers.

  real       the written grade; a G3 clarification can raise it ("adjusted real"), since clarifying is not helping
  mediated   real + points recovered in the follow-up, each weighted by the help level it needed
  potential  (mediated - real) / (max - real)
"""

from __future__ import annotations

from .config import PROFILES, TRIGGERS, settings


def _weight(level: int, transfer: bool | None, cfg: dict) -> float:
    if transfer is False:  # did not carry the idea to a new case without help: one level less credit
        level += 1
    return cfg["weights"].get(str(level), 0.0) if level <= 3 else 0.0


def verified(item: dict) -> bool:
    """A verification follow-up (G1/G5) counts as verified when reached with at most an implicit hint."""
    return item.get("reached") is not None and item["reached"] <= 1 and item.get("transfer") is not False


def question_scores(question: dict, result: dict, item: dict | None, cfg: dict) -> dict:
    pts = float(question.get("points") or 0)
    real = float(result.get("score") or 0)
    out = {"max": pts, "real": real, "adjustedReal": real, "mediated": real, "trigger": None, "level": None,
           "transfer": None, "recovered": 0.0}
    if not item:
        return out
    crit = {c["id"]: float(c.get("points") or 0) for c in question.get("criteria") or []}
    met = item.get("met") or {}
    out.update(trigger=item["trigger"], level=item.get("reached"), transfer=item.get("transfer"))
    if item["trigger"] == "G3":
        clarified = sum(crit.get(cid, 0) for cid in met)
        out["adjustedReal"] = out["mediated"] = min(pts, real + clarified)
        return out
    recovered = sum(crit.get(cid, 0) * _weight(level, item.get("transfer"), cfg) for cid, level in met.items())
    out["recovered"] = round(recovered, 3)
    out["mediated"] = min(pts, real + recovered)
    return out


def student_scores(questions: list[dict], results: dict[str, dict], items: list[dict], cfg: dict | None = None,
                   finished: bool = True) -> dict:
    """Scores and profile for one student. `finished` is False while follow-ups are still open."""
    cfg = settings(cfg)
    by_q = {i["question"]: i for i in items}
    per = {q["id"]: question_scores(q, results.get(q["id"]) or {}, by_q.get(q["id"]), cfg) for q in questions}
    mx = sum(p["max"] for p in per.values())
    real = sum(p["real"] for p in per.values())
    adj = sum(p["adjustedReal"] for p in per.values())
    med = sum(p["mediated"] for p in per.values())
    potential = round((med - adj) / (mx - adj), 3) if mx - adj > 1e-9 else None
    levels = [lvl for i in items if i["trigger"] != "G3" for lvl in (i.get("met") or {}).values()]
    max_help = max(levels) if levels else None
    out = {"max": mx, "real": round(real, 3), "adjustedReal": round(adj, 3), "mediated": round(med, 3),
           "potential": potential, "maxHelp": max_help, "perQuestion": per, "followups": len(items)}
    if items and not finished:
        out.update(profile=None, profileLabel="Waiting for follow-up", action="", why="Follow-up still open.")
        return out
    key, why = profile(adj, mx, potential, max_help, items, cfg)
    out.update(profile=key, profileLabel=PROFILES[key]["label"], action=PROFILES[key]["action"], why=why)
    return out


def profile(adj: float, mx: float, potential: float | None, max_help: int | None, items: list[dict],
            cfg: dict) -> tuple[str, str]:
    share = adj / mx if mx else 0
    if share >= cfg["high_real"]:
        doubtful = [i for i in items if TRIGGERS[i["trigger"]]["verifies"] and not verified(i)]
        if doubtful:
            qs = ", ".join(i["question"].upper() for i in doubtful)
            return "verify", f"High written score ({share:.0%}), but the follow-up on {qs} did not confirm it without help."
        return "mastered", f"High written score ({share:.0%})" + (", confirmed in the follow-up." if items else ".")
    if not items:
        return "not_reached", f"Low written score ({share:.0%}) and no answer where a follow-up could add evidence."
    if potential and potential >= cfg["almost_potential"] and max_help is not None and max_help <= 1:
        help_ = "no help" if max_help == 0 else "an implicit hint"
        return "almost", f"Recovered {potential:.0%} of the missing points with {help_}."
    if potential and potential > 0:
        return "building", f"Recovered {potential:.0%} of the missing points, needing hints up to N{max_help}."
    return "not_reached", "Did not recover points in the follow-up, even with explicit hints."


def class_summary(students: list[dict], cfg: dict | None = None) -> dict:
    """Profile counts and the demo metrics over a class (each entry: {"scores": student_scores(...), "teacherProfile"})."""
    done = [s for s in students if (s.get("scores") or {}).get("profile")]
    counts = {k: sum(1 for s in done if s["scores"]["profile"] == k) for k in PROFILES}
    low = [s for s in done if s["scores"]["adjustedReal"] < settings(cfg)["high_real"] * s["scores"]["max"]]
    judged = [s for s in done if s.get("teacherProfile")]
    agree = sum(1 for s in judged if s["teacherProfile"] == s["scores"]["profile"])
    return {
        "students": len(students), "profiled": len(done), "counts": counts,
        "almostBehindLowGrade": counts["almost"], "lowGrade": len(low),
        "almostShare": round(counts["almost"] / len(done), 3) if done else None,
        "almostShareOfLow": round(counts["almost"] / len(low), 3) if low else None,
        "teacherJudged": len(judged), "agreement": round(agree / len(judged), 3) if judged else None,
    }
