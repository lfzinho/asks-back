"""The demo class: the five scanned students plus fifteen simulated classmates.

Simulated classmates have typed answers (graded by the same offline rule as scanned ones) and
scripted follow-up replies, played through the real ladder, judge and scoring. Their transcripts
are therefore real engine output; they are labelled "simulated" wherever they appear.

Each script lists the replies to one follow-up question in order: ladder replies first, then
the reply to the transfer question if one is asked. A script that runs out answers "I'm not sure".
"""

from __future__ import annotations

from . import ladder
from .exam import Question
from .grader import offline_grade
from .results import QuestionResult, result_doc
from .triggers import answer_text, detect

DOMAIN = "example.com"
NOT_SURE = "I'm not sure."


def email(name: str) -> str:
    return name.lower().replace(" ", ".") + "@" + DOMAIN


# Replies for the five scanned students (bruno's are only a suggestion: the presenter types live).
SCANNED_SCRIPTS = {
    "Ana Souza": {},
    "Bruno Lima": {
        "q5": ["It just goes up.",
               "The wing is tilted, so when it pushes the air down, the air pushes the wing up.",
               "It flies with the nose up, so the tilted wing still pushes air down."],
        "q6": ["The evaporating water takes heat from my skin."],
        "q7": ["A frozen lake: the ice stays on top and the fish live underneath."],
    },
    "Carla Dias": {
        "q5": ["I agree, the air on top has to catch up.", "It goes faster over the wing.",
               "Oh, the tilted wing pushes the air down, so the air pushes the wing up.", "It just flies."],
        "q6": ["I agree, the water is cold.", "It is wet.",
               "The water evaporates and takes heat from my skin.", "Hmm, no idea."],
    },
    "Diego Alves": {"q5": ["I don't know."], "q7": ["I don't know.", "Not sure.", "No idea.", "I don't know."]},
    "Eva Rocha": {"q7": ["The lake would be fine.", "Nothing would change.", "It would float anyway.", "I'm not sure."]},
}

FULL = {
    "q5": "The tilted wing pushes air down, and the air pushes the wing up (Newton's third law).",
    "q6": "The water on your skin evaporates, and evaporation takes heat from your skin.",
    "q7": "Ice is less dense than liquid water, so lakes freeze on top and icebergs float.",
}
ALL_RIGHT = {"q1": "B", "q2": "C", "q3": "B", "q4": "A"}

CLASSMATES = [
    {"name": "Felipe Costa", "mcq": ALL_RIGHT, "answers": FULL, "script": {}},
    {"name": "Gabriela Nunes", "mcq": ALL_RIGHT, "answers": {
        "q5": "The wing is angled, so it pushes the air down and the air pushes back on the wing.",
        "q6": "Water evaporates from the skin, and that takes heat away from the body.",
        "q7": "Ice is less dense because water expands when it freezes, like icebergs in the sea."}, "script": {}},
    {"name": "Heitor Ramos", "mcq": ALL_RIGHT, "answers": {
        "q5": "The wing pushes air down.", "q6": "Evaporation.", "q7": "Ice is less dense than water."},
     "script": {"q5": ["The tilted wing pushes air down, so the air pushes the wing up."],
                "q6": ["The evaporating water takes heat from my skin."],
                "q7": ["Lakes in winter freeze on the top first."]}},
    {"name": "Isabela Freitas", "mcq": {**ALL_RIGHT, "q3": "A"}, "answers": {
        "q5": "The wing pushes air down because wings are designed for it.", "q6": FULL["q6"],
        "q7": "Ice is less dense than water."},
     "script": {"q5": ["Because that is how wings are made.", "The tilted wing pushes air down, so the air pushes it up.",
                       "It tilts the wing so it still pushes air down."],
                "q7": ["A frozen pond: the ice stays on top."]}},
    {"name": "João Pereira", "mcq": {**ALL_RIGHT, "q1": "A", "q4": "C"}, "answers": {
        "q5": "The wing pushes air down because the air on top goes a longer way.",
        "q6": "The cold from the water goes into your body.", "q7": FULL["q7"]},
     "script": {"q5": ["I agree with them.", "It goes faster on top.",
                       "The tilted wing pushes the air down and the air pushes it up.", "No idea."],
                "q6": ["The water is cold.", "You are wet.", "The water evaporates and takes heat from my skin.",
                       "The sweat evaporates faster."]}},
    {"name": "Larissa Moreira", "mcq": {**ALL_RIGHT, "q2": "B", "q3": "A"}, "answers": {
        "q5": "Because the engines hold the plane up.", "q6": "Evaporation.", "q7": FULL["q7"]},
     "script": {"q5": ["The engines push it.", "The wing pushes air down, so the air pushes it up.",
                       "The wing is tilted.", "It tilts the wing."],
                "q6": ["It dries.", "It just gets cold.", "Evaporating water takes heat from the skin.",
                       "The sweat evaporates faster."]}},
    {"name": "Mateus Barros", "mcq": {"q1": "A", "q2": "B", "q3": "B", "q4": "B"}, "answers": {
        "q5": "Because the engines hold it up.", "q6": "Because the wind is cold.",
        "q7": "Ice floats because it has air inside."},
     "script": {"q5": ["The engines.", "I don't know.", "No idea.", "Not sure."],
                "q7": ["It has air.", "I don't know.", "No idea.", "Not sure."]}},
    {"name": "Natália Gomes", "mcq": {"q1": "C", "q2": "A", "q3": "D", "q4": "A"}, "answers": {
        "q5": "Wings.", "q6": "Cold.", "q7": ""}, "script": {}},
    {"name": "Otávio Souza", "mcq": ALL_RIGHT, "answers": {
        "q5": "The wing pushes air down, it is tilted.", "q6": "Water evaporates and takes heat from you.",
        "q7": "Ice is less dense than water, so icebergs float."},
     "script": {"q5": ["It is just fast.", "It flies.", "It cuts the air.", "The air pushes the wing up.",
                       "I'm not sure."]}},
    {"name": "Paula Ribeiro", "mcq": ALL_RIGHT, "answers": {
        "q5": "pushes air down, air pushes wing up, wing tilted",
        "q6": "it evaporates, takes heat from skin",
        "q7": "Owing to hydrogen bonding, water crystallizes into an open lattice of lower density than the liquid; "
              "consequently, ice accumulates atop lakes, insulating the organisms beneath."},
     "script": {"q7": ["It would be fine.", "The same as before.", "It floats.", "Not sure."]}},
    {"name": "Rafael Teixeira", "mcq": {**ALL_RIGHT, "q3": "C"}, "answers": {
        "q5": FULL["q5"], "q6": "The water on you kind of evaporates and you get colder.", "q7": FULL["q7"]},
     "script": {"q6": ["I mean the evaporating water takes heat from my skin, so my skin cools down."]}},
    {"name": "Sofia Martins", "mcq": {**ALL_RIGHT, "q1": "A", "q2": "B"}, "answers": {
        "q5": "The wing pushes air down.", "q6": "Evaporation.", "q7": FULL["q7"]},
     "script": {"q5": ["The tilted wing pushes the air down, and the air pushes the wing up."],
                "q6": ["The evaporating water takes heat from the skin."]}},
    {"name": "Tiago Cardoso", "mcq": {**ALL_RIGHT, "q2": "D", "q3": "A"}, "answers": {
        "q5": "The wing pushes air down.", "q6": "You are just cold.", "q7": "Ice floats because it has air inside."},
     "script": {"q7": ["It has bubbles.", "It is light.",
                       "Ice is less dense because water expands when it freezes, like icebergs.",
                       "The lake would freeze from the bottom."],
                "q5": ["It is quick.", "It cuts the air.", "Air goes around.",
                       "The air pushes the wing up and the wing is tilted.", "No idea."]}},
    {"name": "Ursula Lopes", "mcq": ALL_RIGHT, "answers": {
        "q5": "The wing meets the air at an angle and deflects it downward; by Newton's third law the air pushes "
              "the wing up.",
        "q6": "Evaporation needs energy, so the evaporating water takes heat from the skin.",
        "q7": "Ice is less dense than water (it expands when it freezes), so icebergs float."}, "script": {}},
    {"name": "Vitor Hugo", "mcq": {**ALL_RIGHT, "q4": "B"}, "answers": {
        "q5": "The wing pushes air down.", "q6": "Evaporation.", "q7": "Ice is less dense than water."},
     "script": {"q5": ["The tilted wing pushes air down, so the air pushes the wing up."],
                "q6": ["Evaporating water takes heat from my skin."],
                "q7": ["Icebergs in the sea."]}},
]


def typed_results(questions: list[dict], mcq: dict, answers: dict) -> dict[str, dict]:
    """Grade typed answers with the offline rule: the same result shape as a scanned page."""
    out = {}
    for qd in questions:
        q = Question.model_validate(qd)
        if q.type == "mcq":
            pick = mcq.get(q.id)
            ok = pick == q.answer
            r = QuestionResult("sim", q.id, "mcq", q.points, q.points if ok else 0.0, "graded",
                               {"selected": pick, "reading": "ok" if pick else "blank", "answer": q.answer})
        else:
            text = answers.get(q.id, "")
            g = offline_grade(q, [text] if text else [], [1.0] if text else [])
            points = {c.id: c.points for c in q.criteria}
            r = QuestionResult("sim", q.id, "open", q.points, g.score, "graded", {
                "transcription": [t.model_dump() for t in g.grade.transcription],
                "criteria": [{**c.model_dump(), "points": points.get(c.criterion_id)} for c in g.grade.criteria],
                "feedback": "Typed answer of a simulated classmate.", "confidence": g.grade.confidence,
                "confidence_reason": g.grade.confidence_reason, "justification": g.grade.justification,
                "misconceptions": g.grade.misconceptions})
        out[q.id] = result_doc(r)
    return out


def start_items(questions: list[dict], results: dict, bank: list[dict], backend: str = "mock", cfg: dict | None = None,
                language: str = "English") -> tuple[list[dict], list[dict]]:
    """Detect triggers and open the follow-up items (N0 written). Returns (items, all candidates)."""
    selected, everything = detect(questions, results, bank, cfg)
    by_q = {q["id"]: q for q in questions}
    items = []
    for c in selected:
        entry = next((m for m in bank if m["id"] == c.misconception), None)
        items.append(ladder.start(c.to_dict(), by_q[c.question], answer_text(results[c.question]), entry, backend,
                                  language))
    return items, [c.to_dict() for c in everything]


def play(items: list[dict], questions: list[dict], script: dict[str, list[str]], backend: str = "mock",
         cfg: dict | None = None) -> None:
    """Answer every open item from the script, in order."""
    by_q = {q["id"]: q for q in questions}
    for item in items:
        replies = list(script.get(item["question"], []))
        while not ladder.done(item):
            ladder.reply(item, replies.pop(0) if replies else NOT_SURE, by_q[item["question"]], backend, cfg)

