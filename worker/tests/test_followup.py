"""Triggers, question checks, the mediation ladder, scoring and profiles (no OCR, no model calls)."""

from __future__ import annotations

import pytest

from asksback import ladder
from asksback.config import settings
from asksback.demo import CLASSMATES, play, start_items, typed_results
from asksback.followup import Context, check, template
from asksback.scoring import class_summary, question_scores, student_scores
from asksback.synth import BANK, _master_pages, exam_definition
from asksback.triggers import detect, style_outliers


@pytest.fixture(scope="module")
def questions():
    return exam_definition(_master_pages()[1])["questions"]


def by_name(name):
    return next(c for c in CLASSMATES if c["name"] == name)


def results_of(questions, name):
    c = by_name(name)
    return typed_results(questions, c["mcq"], c["answers"])


# ---------- triggers ----------

def test_bare_answers_trigger_justification_and_elaboration(questions):
    selected, _ = detect(questions, results_of(questions, "Heitor Ramos"), BANK)
    assert [(c.question, c.trigger) for c in selected] == [("q5", "G1"), ("q6", "G1"), ("q7", "G2")]
    assert selected[0].targets == ["halving", "sorted"] and selected[0].impact == 2


def test_known_misconception_wins_over_justification(questions):
    selected, everything = detect(questions, results_of(questions, "João Pereira"), BANK)
    assert {(c.question, c.trigger) for c in everything} >= {("q5", "G1"), ("q5", "G4")}
    q5 = next(c for c in selected if c.question == "q5")
    assert q5.trigger == "G4" and q5.misconception == "bs-any-array"


def test_full_marks_never_get_a_follow_up(questions):
    assert detect(questions, results_of(questions, "Felipe Costa"), BANK)[0] == []


def test_ambiguous_word_asks_for_clarification(questions):
    selected, _ = detect(questions, results_of(questions, "Rafael Teixeira"), BANK)
    assert [(c.question, c.trigger) for c in selected] == [("q6", "G3")]


def test_style_far_from_own_answers_is_an_understanding_check(questions):
    selected, _ = detect(questions, results_of(questions, "Paula Ribeiro"), BANK)
    assert [(c.question, c.trigger) for c in selected] == [("q7", "G5")]
    reason = selected[0].reason.lower()
    for word in ("cheat", "plagiar", "ai-generated", "copied"):
        assert word not in reason


def test_style_needs_two_other_answers_and_only_flags_more_elaborate_writing():
    long = "A stack constitutes a last-in, first-out abstraction, whereas a queue implements first-in semantics."
    assert style_outliers({"q5": "it halves the array each time ok", "q7": long}, settings()) == {}
    texts = {"q5": "it halves the array each time ok", "q6": "it crashes, the stack gets full", "q7": long}
    assert list(style_outliers(texts, settings())) == ["q7"]
    texts["q7"] = "ok"  # shorter than usual is never flagged
    assert style_outliers(texts, settings()) == {}


def test_at_most_three_follow_ups(questions):
    many = [{**q, "id": f"{q['id']}{k}"} for k in "ab" for q in questions if q["type"] == "open"]
    res = typed_results(questions, {}, {"q5": "O(log n)", "q6": "It crashes.", "q7": "A stack is LIFO."})
    res = {f"{qid}{k}": r for k in "ab" for qid, r in res.items()}
    selected, everything = detect(many, res, [])
    assert len(everything) == 6 and len(selected) == 3


# ---------- question quality ----------

def ctx_for(questions, trigger="G1", answer="It is O(log n).", targets=("halving", "sorted"), misconception=None):
    q = next(q for q in questions if q["id"] == "q5")
    types = {"G1": "justification", "G2": "elaboration", "G3": "clarification", "G4": "misconception", "G5": "transfer"}
    return Context(q, answer, trigger, types[trigger], list(targets), misconception)


@pytest.mark.parametrize("trigger", ["G1", "G2", "G3", "G4", "G5"])
def test_every_template_passes_the_checklist(questions, trigger):
    m = BANK[0] if trigger == "G4" else None
    targets = ["transfer"] if trigger == "G5" else ["halving", "sorted"]
    ctx = ctx_for(questions, trigger, targets=targets, misconception=m)
    for level in (0, 1, 2, 3, "transfer"):
        assert check(template(level, ctx), level, ctx) == [], (trigger, level, template(level, ctx))


def test_checklist_catches_each_rule(questions):
    ctx = ctx_for(questions)
    assert "closed" in check('You wrote "It is O(log n)". Is that right?', 0, ctx)[0]
    assert any("not contextual" in p for p in check("What happens at each step of the search?", 0, ctx))
    assert any("gives the answer away" in p for p in check(
        'You wrote "It is O(log n)". Is it because the array is sorted and halves each time, and why?', 0, ctx))
    assert any("one question" in p for p in check('You wrote "It is O(log n)". Why? How?', 0, ctx))
    assert any("benevolent" in p for p in check('You wrote "It is O(log n)". Did you copy from a classmate? Why?', 0, ctx))
    # explicit hints may name the answer
    assert check("Each comparison throws away half of a sorted array. How many steps are left?", 3, ctx) == []


# ---------- ladder ----------

def test_success_with_help_asks_a_transfer_question(questions):
    q5 = next(q for q in questions if q["id"] == "q5")
    cand = {"question": "q5", "trigger": "G1", "type": "justification", "name": "x", "reason": "r", "impact": 2,
            "targets": ["halving", "sorted"]}
    item = ladder.start(cand, q5, "It is O(log n).", None)
    assert [m["level"] for m in item["messages"]] == [0]
    ladder.reply(item, "It gets smaller.", q5)
    assert item["level"] == 1 and item["messages"][-1]["kind"] == "hint"
    ladder.reply(item, "It halves the interval each step.", q5)  # one target met at N1
    assert item["met"] == {"halving": 1} and item["level"] == 2
    ladder.reply(item, "And it must be sorted.", q5)
    assert item["met"] == {"halving": 1, "sorted": 2} and item["reached"] == 2 and item["phase"] == "transfer"
    ladder.reply(item, "You flip the comparison.", q5)
    assert item["transfer"] is True and ladder.done(item)


def test_ladder_stops_after_three_hints(questions):
    q5 = next(q for q in questions if q["id"] == "q5")
    cand = {"question": "q5", "trigger": "G1", "type": "justification", "name": "x", "reason": "r", "impact": 2,
            "targets": ["halving"]}
    item = ladder.start(cand, q5, "It is O(log n).", None)
    for _ in range(4):
        ladder.reply(item, "I don't know.", q5)
    assert ladder.done(item) and item["reached"] is None
    assert [m["level"] for m in item["messages"] if m["role"] == "tutor"] == [0, 1, 2, 3]


def test_clarification_is_asked_once_without_hints(questions):
    res = results_of(questions, "Rafael Teixeira")
    items, _ = start_items(questions, res, BANK)
    play(items, questions, {"q6": ["I'm not sure."]})
    assert [m["level"] for m in items[0]["messages"]] == [0, 0]


# ---------- scoring ----------

def test_mediated_credit_follows_the_weights():
    q = {"id": "q", "points": 3, "criteria": [{"id": "a", "points": 1}, {"id": "b", "points": 1}, {"id": "c", "points": 1}]}
    cfg = settings()
    item = {"trigger": "G2", "met": {"b": 0, "c": 2}, "reached": 2, "transfer": True}
    s = question_scores(q, {"score": 1}, item, cfg)
    assert s["mediated"] == pytest.approx(1 + 1.0 + 0.5)
    s = question_scores(q, {"score": 1}, {**item, "transfer": False}, cfg)  # one level less credit
    assert s["mediated"] == pytest.approx(1 + 0.75 + 0.25)
    s = question_scores(q, {"score": 1}, {**item, "trigger": "G3"}, cfg)  # clarifying adjusts the real score
    assert s["adjustedReal"] == s["mediated"] == 3


def test_teacher_weights_change_the_scores(questions):
    res = results_of(questions, "Larissa Moreira")
    items, _ = start_items(questions, res, BANK)
    play(items, questions, by_name("Larissa Moreira")["script"])
    default = student_scores(questions, res, items)
    generous = student_scores(questions, res, items, {"weights": {"2": 1.0}})
    assert generous["mediated"] > default["mediated"]


def test_open_follow_ups_hold_the_profile(questions):
    res = results_of(questions, "Heitor Ramos")
    items, _ = start_items(questions, res, BANK)
    assert student_scores(questions, res, items, finished=False)["profile"] is None


# ---------- the demo class ----------

def test_demo_class_shows_every_profile(questions):
    students = []
    for c in CLASSMATES:
        res = typed_results(questions, c["mcq"], c["answers"])
        items, _ = start_items(questions, res, BANK)
        play(items, questions, c["script"])
        students.append({"name": c["name"], "scores": student_scores(questions, res, items)})
    got = {s["name"]: s["scores"]["profile"] for s in students}
    assert got["Heitor Ramos"] == got["Isabela Freitas"] == "almost"
    assert got["João Pereira"] == got["Tiago Cardoso"] == "building"
    assert got["Mateus Barros"] == got["Natália Gomes"] == "not_reached"
    assert got["Otávio Souza"] == got["Paula Ribeiro"] == "verify"
    assert got["Felipe Costa"] == got["Rafael Teixeira"] == "mastered"
    summary = class_summary(students + [{"scores": students[0]["scores"], "teacherProfile": "mastered"}])
    assert all(v > 0 for v in summary["counts"].values())
    assert summary["agreement"] == 1.0
