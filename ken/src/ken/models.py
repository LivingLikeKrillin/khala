"""Domain models for ken — frozen dataclasses, pure (no IO/LLM imports)."""

from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class ArtifactRef:
    """A registered artifact: stable id, path, and its current content hash."""

    artifact_id: str
    path: str
    content_hash: str


@dataclass(frozen=True)
class Question:
    """A single grounded comprehension question."""

    text: str


@dataclass(frozen=True)
class Verdict:
    """An LLM-as-judge verdict over a set of answers."""

    passed: bool
    score: float
    rationale: str


@dataclass(frozen=True)
class Vouch:
    """An atomic record: this person can vouch for this artifact at this hash/time."""

    artifact_id: str
    person: str
    content_hash: str
    score: float
    passed: bool
    n_questions: int
    ts: str

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Vouch":
        return cls(
            artifact_id=data["artifact_id"],
            person=data["person"],
            content_hash=data["content_hash"],
            score=data["score"],
            passed=data["passed"],
            n_questions=data["n_questions"],
            ts=data["ts"],
        )


@dataclass(frozen=True)
class CoverageReport:
    """Org-level cognitive-debt coverage + orphan hotlist."""

    total: int
    covered: int
    ratio: float
    orphans: list[str]
