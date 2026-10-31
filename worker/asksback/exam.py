"""Exam definition (exam.yaml): blank master pages, question regions and rubric.

All coordinates are pixels in the master page image, as [x, y, w, h].
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, PrivateAttr, model_validator

Box = tuple[int, int, int, int]


class Criterion(BaseModel):
    id: str
    points: float  # negative points = penalty applied when the criterion is met
    description: str
    # "answer": the result itself; "reasoning": the justification behind it (G1 needs the difference).
    kind: Literal["answer", "reasoning"] = "answer"
    # Words or short phrases that show the criterion is met. Used by the offline grader and reply judge,
    # and never shown to students.
    look_for: list[str] = []


class Question(BaseModel):
    id: str
    page: int  # 1-based index into Exam.pages
    type: Literal["mcq", "open"]
    region: Box  # where the student's answer goes
    points: float
    # mcq
    options: dict[str, Box] = {}
    option_text: dict[str, str] = {}
    answer: str | None = None
    # open
    prompt: str | None = None  # question statement, if not visible inside `region`
    statement_region: Box | None = None  # master crop shown to the grader as the question statement
    answer_key: str | None = None
    criteria: list[Criterion] = []

    @model_validator(mode="after")
    def _check(self) -> Question:
        if self.type == "mcq":
            if not self.options:
                raise ValueError(f"{self.id}: mcq needs options")
            if self.answer not in self.options:
                raise ValueError(f"{self.id}: answer {self.answer!r} is not one of {list(self.options)}")
        else:
            if not self.criteria:
                raise ValueError(f"{self.id}: open question needs criteria")
            ids = [c.id for c in self.criteria]
            if len(set(ids)) != len(ids):
                raise ValueError(f"{self.id}: duplicate criterion ids")
        return self


class Exam(BaseModel):
    name: str
    course: str = ""  # misconception banks are kept per course
    language: str = "English"  # language for feedback and follow-ups
    grading_style: str = ""  # the teacher's general style, in their own words
    pages: list[str]  # master page images, relative to the exam directory
    questions: list[Question]

    _root: Path = PrivateAttr(default=Path("."))

    @model_validator(mode="after")
    def _check(self) -> Exam:
        ids = [q.id for q in self.questions]
        if len(set(ids)) != len(ids):
            raise ValueError("duplicate question ids")
        for q in self.questions:
            if not 1 <= q.page <= len(self.pages):
                raise ValueError(f"{q.id}: page {q.page} out of range")
        return self

    @classmethod
    def load(cls, exam_dir: Path) -> Exam:
        exam_dir = Path(exam_dir)
        exam = cls.model_validate(yaml.safe_load((exam_dir / "exam.yaml").read_text()))
        exam._root = exam_dir
        return exam

    @property
    def root(self) -> Path:
        return self._root

    @property
    def max_points(self) -> float:
        return sum(q.points for q in self.questions)

    def page_paths(self) -> list[Path]:
        return [self._root / p for p in self.pages]

    def question(self, qid: str) -> Question:
        return next(q for q in self.questions if q.id == qid)
