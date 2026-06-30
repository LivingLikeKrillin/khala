"""Domain models for adept — frozen dataclasses, pure (no IO/LLM imports)."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass(frozen=True)
class ArtifactRef:
    """A registered artifact: stable id, path, and its current content hash."""

    artifact_id: str
    path: str
    content_hash: str


@dataclass(frozen=True)
class Question:
    """A single grounded comprehension question.

    `id` is a stable handle assigned by the questions store
    (`sha(artifact_id + content_hash + index)[:12]`). A freshly-generated
    question (e.g. from `probe.make_questions`) has `id=""` until the store
    assigns one on save. Construct with keyword args.
    """

    text: str
    id: str = ""


@dataclass(frozen=True)
class Verdict:
    """An LLM-as-judge verdict over a set of answers."""

    passed: bool
    score: float
    rationale: str


@dataclass(frozen=True)
class Attempt:
    """One graded attempt at a question, appended to the attempt ledger.

    `artifact_id` is denormalized so derivations need no live join. `content_hash`
    binds the attempt to the artifact content it was answered against — attempts
    against a stale hash are ignored by `schedule.rebuild`.
    """

    person: str
    artifact_id: str
    question_id: str
    content_hash: str
    passed: bool
    score: float
    ts: str

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Attempt":
        return cls(
            person=data["person"],
            artifact_id=data["artifact_id"],
            question_id=data["question_id"],
            content_hash=data["content_hash"],
            passed=data["passed"],
            score=data["score"],
            ts=data["ts"],
        )


@dataclass(frozen=True)
class ReviewState:
    """A *computed* per-question review state (never persisted).

    Produced by `schedule.rebuild` by folding a question's attempts in ts order.
    Absence of a state for a question means never-attempted / stale-hash.
    """

    question_id: str
    content_hash: str
    interval_idx: int
    last_ts: str
    last_passed: bool
    fail_count: int


@dataclass(frozen=True)
class WeaknessItem:
    """A repeatedly-failed question, surfaced in the weakness map."""

    question_id: str
    artifact_id: str
    fail_count: int


@dataclass(frozen=True)
class CoverageReport:
    """Org-level cognitive-debt coverage + orphan hotlist + weakness map."""

    total: int
    covered: int
    ratio: float
    orphans: list[str]
    weakness: list[WeaknessItem] = field(default_factory=list)
