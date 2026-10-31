"""Synthetic exam: the demo class's everyday-science quiz, filled in by five fictional students.

Renders a two-page blank exam, fills it in with handwriting-style fonts, and turns each page
into a fake phone photo (perspective, rotation, uneven light, blur, noise, JPEG). Also writes
exam.yaml, with the rubric, the look-for terms and the course's starting misconception bank.

The five answers are written so that each follow-up trigger and each profile shows up:
ana answers everything with reasons, bruno gives bare answers (justification follow-ups),
carla shows two known misconceptions, diego is far from the answers, and eva's last answer
reads very differently from her other ones (understanding check). Question 5 is the pitch's
airplane question.

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

EXAM_NAME = "Everyday Science: Quiz 3"
COURSE = "SCI1"
MCQ = [
    ("q1", "1. A metal spoon left in hot soup gets hot by:",
     ["Convection", "Conduction", "Radiation", "Friction", "Magnetism"], "B"),
    ("q2", "2. What causes the seasons on Earth?", ["Distance", "Wind", "Earth's tilt", "The Moon", "Clouds"], "C"),
    ("q3", "3. A ball is thrown straight up. At the top, its speed is:",
     ["Maximum", "Zero", "Negative", "Constant", "Infinite"], "B"),
    ("q4", "4. Sound travels fastest through:", ["Steel", "Water", "Air", "Vacuum", "Foam"], "A"),
]
LETTERS = "ABCDE"

OPEN = [
    {
        "id": "q5", "y": 150, "points": 3,
        "text": ["5. How does an airplane fly? Explain why. (3 points)"],
        "prompt": "How does an airplane fly? Explain why.",
        "answer_key": "The wing meets the air at an angle (and is curved), so it turns the air that passes it downward. "
                      "Pushing air down pushes the wing up with an equal and opposite force (Newton's third law): "
                      "that force is the lift.",
        "criteria": [
            {"id": "result", "points": 1, "kind": "answer",
             "description": "Says the wing pushes (deflects) air downward, or that the wing produces lift.",
             "look_for": ["air down", "pushes air", "pushes the air", "deflects", "downward", "downwards", "lift"]},
            {"id": "reaction", "points": 1, "kind": "reasoning",
             "description": "Explains that pushing air down pushes the wing up (action and reaction, Newton's third law).",
             "look_for": ["third law", "reaction", "pushes the wing up", "pushes it up", "pushes it back up",
                          "equal and opposite", "newton", "pushes back", "pushed up", "pushes up", "wing up"],
             "hints": ["Re-read what you wrote, then think about what happens to the wing while it pushes the air.",
                       "Think about action and reaction: when you push something, what does it do to you?",
                       "When the wing throws air down, the air pushes the wing with an equal and opposite force. "
                       "Which way does that force point, and what does it do to the plane?"]},
            {"id": "angle", "points": 1, "kind": "reasoning",
             "description": "Mentions the wing's angle (angle of attack) or shape turning the air.",
             "look_for": ["angle", "angled", "tilted", "tilt", "tilts", "curved", "shape", "turns the air", "bends the air"],
             "hints": ["Look at how the wing meets the oncoming wind: is it perfectly flat against it?",
                       "Think about how the wing is set against the wind, and how that changes the air's path.",
                       "A wing is not flat to the wind: it meets the air at an angle, a bit like your hand out of a car "
                       "window. What does that angle do to the air that passes under it?"]},
        ],
        "transfer": {"prompt": "How can a stunt plane fly upside down?",
                     "look_for": ["angle", "tilt", "tilts", "tilted", "nose up", "pushes air down", "still pushes",
                                  "angle of attack", "points the wing"]},
    },
    {
        "id": "q6", "y": 580, "points": 2,
        "text": ["6. Why do you feel cold when you get out of a swimming pool,",
                 "    even on a warm day? (2 points)"],
        "prompt": "Why do you feel cold when you get out of a swimming pool, even on a warm day?",
        "answer_key": "The water left on the skin evaporates, and evaporating needs energy: the water takes that heat "
                      "from your skin, so the skin cools down.",
        "criteria": [
            {"id": "outcome", "points": 1, "kind": "answer", "description": "Says the water on the skin evaporates.",
             "look_for": ["evaporates", "evaporation", "evaporating", "evaporate", "evaporated", "vapor", "vapour"],
             "hints": ["Re-read your answer: what happens to the water left on your skin once you are out?",
                       "Think about where the water on your skin goes when it disappears.",
                       "The water on your skin slowly turns into vapour in the air. What is that change called, "
                       "and what does it need?"]},
            {"id": "heat", "points": 1, "kind": "reasoning",
             "description": "Explains that evaporating water takes heat (energy) from the skin.",
             "look_for": ["takes heat", "takes the heat", "takes energy", "heat from", "energy from", "absorbs heat",
                          "removes heat", "draws heat", "heat away", "uses heat", "needs heat", "needs energy",
                          "steals heat"],
             "hints": ["Re-read what you wrote: where does the water get what it needs to turn into vapour?",
                       "Think about energy: changing from liquid to gas needs energy. Where does it come from?",
                       "Water needs energy to evaporate, and the closest source is your warm skin. "
                       "What happens to your skin when something keeps taking its energy?"]},
        ],
        "transfer": {"prompt": "Why does a fan make you feel cooler when you are sweating?",
                     "look_for": ["evaporates", "evaporation", "evaporating", "evaporate", "faster", "sweat", "heat"]},
    },
    {
        "id": "q7", "y": 1020, "points": 2,
        "text": ["7. Why does ice float on water? Give one example of this",
                 "    in nature. (2 points)"],
        "prompt": "Why does ice float on water? Give one example of this in nature.",
        "answer_key": "Ice is less dense than liquid water: water expands when it freezes. "
                      "Examples: lakes freeze from the top down, icebergs float in the sea.",
        "criteria": [
            {"id": "density", "points": 1, "kind": "answer",
             "description": "Ice is less dense than liquid water (water expands when it freezes).",
             "look_for": ["less dense", "lower density", "less density", "expands", "expand", "more space", "takes up more"],
             "hints": ["Re-read your answer: compare a cup of ice with a cup of water. Which one is heavier?",
                       "Think about what happens to the size of water when it freezes.",
                       "Water takes up more space when it freezes, so the same amount of ice is spread over a bigger "
                       "volume. What does that do to its density?"]},
            {"id": "example", "points": 1, "kind": "answer", "description": "Gives a sensible example from nature.",
             "look_for": ["lake", "lakes", "iceberg", "icebergs", "pond", "ponds", "river", "rivers", "sea ice",
                          "arctic", "polar", "glacier"],
             "hints": ["Re-read your answer and think of a place outdoors where you have seen ice on water.",
                       "Think about what happens to a lake or the sea in the cold.",
                       "In winter, a frozen lake has ice on top and liquid water underneath. Where else in nature "
                       "does ice float?"]},
        ],
        "transfer": {"prompt": "If ice sank instead of floating, what would happen to a lake during a long winter?",
                     "look_for": ["bottom", "freeze solid", "freezes solid", "freeze completely", "fish", "die",
                                  "all the way", "whole lake", "entire lake", "freeze from the bottom"]},
    },
]
ANSWER_AREA = {"q5": (100, 205, 1040, 330), "q6": (100, 670, 1040, 300), "q7": (100, 1110, 1040, 330)}

# The course's misconception bank before this exam: what earlier classes got wrong.
BANK = [
    {"id": "wing-equal-time", "question": "q5",
     "title": "Thinks the air over the wing must take a longer path and meet the air below at the same time",
     "phrases": ["longer way", "longer path", "longer distance", "same time", "meet again", "catch up", "goes further"],
     "classmate_claim": "the air on top travels a longer path and has to meet the air below at the back of the wing, "
                        "so it speeds up",
     "concept": "what the wing does to the air that passes under and over it"},
    {"id": "wing-engines", "question": "q5", "title": "Thinks the engines are what hold the plane up",
     "phrases": ["engines hold", "engine holds", "engines push it up", "because of the engines", "engines lift"],
     "classmate_claim": "the engines are what hold the plane up in the air",
     "concept": "what the engines do and what the wings do"},
    {"id": "pool-cold-enters", "question": "q6", "title": "Thinks cold passes from the water into the body",
     "phrases": ["cold from the water", "cold goes into", "cold enters", "cold gets into", "the cold goes in"],
     "classmate_claim": "you feel cold because the cold from the water goes into your body",
     "concept": "which way heat moves, and where it goes when water evaporates"},
    {"id": "ice-air", "question": "q7", "title": "Thinks ice floats only because of the air trapped inside",
     "phrases": ["full of air", "air inside", "air bubbles", "has air", "because of the air", "trapped air"],
     "classmate_claim": "ice floats only because it has air bubbles trapped inside",
     "concept": "what happens to water's volume when it freezes"},
]

STUDENTS = {
    "ana": dict(name="Ana Souza", font=0, color=BLUE, mcq={"q1": "B", "q2": "C", "q3": "B", "q4": "A"},
                q5=["The tilted wing pushes air down, so the", "air pushes the wing up from below."],
                q6=["The water evaporates and takes", "heat from your skin."],
                q7=["Ice is less dense than water,", "so lakes freeze on top."]),
    "bruno": dict(name="Bruno Lima", font=4, color=BLACK, mcq={"q1": "B", "q2": "C", "q3": "B", "q4": "A"},
                  q5=["The wing pushes the air down."], q6=["Because the water evaporates."],
                  q7=["Ice is less dense than", "liquid water."]),
    "carla": dict(name="Carla Dias", font=3, color=BLUE, mcq={"q1": "B", "q2": "C", "q3": "A", "q4": "A"},
                  q5=["The wing pushes air down because the air", "on top goes a longer way."],
                  q6=["The cold from the water goes", "into your skin."],
                  q7=["Ice is less dense, like", "icebergs in the sea."]),
    "diego": dict(name="Diego Alves", font=1, color=BLACK, mcq={"q1": "A", "q2": "A", "q3": "B", "q4": "C"},
                  q5=["The air kind of holds it."], q6=["Because you are wet."], q7=["Ice floats because it is", "full of air."],
                  upside_down=[1], reverse_order=True),
    "eva": dict(name="Eva Rocha", font=4, color=PENCIL, mcq={"q1": "B", "q2": "C", "q3": "B", "q4": "A"},
                q5=["pushes air down, air pushes", "wing up, wing is tilted"], q6=["water evaporates and", "takes heat from skin"],
                q7=["Upon freezing, water molecules form an", "open hexagonal lattice, so ice is less",
                    "dense; consequently, ice forming atop", "lakes insulates the ecosystem beneath."]),
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
    text = text.replace(" ", "  ")  # handwriting leaves wider gaps between words than these fonts do
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
                          "prompt": q["prompt"], "answer_key": q["answer_key"], "criteria": q["criteria"],
                          "transfer": q["transfer"]})
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
