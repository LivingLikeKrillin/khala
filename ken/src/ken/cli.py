"""ken CLI — agent primitives over a deterministic substrate, + headless review.

Agent-driven loop (no API key): `due` -> `save-questions` -> `record-attempt` ->
`coverage`. The Claude Code agent supplies cognition (questions, grading,
remediation); ken owns the question store, attempt ledger, and pure derivations.

Headless self-drive: `review` uses the v0 LLM seam (AnthropicLLM via `_make_llm`),
generating questions and grading itself. Tests monkeypatch `ken.cli._make_llm`.
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import typer

from ken import service
from ken.llm import AnthropicLLM, LLMClient
from ken.models import Attempt, Question
from ken.store import KenStore
from ken.stores.file_store import FileStore

app = typer.Typer(help="ken — cognitive-debt repayment loop")

DEFAULT_MANIFEST = "ken.manifest.yaml"
DEFAULT_QUESTIONS = "ken.questions.json"
DEFAULT_LEDGER = "ken.attempts.jsonl"
DEFAULT_N_QUESTIONS = 5


def _make_llm() -> LLMClient:
    """LLM factory — the test seam. Commands call this, never AnthropicLLM() inline."""
    return AnthropicLLM()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _find_ref(store: KenStore, artifact_id: str):
    return next(
        (r for r in store.load_manifest() if r.artifact_id == artifact_id), None
    )


@app.command()
def register(
    path: str = typer.Argument(..., help="Path to the artifact to register."),
    manifest: str = typer.Option(DEFAULT_MANIFEST, "--manifest", help="Manifest path."),
) -> None:
    """Register an artifact into the manifest; prints its artifact_id."""
    store = FileStore(manifest=manifest, questions=DEFAULT_QUESTIONS, ledger=DEFAULT_LEDGER)
    ref = service.register_artifact(path, store=store)
    typer.echo(f"registered {ref.path} {ref.artifact_id}")


@app.command()
def due(
    person: str = typer.Option(None, "--as", help="The reviewer (informational)."),
    manifest: str = typer.Option(DEFAULT_MANIFEST, "--manifest", help="Manifest path."),
    questions: str = typer.Option(DEFAULT_QUESTIONS, "--questions", help="Questions store."),
    ledger: str = typer.Option(DEFAULT_LEDGER, "--ledger", help="Attempt ledger."),
) -> None:
    """List due questions; flag artifacts with no (or stale) questions.

    An artifact with no saved questions, or whose stored hash != current hash, is
    printed as `needs-questions <artifact_id>`. Otherwise each due question (which
    includes never-attempted ones, via schedule.due's full-id-set contract) is
    printed as `due <artifact_id> <question_id> <text>`.
    """
    store = FileStore(manifest=manifest, questions=questions, ledger=ledger)
    lines = service.due_items(store=store, now=_now())
    for line in lines:
        if line.needs_questions:
            typer.echo(f"needs-questions {line.artifact_id}")
            continue
        for qid, text in line.questions:
            typer.echo(f"due {line.artifact_id} {qid} {text}")


@app.command(name="save-questions")
def save_questions_cmd(
    artifact_id: str = typer.Argument(..., help="The artifact_id."),
    hash_: str = typer.Option(..., "--hash", help="The artifact's current content hash."),
    manifest: str = typer.Option(DEFAULT_MANIFEST, "--manifest", help="Manifest path."),
    questions: str = typer.Option(DEFAULT_QUESTIONS, "--questions", help="Questions store."),
) -> None:
    """Store questions for an artifact (one per stdin line). Rejects a stale --hash."""
    store = FileStore(manifest=manifest, questions=questions, ledger=DEFAULT_LEDGER)
    ref = _find_ref(store, artifact_id)
    if ref is None:
        typer.echo(f"unknown artifact_id: {artifact_id}", err=True)
        raise typer.Exit(code=1)
    if hash_ != ref.content_hash:
        typer.echo(
            f"hash mismatch: --hash {hash_} != current {ref.content_hash} "
            "(questions must bind to current content)",
            err=True,
        )
        raise typer.Exit(code=1)

    lines = [ln.strip() for ln in sys.stdin.read().splitlines() if ln.strip()]
    qs = [Question(text=ln) for ln in lines]
    store.save_questions(artifact_id, ref.content_hash, qs)
    typer.echo(f"saved {len(qs)} questions for {artifact_id} @ {ref.content_hash}")


@app.command(name="record-attempt")
def record_attempt_cmd(
    person: str = typer.Option(..., "--as", help="The reviewer."),
    question_id: str = typer.Option(..., "--question", help="The question_id."),
    artifact_id: str = typer.Option(..., "--artifact", help="The artifact_id."),
    passed: bool = typer.Option(None, "--passed/--failed", help="Pass or fail the question."),
    score: float = typer.Option(1.0, "--score", help="Score 0-1."),
    manifest: str = typer.Option(DEFAULT_MANIFEST, "--manifest", help="Manifest path."),
    questions: str = typer.Option(DEFAULT_QUESTIONS, "--questions", help="Questions store."),
    ledger: str = typer.Option(DEFAULT_LEDGER, "--ledger", help="Attempt ledger."),
) -> None:
    """Append one attempt to the ledger (append-only). State is recomputed on read."""
    if passed is None:
        typer.echo("specify --passed or --failed", err=True)
        raise typer.Exit(code=1)
    store = FileStore(manifest=manifest, questions=questions, ledger=ledger)
    ref = _find_ref(store, artifact_id)
    if ref is None:
        typer.echo(f"unknown artifact_id: {artifact_id}", err=True)
        raise typer.Exit(code=1)

    attempt = Attempt(
        person=person,
        artifact_id=artifact_id,
        question_id=question_id,
        content_hash=ref.content_hash,
        passed=passed,
        score=score,
        ts=_now(),
    )
    store.append_attempt(attempt)
    typer.echo(f"recorded {'pass' if passed else 'fail'} for {question_id}")


@app.command()
def coverage(
    person: str = typer.Option(None, "--as", help="The reviewer (informational)."),
    manifest: str = typer.Option(DEFAULT_MANIFEST, "--manifest", help="Manifest path."),
    questions: str = typer.Option(DEFAULT_QUESTIONS, "--questions", help="Questions store."),
    ledger: str = typer.Option(DEFAULT_LEDGER, "--ledger", help="Attempt ledger."),
) -> None:
    """Report covered/total, ratio, orphan hotlist, and the weakness map."""
    store = FileStore(manifest=manifest, questions=questions, ledger=ledger)
    report = service.coverage_report(store=store)

    pct = f"{report.ratio * 100:.1f}%"
    typer.echo(f"coverage: {report.covered}/{report.total} ({pct})")
    if report.orphans:
        typer.echo("orphans (cognitive-debt hotlist):")
        for aid in report.orphans:
            typer.echo(f"  - {aid}")
    else:
        typer.echo("orphans: none")

    if report.weakness:
        typer.echo("weakness map (repeatedly-failed):")
        for w in sorted(report.weakness, key=lambda x: -x.fail_count):
            typer.echo(f"  - {w.question_id} ({w.artifact_id}) fails={w.fail_count}")
    else:
        typer.echo("weakness map: none")


@app.command()
def review(
    artifact_id: str = typer.Argument(..., help="The artifact_id to review."),
    person: str = typer.Option(..., "--as", help="The reviewer."),
    manifest: str = typer.Option(DEFAULT_MANIFEST, "--manifest", help="Manifest path."),
    questions: str = typer.Option(DEFAULT_QUESTIONS, "--questions", help="Questions store."),
    ledger: str = typer.Option(DEFAULT_LEDGER, "--ledger", help="Attempt ledger."),
    n: int = typer.Option(DEFAULT_N_QUESTIONS, "--n", help="Number of questions to generate."),
) -> None:
    """Headless self-drive: generate questions (if needed), grade answers, record attempts.

    This is the only LLM-calling path (keyed AnthropicLLM via `_make_llm`). The
    agent-driven loop uses the primitives above instead (keyless).
    """
    store = FileStore(manifest=manifest, questions=questions, ledger=ledger)
    ref = _find_ref(store, artifact_id)
    if ref is None:
        typer.echo(f"unknown artifact_id: {artifact_id}", err=True)
        raise typer.Exit(code=1)

    text = Path(ref.path).read_text(encoding="utf-8")
    llm = _make_llm()

    qs = service.ensure_questions(artifact_id, store=store, llm=llm, n=n)

    answers: list[str] = []
    for q in qs:
        typer.echo(q.text)
        answers.append(input())

    qa_pairs = list(zip((q.text for q in qs), answers))
    verdict = service.grade_set(text, qa_pairs, llm=llm)
    typer.echo(
        f"verdict: passed={verdict.passed} score={verdict.score} — {verdict.rationale}"
    )

    # Headless grades the answer set as a whole; record each question with that verdict.
    ts = _now()
    for q in qs:
        store.append_attempt(
            Attempt(
                person=person,
                artifact_id=artifact_id,
                question_id=q.id,
                content_hash=ref.content_hash,
                passed=verdict.passed,
                score=verdict.score,
                ts=ts,
            )
        )
    typer.echo(f"recorded {len(qs)} attempts for {artifact_id}")


if __name__ == "__main__":  # pragma: no cover
    app()
