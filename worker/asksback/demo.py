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
        "q5": ["It gets smaller every step.",
               "Each comparison cuts the interval in half, and that only works because the array is sorted.",
               "I would flip the comparison and go the other way, it is still log n."],
        "q6": ["Every call adds a frame to the call stack until the memory runs out."],
        "q7": ["A stack is like a pile of plates, a queue is like a line at a shop."],
    },
    "Carla Dias": {
        "q5": ["I agree, it just checks the middle.", "It compares the target with the middle element.",
               "Oh, if it is sorted you can discard half of it each time.", "You flip the comparison."],
        "q6": ["It is a loop that hangs.", "It never stops.",
               "Each call puts a frame on the call stack until there is no memory, a stack overflow.", "Hmm, no idea."],
    },
    "Diego Alves": {"q5": ["I don't know."], "q7": ["I don't know.", "Not sure.", "No idea.", "I don't know."]},
    "Eva Rocha": {"q7": ["It would be printed first.", "Nothing would change.", "It goes first because it was sent first.",
                         "I'm not sure."]},
}

FULL = {
    "q5": "O(log n): every comparison halves the interval, and it only works on a sorted array.",
    "q6": "Stack overflow, because every call adds a frame to the call stack.",
    "q7": "A stack is LIFO, like a pile of books; a queue is FIFO, like a line at a shop.",
}
ALL_RIGHT = {"q1": "B", "q2": "C", "q3": "C", "q4": "A"}

CLASSMATES = [
    {"name": "Felipe Costa", "mcq": ALL_RIGHT, "answers": FULL, "script": {}},
    {"name": "Gabriela Nunes", "mcq": ALL_RIGHT, "answers": {
        "q5": "It is O(log n). Each step cuts the search interval in half, so the array has to be sorted first.",
        "q6": "It never stops calling itself, every call adds a frame, and it ends in a stack overflow.",
        "q7": "Stack: LIFO, like the undo history. Queue: FIFO, like a printer queue."}, "script": {}},
    {"name": "Heitor Ramos", "mcq": ALL_RIGHT, "answers": {
        "q5": "O(log n)", "q6": "Infinite recursion, it crashes.", "q7": "A stack is LIFO, a queue is FIFO."},
     "script": {"q5": ["The interval is cut in half each time, and the array must be sorted."],
                "q6": ["Each call adds a frame on the call stack until it runs out of memory."],
                "q7": ["A stack is like undo in an editor, a queue is like a line at the bank."]}},
    {"name": "Isabela Freitas", "mcq": {**ALL_RIGHT, "q3": "A"}, "answers": {
        "q5": "O(log n) because it is very fast and efficient.", "q6": FULL["q6"],
        "q7": "Stacks are LIFO and queues are FIFO."},
     "script": {"q5": ["Because it is efficient.", "Each comparison throws away half, so the array needs to be sorted.",
                       "You reverse the comparison, and it stays log n."],
                "q7": ["A pile of plates and a line at the cinema."]}},
    {"name": "João Pereira", "mcq": {**ALL_RIGHT, "q1": "A", "q4": "C"}, "answers": {
        "q5": "O(log n), it works on any list.", "q6": "It turns into an infinite loop and hangs.", "q7": FULL["q7"]},
     "script": {"q5": ["I agree with them.", "It looks at the middle.", "If it is sorted you can discard half.", "No idea."],
                "q6": ["It just loops.", "It never stops.",
                       "Each call adds a frame to the call stack and it ends in a stack overflow.", "It would still overflow."]}},
    {"name": "Larissa Moreira", "mcq": {**ALL_RIGHT, "q2": "B", "q3": "A"}, "answers": {
        "q5": "O(n/2) since it looks at half.", "q6": "Stack overflow.", "q7": FULL["q7"]},
     "script": {"q5": ["It is n/2.", "You keep halving n, so it takes log n steps.", "And the array must be sorted.",
                       "You reverse the comparisons."],
                "q6": ["It crashes.", "It just runs out.", "Every call stores a frame on the stack.", "It still overflows."]}},
    {"name": "Mateus Barros", "mcq": {"q1": "A", "q2": "B", "q3": "C", "q4": "B"}, "answers": {
        "q5": "O(n/2)", "q6": "It returns zero.", "q7": "They are the same thing."},
     "script": {"q5": ["It is n/2.", "I don't know.", "No idea.", "Not sure."],
                "q7": ["They are the same.", "I don't know.", "No idea.", "Not sure."]}},
    {"name": "Natália Gomes", "mcq": {"q1": "C", "q2": "A", "q3": "B", "q4": "A"}, "answers": {
        "q5": "Binary.", "q6": "It gives an error message.", "q7": ""}, "script": {}},
    {"name": "Otávio Souza", "mcq": ALL_RIGHT, "answers": {
        "q5": "O(log n), the array must be sorted.", "q6": "Stack overflow: each call adds a frame.",
        "q7": "Stack is LIFO (plates), queue is FIFO (a line)."},
     "script": {"q5": ["It is just faster.", "It skips stuff.", "It checks the middle.", "The interval halves each time.",
                       "I'm not sure."]}},
    {"name": "Paula Ribeiro", "mcq": ALL_RIGHT, "answers": {
        "q5": "log n, it halves, needs sorted array",
        "q6": "it crashes, stack overflow, too many frames",
        "q7": "A stack constitutes a last-in, first-out abstraction, whereas a queue implements first-in, first-out "
              "semantics; consequently, undo histories and printer spooling exemplify each respectively."},
     "script": {"q7": ["It gets printed first.", "The same as before.", "First in first out.", "Not sure."]}},
    {"name": "Rafael Teixeira", "mcq": {**ALL_RIGHT, "q3": "B"}, "answers": {
        "q5": FULL["q5"], "q6": "The stack gets bigger and bigger until it crashes.", "q7": FULL["q7"]},
     "script": {"q6": ["I mean every call adds a frame, so the call stack fills up until there is no memory left."]}},
    {"name": "Sofia Martins", "mcq": {**ALL_RIGHT, "q1": "A", "q2": "B"}, "answers": {
        "q5": "O(log n)", "q6": "Stack overflow.", "q7": FULL["q7"]},
     "script": {"q5": ["You keep halving the interval, and the array has to be sorted."],
                "q6": ["Each call adds a frame until the memory runs out."]}},
    {"name": "Tiago Cardoso", "mcq": {**ALL_RIGHT, "q2": "D", "q3": "A"}, "answers": {
        "q5": "O(log n)", "q6": "It stops.", "q7": "They are the same thing."},
     "script": {"q7": ["They both store things.", "The newest one.",
                       "A stack is LIFO and a queue is FIFO, like plates and a line.", "The first one would be printed last."],
                "q5": ["It is quick.", "It checks the middle.", "It looks at half each time.", "The array is sorted.",
                       "No idea."]}},
    {"name": "Ursula Lopes", "mcq": ALL_RIGHT, "answers": {
        "q5": "O(log n). Each comparison discards half of the remaining elements, which needs a sorted array.",
        "q6": "Infinite recursion: each call adds a stack frame until the call stack overflows.",
        "q7": "Stack = LIFO (pile of plates). Queue = FIFO (line at the cafeteria)."}, "script": {}},
    {"name": "Vitor Hugo", "mcq": {**ALL_RIGHT, "q4": "B"}, "answers": {
        "q5": "O(log n)", "q6": "It crashes.", "q7": "Stack is LIFO, queue is FIFO."},
     "script": {"q5": ["Each step cuts the interval in half; it needs a sorted array."],
                "q6": ["Every call adds a frame to the call stack until memory runs out."],
                "q7": ["Plates for the stack, a line at the shop for the queue."]}},
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

