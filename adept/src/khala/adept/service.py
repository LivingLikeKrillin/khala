"""adept service — shared orchestration over the deterministic substrate.

This layer factors the question/grade/coverage orchestration out of the CLI so it
can be reused by other front-ends (e.g. the adept-web API). It owns no derivation
logic of its own — it composes the pure modules (registry, questions, schedule,
coverage) with the cognition seams (probe, judge) behind the `LLMClient` protocol.

Persistence goes through a `AdeptStore` (FileStore or PostgresStore), injected by the
caller. `registry.current_hash(path)` and `Path(ref.path).read_text(...)` stay
DIRECT (filesystem) — the store is an index, not the artifact archive.

Invariants preserved from the substrate: question/attempt writes are FAIL-LOUD
(IO errors propagate); `judge.grade` is FAIL-CLOSED internally (LLM/parse error ->
passed=False) and is NOT re-wrapped here.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from khala.adept.coverage import compute_coverage_v1
from khala.adept.judge import grade as judge_grade
from khala.adept.llm import LLMClient
from khala.adept.models import ArtifactRef, Attempt, CoverageReport, Question
from khala.adept.probe import make_questions
from khala.adept.schedule import due as schedule_due
from khala.adept.schedule import next_due_at, rebuild
from khala.adept.store import AdeptStore


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def find_ref(artifact_id: str, *, store: AdeptStore) -> ArtifactRef | None:
    return next((r for r in store.load_manifest() if r.artifact_id == artifact_id), None)


def _bound_questions(ref: ArtifactRef, *, store: AdeptStore) -> list[Question] | None:
    """The artifact's questions IFF currently bound to its live content, else None.

    Mirrors the artifact-level stale gate used by coverage/due: questions missing,
    or whose stored store-hash != the artifact's current hash, mean nothing is bound
    (the artifact is an orphan / needs (re)generation).
    """
    store_hash, qs = store.load_questions(ref.artifact_id)
    if not qs or store_hash != ref.content_hash:
        return None
    return qs


def register_artifact(path: str, *, store: AdeptStore) -> ArtifactRef:
    return store.register(path)


def ensure_questions(
    artifact_id: str,
    *,
    store: AdeptStore,
    llm: LLMClient,
    n: int,
) -> list[Question]:
    """Return the artifact's questions, generating/regenerating when missing or stale."""
    ref = find_ref(artifact_id, store=store)
    if ref is None:
        raise KeyError(artifact_id)
    qs = _bound_questions(ref, store=store)
    if qs is None:
        made = make_questions(Path(ref.path).read_text(encoding="utf-8"), n=n, llm=llm)
        store.save_questions(artifact_id, ref.content_hash, made)  # fail-loud
        _, qs = store.load_questions(artifact_id)  # reload with ids
    return qs


@dataclass(frozen=True)
class DueLine:
    artifact_id: str
    needs_questions: bool
    questions: list  # list[tuple[qid, text]] when not needs_questions


def due_items(*, store: AdeptStore, now: str) -> list[DueLine]:
    """Per-artifact due lines: needs-questions when missing/stale, else due (qid, text)."""
    refs = store.load_manifest()
    attempts = store.load_attempts()
    out: list[DueLine] = []
    for ref in refs:
        qs = _bound_questions(ref, store=store)
        if qs is None:
            out.append(DueLine(ref.artifact_id, True, []))
            continue
        states = rebuild(attempts, current_hashes={q.id: ref.content_hash for q in qs})
        due_ids = schedule_due(states, [q.id for q in qs], now=now)
        tbid = {q.id: q.text for q in qs}
        out.append(DueLine(ref.artifact_id, False, [(qid, tbid[qid]) for qid in due_ids]))
    return out


@dataclass(frozen=True)
class AttemptResult:
    passed: bool
    score: float
    remediation: str | None


def remediate(artifact_text: str, question_text: str, answer: str, *, llm: LLMClient) -> str | None:
    """Generate a grounded remediation for a wrong answer; None on any LLM failure."""
    # Structure per adept/references/grading.md — explanatory feedback is a
    # precondition for learning transfer (evidence.md E3), so this never degrades
    # to a bare "wrong, the answer is X".
    sys_p = (
        "You are tutoring a developer who answered a comprehension question wrong. "
        "Using ONLY the artifact: acknowledge what their answer got right (if "
        "anything), state the artifact's own decision AND its reasoning, then give "
        "one concrete work moment where this knowledge changes what they would do. "
        "Concise, no preamble, no lecture — a retry will complete the learning."
    )
    user = f"ARTIFACT:\n{artifact_text}\n\nQUESTION: {question_text}\nTHEIR ANSWER: {answer}"
    try:
        return llm.generate(sys_p, user).strip() or None
    except Exception:  # noqa: BLE001 — never block recording on remediation failure
        return None


def grade_answer(
    artifact_id: str,
    question_id: str,
    answer: str,
    *,
    person: str,
    store: AdeptStore,
    llm: LLMClient,
    now: str,
) -> AttemptResult:
    """Grade ONE answer, record the attempt (fail-loud), and remediate on fail.

    `judge.grade` already fail-closes internally (LLM/parse error -> passed=False),
    so this function does NOT re-wrap it. The attempt is always recorded before
    remediation is attempted, so a remediation failure cannot block recording.
    """
    ref = find_ref(artifact_id, store=store)
    if ref is None:
        raise KeyError(artifact_id)
    _, qs = store.load_questions(artifact_id)
    q = next((x for x in qs if x.id == question_id), None)
    if q is None:
        raise KeyError(question_id)
    text = Path(ref.path).read_text(encoding="utf-8")
    verdict = judge_grade(text, [(q.text, answer)], llm=llm)  # fail-closed internally
    store.append_attempt(
        Attempt(
            person=person,
            artifact_id=artifact_id,
            question_id=question_id,
            content_hash=ref.content_hash,
            passed=verdict.passed,
            score=verdict.score,
            ts=now,
        )
    )  # fail-loud
    rem = None if verdict.passed else remediate(text, q.text, answer, llm=llm)
    return AttemptResult(passed=verdict.passed, score=verdict.score, remediation=rem)


def coverage_report(*, store: AdeptStore, now: str) -> CoverageReport:
    refs = store.load_manifest()
    attempts = store.load_attempts()
    qmap = {r.artifact_id: store.load_questions(r.artifact_id) for r in refs}
    return compute_coverage_v1(refs, qmap, attempts, now=now)


@dataclass(frozen=True)
class ArtifactStatus:
    artifact_id: str
    path: str
    status: str  # "orphan" | "vouched"
    weak_count: int


def list_artifacts(*, store: AdeptStore, now: str) -> list[ArtifactStatus]:
    """One status row per manifest ref, derived from `coverage_report` (no new logic)."""
    refs = store.load_manifest()
    report = coverage_report(store=store, now=now)
    orphans = set(report.orphans)
    weak_by_artifact: dict[str, int] = {}
    for w in report.weakness:
        weak_by_artifact[w.artifact_id] = weak_by_artifact.get(w.artifact_id, 0) + w.fail_count
    return [
        ArtifactStatus(
            artifact_id=ref.artifact_id,
            path=ref.path,
            status="orphan" if ref.artifact_id in orphans else "vouched",
            weak_count=weak_by_artifact.get(ref.artifact_id, 0),
        )
        for ref in refs
    ]


@dataclass(frozen=True)
class QuestionDetail:
    question_id: str
    text: str
    rung: int                 # interval_idx 0..4 (0 when never-attempted)
    attempted: bool
    last_passed: bool | None
    last_ts: str | None
    fail_count: int
    next_due: str | None      # ISO-8601; None => never-attempted => due now
    due: bool


def artifact_detail(artifact_id: str, *, store: AdeptStore, now: str) -> list[QuestionDetail]:
    """Per-question schedule/mastery rows for one artifact. Read-only; no LLM.

    Returns [] when the artifact has no current questions or its questions are stale
    (artifact-level gate, matching coverage's `orphan` verdict). For a bound artifact,
    due-ness is exactly `schedule.due` (never re-derived here).
    """
    ref = find_ref(artifact_id, store=store)
    if ref is None:
        raise KeyError(artifact_id)
    qs = _bound_questions(ref, store=store)
    if qs is None:
        return []
    attempts = store.load_attempts()
    states = rebuild(attempts, current_hashes={q.id: ref.content_hash for q in qs})
    due_set = set(schedule_due(states, [q.id for q in qs], now=now))
    rows: list[QuestionDetail] = []
    for q in qs:
        st = states.get(q.id)
        if st is None:
            rows.append(QuestionDetail(
                question_id=q.id, text=q.text, rung=0, attempted=False,
                last_passed=None, last_ts=None, fail_count=0,
                next_due=None, due=q.id in due_set,
            ))
        else:
            rows.append(QuestionDetail(
                question_id=q.id, text=q.text, rung=st.interval_idx, attempted=True,
                last_passed=st.last_passed, last_ts=st.last_ts, fail_count=st.fail_count,
                next_due=next_due_at(st).isoformat(), due=q.id in due_set,
            ))
    return rows
