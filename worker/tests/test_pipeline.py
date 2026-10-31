"""From photos to flagged answers on the synthetic quiz, with the offline grader (local OCR, no model)."""

from __future__ import annotations

import json

import pytest

from asksback.grader import OfflineGrader
from asksback.pipeline import run
from asksback.results import result_doc
from asksback.synth import BANK, generate
from asksback.triggers import detect


@pytest.fixture(scope="session")
def scanned(tmp_path_factory):
    root = tmp_path_factory.mktemp("synthetic")
    exam = generate(root / "exam", seed=7)
    run(root / "exam", root / "out", OfflineGrader(root / "ocr"), lambda qid: [m for m in BANK if m["question"] == qid])
    data = json.loads((root / "out" / "results.json").read_text())
    by_student: dict[str, dict] = {}
    for r in data["results"]:
        by_student.setdefault(r["student"], {})[r["question"]] = result_doc(r)
    return exam, data, by_student


def test_every_page_is_matched(scanned):
    _, data, _ = scanned
    for student, regs in data["registrations"].items():
        assert sorted(r["page"] for r in regs) == [1, 2], student
    # diego's photos are in reverse order and page 1 is upside down
    assert [r["page"] for r in data["registrations"]["diego"]] == [2, 1]


def test_multiple_choice_is_read(scanned):
    _, _, by = scanned
    assert [by["ana"][q]["mcq"]["selected"] for q in ("q1", "q2", "q3", "q4")] == ["B", "C", "B", "A"]
    assert by["diego"]["q1"]["score"] == 0 and by["diego"]["q3"]["score"] == 1


def test_scanned_students_get_the_intended_follow_ups(scanned):
    exam, _, by = scanned
    got = {s: [(c.question, c.trigger) for c in detect(exam["questions"], res, BANK)[0]] for s, res in by.items()}
    assert got["ana"] == []
    assert got["bruno"] == [("q5", "G1"), ("q6", "G1"), ("q7", "G2")]
    assert sorted(got["carla"]) == [("q5", "G4"), ("q6", "G4")]
    assert dict(got["diego"])["q7"] == "G4"
    assert got["eva"] == [("q7", "G5")]
