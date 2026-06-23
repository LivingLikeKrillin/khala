"""ken service — shared orchestration over the deterministic substrate.

This layer factors the question/grade/coverage orchestration out of the CLI so it
can be reused by other front-ends (e.g. the ken-web API). It owns no derivation
logic of its own — it composes the pure modules (registry, questions, schedule,
coverage) with the cognition seams (probe, judge) behind the `LLMClient` protocol.

Invariants preserved from the substrate: question/attempt writes are FAIL-LOUD
(IO errors propagate); `judge.grade` is FAIL-CLOSED internally (LLM/parse error ->
passed=False) and is NOT re-wrapped here.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from ken.attempt import load_attempts
from ken.coverage import compute_coverage_v1
from ken.judge import grade as judge_grade
from ken.llm import LLMClient
from ken.models import ArtifactRef, CoverageReport, Question, Verdict
from ken.probe import make_questions
from ken.questions import load_questions, save_questions
from ken.registry import load_manifest, register as registry_register
from ken.schedule import due as schedule_due, rebuild


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def find_ref(manifest: str, artifact_id: str) -> ArtifactRef | None:
    return next((r for r in load_manifest(manifest) if r.artifact_id == artifact_id), None)


def register_artifact(path: str, *, manifest: str) -> ArtifactRef:
    return registry_register(path, manifest_path=manifest)


def ensure_questions(
    artifact_id: str,
    *,
    manifest: str,
    questions_store: str,
    llm: LLMClient,
    n: int,
) -> list[Question]:
    """Return the artifact's questions, generating/regenerating when missing or stale."""
    ref = find_ref(manifest, artifact_id)
    if ref is None:
        raise KeyError(artifact_id)
    store_hash, qs = load_questions(artifact_id, store_path=questions_store)
    if not qs or store_hash != ref.content_hash:
        made = make_questions(Path(ref.path).read_text(encoding="utf-8"), n=n, llm=llm)
        save_questions(artifact_id, ref.content_hash, made, store_path=questions_store)  # fail-loud
        _, qs = load_questions(artifact_id, store_path=questions_store)  # reload with ids
    return qs


@dataclass(frozen=True)
class DueLine:
    artifact_id: str
    needs_questions: bool
    questions: list  # list[tuple[qid, text]] when not needs_questions


def due_items(*, manifest: str, questions_store: str, ledger: str, now: str) -> list[DueLine]:
    """Per-artifact due lines: needs-questions when missing/stale, else due (qid, text)."""
    refs = load_manifest(manifest)
    attempts = load_attempts(ledger)
    out: list[DueLine] = []
    for ref in refs:
        store_hash, qs = load_questions(ref.artifact_id, store_path=questions_store)
        if not qs or store_hash != ref.content_hash:
            out.append(DueLine(ref.artifact_id, True, []))
            continue
        states = rebuild(attempts, current_hashes={q.id: ref.content_hash for q in qs})
        due_ids = schedule_due(states, [q.id for q in qs], now=now)
        tbid = {q.id: q.text for q in qs}
        out.append(DueLine(ref.artifact_id, False, [(qid, tbid[qid]) for qid in due_ids]))
    return out


def grade_set(artifact_text: str, qa_pairs, *, llm: LLMClient) -> Verdict:
    return judge_grade(artifact_text, qa_pairs, llm=llm)


def coverage_report(*, manifest: str, questions_store: str, ledger: str) -> CoverageReport:
    refs = load_manifest(manifest)
    attempts = load_attempts(ledger)
    qmap = {r.artifact_id: load_questions(r.artifact_id, store_path=questions_store) for r in refs}
    return compute_coverage_v1(refs, qmap, attempts)
