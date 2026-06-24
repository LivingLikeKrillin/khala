"""Pydantic v2 request/response DTOs for the ken-web API.

These are the wire contract the React SPA consumes. They mirror ken-core's
dataclasses but live here so the API surface is decoupled from the substrate.
"""

from __future__ import annotations

from pydantic import BaseModel


class RegisterReq(BaseModel):
    path: str


class ArtifactOut(BaseModel):
    artifact_id: str
    path: str
    status: str  # "vouched" | "orphan"
    weak_count: int


class QuestionOut(BaseModel):
    question_id: str
    text: str


class DueOut(BaseModel):
    questions: list[QuestionOut]


class AttemptReq(BaseModel):
    artifact_id: str
    question_id: str
    person: str
    answer: str


class AttemptOut(BaseModel):
    passed: bool
    score: float
    remediation: str | None = None


class WeaknessOut(BaseModel):
    question_id: str
    artifact_id: str
    fail_count: int


class CoverageOut(BaseModel):
    total: int
    covered: int
    ratio: float
    orphans: list[str]
    weakness: list[WeaknessOut]


class QuestionDetailOut(BaseModel):
    question_id: str
    text: str
    rung: int
    attempted: bool
    last_passed: bool | None = None
    last_ts: str | None = None
    fail_count: int
    next_due: str | None = None
    due: bool


class ArtifactDetailOut(BaseModel):
    questions: list[QuestionDetailOut]
