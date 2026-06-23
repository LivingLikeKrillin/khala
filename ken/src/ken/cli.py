"""ken CLI — register / probe / coverage (the walking skeleton).

LLM seam: every command obtains its client via the module-level `_make_llm()`
factory (never `AnthropicLLM()` inline), so tests monkeypatch `ken.cli._make_llm`.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import typer

from ken.coverage import compute_coverage
from ken.judge import grade
from ken.llm import AnthropicLLM, LLMClient
from ken.probe import make_questions
from ken.registry import load_manifest, register as registry_register
from ken.vouch import load_vouches, record_vouch
from ken.models import Vouch

app = typer.Typer(help="ken — cognitive-debt meter")

DEFAULT_MANIFEST = "ken.manifest.yaml"
DEFAULT_LEDGER = "ken.ledger.jsonl"
DEFAULT_TTL_DAYS = 90
DEFAULT_N_QUESTIONS = 5


def _make_llm() -> LLMClient:
    """LLM factory — the test seam. Commands call this, never AnthropicLLM() inline."""
    return AnthropicLLM()


@app.command()
def register(
    path: str = typer.Argument(..., help="Path to the artifact to register."),
    manifest: str = typer.Option(DEFAULT_MANIFEST, "--manifest", help="Manifest path."),
) -> None:
    """Register an artifact into the manifest; prints its artifact_id."""
    ref = registry_register(path, manifest_path=manifest)
    typer.echo(f"registered {ref.path} {ref.artifact_id}")


@app.command()
def probe(
    artifact_id: str = typer.Argument(..., help="The artifact_id to probe."),
    person: str = typer.Option(..., "--as", help="The named voucher."),
    manifest: str = typer.Option(DEFAULT_MANIFEST, "--manifest", help="Manifest path."),
    ledger: str = typer.Option(DEFAULT_LEDGER, "--ledger", help="Vouch ledger path."),
    n: int = typer.Option(DEFAULT_N_QUESTIONS, "--n", help="Number of questions."),
) -> None:
    """Generate grounded questions, grade answers, record a vouch on pass."""
    refs = load_manifest(manifest)
    ref = next((r for r in refs if r.artifact_id == artifact_id), None)
    if ref is None:
        typer.echo(f"unknown artifact_id: {artifact_id}", err=True)
        raise typer.Exit(code=1)

    text = Path(ref.path).read_text(encoding="utf-8")
    llm = _make_llm()

    questions = make_questions(text, n=n, llm=llm)
    answers: list[str] = []
    for q in questions:
        typer.echo(q.text)
        answers.append(input())

    qa_pairs = list(zip((q.text for q in questions), answers))
    verdict = grade(text, qa_pairs, llm=llm)

    typer.echo(f"verdict: passed={verdict.passed} score={verdict.score} — {verdict.rationale}")

    if verdict.passed:
        vouch = Vouch(
            artifact_id=ref.artifact_id,
            person=person,
            content_hash=ref.content_hash,
            score=verdict.score,
            passed=True,
            n_questions=len(questions),
            ts=datetime.now(timezone.utc).isoformat(),
        )
        record_vouch(vouch, ledger_path=ledger)
        typer.echo(f"vouch recorded for {ref.artifact_id} by {person}")
    else:
        typer.echo("no vouch recorded (did not pass)")


@app.command()
def coverage(
    manifest: str = typer.Option(DEFAULT_MANIFEST, "--manifest", help="Manifest path."),
    ledger: str = typer.Option(DEFAULT_LEDGER, "--ledger", help="Vouch ledger path."),
    ttl_days: int = typer.Option(DEFAULT_TTL_DAYS, "--ttl-days", help="Vouch TTL in days."),
) -> None:
    """Report covered/total, ratio, and the orphan hotlist."""
    refs = load_manifest(manifest)  # carries live current_hash per ref
    vouches = load_vouches(ledger)
    now = datetime.now(timezone.utc).isoformat()
    report = compute_coverage(refs, vouches, now=now, ttl_days=ttl_days)

    pct = f"{report.ratio * 100:.1f}%"
    typer.echo(f"coverage: {report.covered}/{report.total} ({pct})")
    if report.orphans:
        typer.echo("orphans (cognitive-debt hotlist):")
        for aid in report.orphans:
            typer.echo(f"  - {aid}")
    else:
        typer.echo("orphans: none")


if __name__ == "__main__":  # pragma: no cover
    app()
