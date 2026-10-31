"""Synthetic exam: the demo class's algorithms quiz, filled in by five fictional students.

Renders a two-page blank exam, fills it in with handwriting-style fonts, and turns each page
into a fake phone photo (perspective, rotation, uneven light, blur, noise, JPEG). Also writes
exam.yaml, with the rubric, the look-for terms and the course's starting misconception bank.

The five answers are written so that each follow-up trigger and each profile shows up:
ana answers everything with reasons, bruno gives bare answers (justification follow-ups),
carla shows two known misconceptions, diego is far from the answers, and eva's last answer
reads very differently from her other ones (understanding check).

Fonts look like handwriting but are far cleaner than real students' writing, so results
here prove the plumbing works, not that real grading will be accurate.
"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import yaml
from PIL import Image, ImageDraw, ImageFont

W, H = 1240, 1754  # A4 at 150 dpi
PRINT_FONT = "/System/Library/Fonts/Helvetica.ttc"
HAND_FONTS = [
    "/System/Library/Fonts/Supplemental/Bradley Hand Bold.ttf",
    "/System/Library/Fonts/Noteworthy.ttc",
    "/System/Library/Fonts/Supplemental/Chalkboard.ttc",
    "/System/Library/Fonts/MarkerFelt.ttc",
    "/System/Library/Fonts/Supplemental/Comic Sans MS.ttf",
]
BLUE, BLACK, PENCIL = (25, 45, 150), (25, 25, 30), (95, 95, 100)

EXAM_NAME = "Algorithms and Data Structures: Quiz 2"
COURSE = "CS1"
MCQ = [
    ("q1", "1. Which structure removes the most recently added item first?",
     ["Queue", "Stack", "Heap", "Tree", "Graph"], "B"),
    ("q2", "2. Worst-case time of linear search on n items:", ["O(1)", "O(log n)", "O(n)", "O(n log n)", "O(n²)"], "C"),
    ("q3", "3. Which of these sorting algorithms is stable?", ["Quick", "Heap", "Merge", "Selection", "Shell"], "C"),
    ("q4", "4. Average time of a lookup in a hash table:", ["O(1)", "O(log n)", "O(n)", "O(n log n)", "O(n²)"], "A"),
]
LETTERS = "ABCDE"

OPEN = [
    {
        "id": "q5", "y": 150, "points": 3,
        "text": ["5. What is the time complexity of binary search, and why? (3 points)"],
        "prompt": "What is the time complexity of binary search, and why?",
        "answer_key": "O(log n): each comparison discards half of the remaining interval, so after k steps n/2^k "
                      "elements are left, and k = log2 n steps reach one element. It only works on a sorted array.",
        "criteria": [
            {"id": "result", "points": 1, "kind": "answer", "description": "States O(log n).",
             "look_for": ["log n", "o(log", "logn", "log2 n", "log 2 n", "logarithmic"]},
            {"id": "halving", "points": 1, "kind": "reasoning",
             "description": "Explains that each step halves the search interval (discards half of the remaining elements).",
             "look_for": ["half", "halves", "halving", "in two", "divide by 2", "divided by 2", "cut in half",
                          "split in half", "splits"]},
            {"id": "sorted", "points": 1, "kind": "reasoning", "description": "Says the array must be sorted.",
             "look_for": ["sorted", "ordered", "in order"]},
        ],
    },
    {
        "id": "q6", "y": 580, "points": 2,
        "text": ["6. A recursive function has no base case. What happens when it runs,",
                 "    and why? (2 points)"],
        "prompt": "A recursive function has no base case. What happens when it runs, and why?",
        "answer_key": "It never stops calling itself and ends with a stack overflow, because every call pushes a "
                      "new frame on the call stack until the stack's memory runs out.",
        "criteria": [
            {"id": "outcome", "points": 1, "kind": "answer",
             "description": "Says it never stops and ends in a stack overflow (or a recursion error / crash).",
             "look_for": ["stack overflow", "overflow", "never stops", "infinite recursion", "recursion error",
                          "crash", "crashes", "forever"]},
            {"id": "frames", "points": 1, "kind": "reasoning",
             "description": "Explains that every call adds a frame to the call stack until memory runs out.",
             "look_for": ["frame", "frames", "call stack", "memory", "each call", "every call", "fills the stack",
                          "stack fills", "stack fills up"]},
        ],
    },
    {
        "id": "q7", "y": 1020, "points": 2,
        "text": ["7. What is the difference between a stack and a queue? Give one",
                 "    real-world example of each. (2 points)"],
        "prompt": "What is the difference between a stack and a queue? Give one real-world example of each.",
        "answer_key": "A stack is last-in, first-out (LIFO); a queue is first-in, first-out (FIFO). "
                      "Examples: a pile of plates or an undo history; a line at a shop or a printer queue.",
        "criteria": [
            {"id": "order", "points": 1, "kind": "answer",
             "description": "Stack is last-in-first-out (LIFO), queue is first-in-first-out (FIFO).",
             "look_for": ["lifo", "fifo", "last in", "first in", "last-in", "first-in"]},
            {"id": "examples", "points": 1, "kind": "answer", "description": "Gives a sensible real-world example of each.",
             "look_for": ["plates", "pile", "books", "undo", "line", "printer", "checkout", "cafeteria", "tickets",
                          "browser back", "spool", "spooling", "queue at", "shop"]},
        ],
    },
]
ANSWER_AREA = {"q5": (100, 205, 1040, 330), "q6": (100, 670, 1040, 300), "q7": (100, 1110, 1040, 330)}

# The course's misconception bank before this exam: what earlier classes got wrong.
BANK = [
    {"id": "bs-any-array", "question": "q5", "title": "Thinks binary search works on any array, sorted or not",
     "phrases": ["any array", "any list", "unsorted", "not need to be sorted", "doesnt need to be sorted",
                 "does not matter if sorted"],
     "classmate_claim": "binary search works on any array, sorted or not",
     "concept": "what being sorted lets you discard"},
    {"id": "bs-n-over-2", "question": "q5", "title": "Thinks binary search is O(n/2) because it looks at half",
     "phrases": ["n/2", "o(n/2)", "n over 2"],
     "classmate_claim": "binary search is O(n/2), because it only looks at half of the array",
     "concept": "how many times you can halve n before one element is left"},
    {"id": "rec-loop", "question": "q6", "title": "Treats missing base case as a loop that just hangs, without the stack",
     "phrases": ["infinite loop", "hangs", "freezes", "just keeps looping"],
     "classmate_claim": "a recursion with no base case is just an infinite loop that hangs, like while(true)",
     "concept": "what each call leaves on the call stack"},
    {"id": "sq-same", "question": "q7", "title": "Thinks a stack and a queue are the same structure",
     "phrases": ["same thing", "the same", "no difference"],
     "classmate_claim": "a stack and a queue are the same thing with different names",
     "concept": "which item leaves first in each one"},
]

STUDENTS = {
    "ana": dict(name="Ana Souza", font=0, color=BLUE, mcq={"q1": "B", "q2": "C", "q3": "C", "q4": "A"},
                q5=["O(log n), because each step halves", "the interval, and the array must be sorted."],
                q6=["Stack overflow: each call adds a frame", "to the call stack and it never ends."],
                q7=["A stack is LIFO (a pile of plates),", "a queue is FIFO (a line at a shop)."]),
    "bruno": dict(name="Bruno Lima", font=1, color=BLACK, mcq={"q1": "B", "q2": "C", "q3": "C", "q4": "A"},
                  q5=["O(log n)"], q6=["It crashes with an error."], q7=["A stack is LIFO and", "a queue is FIFO."]),
    "carla": dict(name="Carla Dias", font=2, color=BLUE, mcq={"q1": "B", "q2": "C", "q3": "A", "q4": "A"},
                  q5=["O(log n), it works on any array", "by checking the middle."],
                  q6=["It becomes an infinite loop", "and the program hangs."],
                  q7=["Stack: LIFO, like plates.", "Queue: FIFO, like a line."]),
    "diego": dict(name="Diego Alves", font=3, color=BLACK, mcq={"q1": "A", "q2": "B", "q3": "C", "q4": "C"},
                  q5=["O(n/2) because it looks", "at half"], q6=["The program stops."], q7=["They are the same thing."],
                  upside_down=[1], reverse_order=True),
    "eva": dict(name="Eva Rocha", font=4, color=PENCIL, mcq={"q1": "B", "q2": "C", "q3": "C", "q4": "A"},
                q5=["log n, halves it each time,", "needs sorted"], q6=["stack overflow, frames pile up"],
                q7=["A stack enforces last-in, first-out semantics,", "whereas a queue guarantees first-in,",
                    "first-out ordering; e.g. undo histories", "versus printer spooling."]),
}
STYLE = """Reasoning points need the reasoning on paper: a bare result gets only the result point.
Ignore spelling mistakes as long as the word is recognizable."""


def _font(path: str, size: int) -> ImageFont.FreeTypeFont:
    try:
        return ImageFont.truetype(path, size)
    except OSError:
        return ImageFont.load_default(size)




def _master_pages() -> tuple[list[Image.Image], dict]:
    title, body, small = _font(PRINT_FONT, 40), _font(PRINT_FONT, 27), _font(PRINT_FONT, 22)
    regions: dict = {}

    p1 = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(p1)
    d.text((100, 70), EXAM_NAME, font=title, fill="black")
    d.text((100, 140), "Name: _______________________________     Class: ________", font=body, fill="black")
    regions["name"] = [170, 115, 520, 60]
    d.text((100, 195), "Part 1. Mark exactly one option per question with an X.", font=small, fill="black")
    for i, (qid, text, opts, _) in enumerate(MCQ):
        y = 260 + i * 160
        d.text((100, y), text, font=body, fill="black")
        yo = y + 55
        options = {}
        for j, opt in enumerate(opts):
            x = 110 + j * 210
            d.rectangle((x, yo, x + 34, yo + 34), outline="black", width=2)
            d.text((x + 48, yo + 2), f"{LETTERS[j]})  {opt}", font=body, fill="black")
            options[LETTERS[j]] = [x - 6, yo - 6, 46, 46]
        regions[qid] = {"region": [100, y - 10, 1050, 115], "options": options}
    d.text((100, 960), "Write clearly; answers that cannot be read are not graded.", font=small, fill="black")
    d.text((100, 990), "Part 2 is on the next page.", font=small, fill="black")
    d.text((1000, 1680), "Page 1 of 2", font=small, fill="black")

    p2 = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(p2)
    d.text((100, 70), "Part 2: explain your answers", font=title, fill="black")
    for q in OPEN:
        for k, line in enumerate(q["text"]):
            d.text((100, q["y"] + k * 36), line, font=body, fill="black")
        x, y, w, h = ANSWER_AREA[q["id"]]
        d.rectangle((x, y, x + w, y + h), outline=(150, 150, 150), width=2)
        for ly in range(y + 60, y + h - 10, 60):
            d.line((x + 15, ly, x + w - 15, ly), fill=(205, 205, 205), width=1)
        regions[q["id"]] = {"region": [x + 3, y + 3, w - 6, h - 6],
                            "statement_region": [90, q["y"] - 8, 1060, 36 * len(q["text"]) + 12]}
    d.text((1000, 1680), "Page 2 of 2", font=small, fill="black")
    return [p1, p2], regions


def _write(img: Image.Image, text: str, x: int, y: int, font, color, rng: np.random.Generator) -> None:
    left, top, right, bottom = font.getbbox(text)
    layer = Image.new("RGBA", (right + 20, bottom + 20), (0, 0, 0, 0))
    ImageDraw.Draw(layer).text((10, 10), text, font=font, fill=color + (235,))
    layer = layer.rotate(float(rng.uniform(-2.5, 2.5)), resample=Image.BICUBIC, expand=True)
    img.paste(layer, (int(x + rng.integers(-6, 7)), int(y + rng.integers(-4, 5))), layer)


def _cross(img: Image.Image, box: list[int], color, rng: np.random.Generator) -> None:
    x, y, w, h = box
    d = ImageDraw.Draw(img)
    j = lambda: int(rng.integers(-4, 5))  # noqa: E731
    d.line((x + 6 + j(), y + 6 + j(), x + w - 6 + j(), y + h - 6 + j()), fill=color, width=4)
    d.line((x + w - 6 + j(), y + 6 + j(), x + 6 + j(), y + h - 6 + j()), fill=color, width=4)



def _student_pages(masters: list[Image.Image], regions: dict, spec: dict, rng) -> list[Image.Image]:
    p1, p2 = masters[0].copy(), masters[1].copy()
    font = _font(HAND_FONTS[spec["font"]], 38)
    _write(p1, spec["name"], 200, 118, font, spec["color"], rng)
    for qid, choice in spec["mcq"].items():
        for c in [choice] if isinstance(choice, str) else choice:
            _cross(p1, regions[qid]["options"][c], spec["color"], rng)
    for qid in ("q5", "q6", "q7"):
        x, y, _, _ = ANSWER_AREA[qid]
        for k, line in enumerate(spec[qid]):
            _write(p2, line, x + 30 + int(rng.integers(0, 30)), y + 12 + k * 60, font, spec["color"], rng)
    return [p1, p2]


CONDITIONS = {
    "easy": dict(tilt=3, jitter=0.02, light=0.06, blur=0.6, noise=2.0, jpeg=90, shadow=False),
    "normal": dict(tilt=6, jitter=0.035, light=0.12, blur=0.9, noise=3.5, jpeg=85, shadow=False),
    "hard": dict(tilt=12, jitter=0.06, light=0.30, blur=1.6, noise=6.0, jpeg=70, shadow=True),
}


def _photo(page: Image.Image, rng: np.random.Generator, upside_down: bool, cond: dict) -> np.ndarray:
    """Simulate a phone photo of the page lying on a table."""
    src = cv2.cvtColor(np.asarray(page), cv2.COLOR_RGB2BGR)
    h, w = src.shape[:2]
    cw, ch = int(w * 1.35), int(h * 1.3)
    table = np.full((ch, cw, 3), (70, 95, 120), np.uint8)
    table = cv2.add(table, rng.integers(0, 25, table.shape, dtype=np.uint8))

    ang = np.deg2rad(rng.uniform(-cond["tilt"], cond["tilt"]) + (180 if upside_down else 0))
    c, s = np.cos(ang), np.sin(ang)
    corners = np.float32([[-w / 2, -h / 2], [w / 2, -h / 2], [w / 2, h / 2], [-w / 2, h / 2]])
    rot = corners @ np.float32([[c, s], [-s, c]])
    dst = rot + np.float32([cw / 2, ch / 2]) + rng.uniform(-cond["jitter"], cond["jitter"], (4, 2)).astype(np.float32) * w
    M = cv2.getPerspectiveTransform(np.float32([[0, 0], [w, 0], [w, h], [0, h]]), dst.astype(np.float32))
    warped = cv2.warpPerspective(src, M, (cw, ch))
    mask = cv2.warpPerspective(np.full((h, w), 255, np.uint8), M, (cw, ch))
    photo = np.where(mask[..., None] > 0, warped, table)

    yy, xx = np.mgrid[0:ch, 0:cw].astype(np.float32)
    gx, gy = rng.uniform(-1, 1, 2)
    light = 0.92 + cond["light"] * (gx * (xx / cw - 0.5) + gy * (yy / ch - 0.5))
    light -= 0.10 * (((xx / cw - 0.5) ** 2 + (yy / ch - 0.5) ** 2) * 2)
    photo = np.clip(photo.astype(np.float32) * light[..., None], 0, 255)
    if cond["shadow"]:  # the teacher's hand or the phone casting a soft shadow across one side
        x0 = rng.uniform(0.55, 0.8) * cw
        shade = np.where(xx + 0.3 * (yy - ch / 2) > x0, 0.62, 1.0).astype(np.float32)
        photo *= cv2.GaussianBlur(shade, (0, 0), 25)[..., None]
    photo = cv2.GaussianBlur(photo, (0, 0), cond["blur"])
    photo = np.clip(photo + rng.normal(0, cond["noise"], photo.shape), 0, 255).astype(np.uint8)
    return photo




def exam_definition(regions: dict) -> dict:
    questions = []
    for qid, _, opts, answer in MCQ:
        questions.append({"id": qid, "page": 1, "type": "mcq", "points": 1, "answer": answer,
                          "region": regions[qid]["region"], "options": regions[qid]["options"],
                          "option_text": dict(zip(LETTERS, opts))})
    for q in OPEN:
        questions.append({"id": q["id"], "page": 2, "type": "open", "points": q["points"],
                          "region": regions[q["id"]]["region"], "statement_region": regions[q["id"]]["statement_region"],
                          "prompt": q["prompt"], "answer_key": q["answer_key"], "criteria": q["criteria"]})
    return {"name": EXAM_NAME, "course": COURSE, "language": "English", "grading_style": STYLE,
            "pages": ["master/page1.png", "master/page2.png"], "name_region": regions["name"], "questions": questions}


def generate(out: Path, seed: int = 7, conditions: str = "normal", students: dict | None = None) -> dict:
    """Write the exam folder and return the exam definition. `students` defaults to the five above."""
    students = students or STUDENTS
    cond = CONDITIONS[conditions]
    rng = np.random.default_rng(seed)
    (out / "master").mkdir(parents=True, exist_ok=True)
    masters, regions = _master_pages()
    for i, m in enumerate(masters, start=1):
        m.save(out / "master" / f"page{i}.png")
    masters[0].save(out / "exam.pdf", save_all=True, append_images=masters[1:], resolution=150)
    exam = exam_definition(regions)
    (out / "exam.yaml").write_text(yaml.safe_dump({k: v for k, v in exam.items() if k != "name_region"},
                                                  sort_keys=False, allow_unicode=True, width=120))
    (out / "bank.yaml").write_text(yaml.safe_dump(BANK, sort_keys=False, allow_unicode=True, width=120))

    for name, spec in students.items():
        sdir = out / "students" / name
        sdir.mkdir(parents=True, exist_ok=True)
        pages = _student_pages(masters, regions, spec, rng)
        order = list(range(len(pages)))[::-1] if spec.get("reverse_order") else range(len(pages))
        for n, i in enumerate(order):
            photo = _photo(pages[i], rng, (i + 1) in spec.get("upside_down", []), cond)
            cv2.imwrite(str(sdir / f"IMG_{1000 + n}.jpg"), photo, [cv2.IMWRITE_JPEG_QUALITY, cond["jpeg"]])
    return exam
