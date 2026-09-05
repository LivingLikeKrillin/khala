"""`status()` reports; it does not edit what it reports on.

`SPEC-arbiter-status-is-read-only` §5. The tests are grouped by the property each one
pins, because the risk the SPEC names is that fixing one half silently drops the other:
the read-only property and the grouping invariant travel through different report fields.
"""

from __future__ import annotations

import hashlib

import pytest

from khala.arbiter.artifacts import Artifact
from khala.arbiter.config import ArbiterConfig
from khala.arbiter.gate import Gate
from khala.arbiter.ledger import Ledger

NOW = "2026-09-05T00:00:00Z"


def make_ledger(root):
    return Ledger(root, now=lambda: NOW)


def _digest(root) -> dict[str, str]:
    """Every artifact file's bytes, keyed by path — the whole-ledger fingerprint."""
    out = {}
    for d in ("specs", "adr"):
        for p in sorted((root / d).glob("*.md")):
            out[p.name] = hashlib.sha256(p.read_bytes()).hexdigest()
    return out


def _stamped_spec(led, root, title="A") -> Artifact:
    sid = led.record("spec", title)
    a = Artifact.load(root / "specs" / f"{sid}.md")
    a.meta["status"] = "approved"
    a.meta["content_hash"] = a.recompute_hash()
    a.save()
    return Artifact.load(a.path)


def _drifted_spec(led, root, title="A") -> Artifact:
    a = _stamped_spec(led, root, title)
    a.body += "\nan edit that did not update the stamp\n"
    a.save()
    return Artifact.load(a.path)


def _unstamped_approved_spec(led, root, title="B") -> Artifact:
    sid = led.record("spec", title)
    a = Artifact.load(root / "specs" / f"{sid}.md")
    a.meta["status"] = "approved"  # promoted with no content_hash at all
    a.save()
    return Artifact.load(a.path)


def _tampered_adr(led, root, title="Decide") -> Artifact:
    aid = led.record("adr", title)
    p = led._resolve(aid)
    a = Artifact.load(p)
    a.meta["status"] = "accepted"
    a.meta["content_hash"] = a.recompute_hash()
    a.save()
    a2 = Artifact.load(p)
    a2.body += "\nin-place amendment\n"
    a2.save()
    return Artifact.load(p)


# ── §5.1 the read-only property ──────────────────────────────────────────────

def test_status_leaves_every_file_byte_identical(docs_root):
    """The assertion that fails before the change: all three findings, no writes."""
    led = make_ledger(docs_root)
    drifted = _drifted_spec(led, docs_root)
    unstamped = _unstamped_approved_spec(led, docs_root)
    adr = _tampered_adr(led, docs_root)

    before = _digest(docs_root)
    rep = {r["id"]: r for r in led.status()}
    assert _digest(docs_root) == before

    assert rep[drifted.id]["needs_review"] is True
    assert rep[unstamped.id]["needs_review"] is True
    assert rep[adr.id]["tampered"] is True


def test_status_on_a_clean_ledger_finds_nothing_and_writes_nothing(docs_root):
    """Negative control — the byte-identity test above must not pass on an empty finding set."""
    led = make_ledger(docs_root)
    _stamped_spec(led, docs_root)
    before = _digest(docs_root)
    rep = led.status()
    assert _digest(docs_root) == before
    assert [r for r in rep if r["needs_review"] or r["tampered"]] == []


def test_status_is_repeatable_because_it_never_repairs(docs_root):
    """Two calls report the same thing; before the change the second saw a demoted file."""
    led = make_ledger(docs_root)
    a = _drifted_spec(led, docs_root)
    first = {r["id"]: dict(r) for r in led.status()}
    second = {r["id"]: dict(r) for r in led.status()}
    assert first == second
    assert first[a.id]["needs_review"] is True


# ── §5.2/§5.3 the grouping invariant, one test per report field ──────────────

def _group_of(index_text: str, artifact_id: str) -> str:
    """Which '## ' heading the artifact's row falls under."""
    current = None
    for line in index_text.splitlines():
        if line.startswith("## "):
            current = line[3:].strip()
        elif artifact_id in line:
            return current
    raise AssertionError(f"{artifact_id} not present in the index")


def test_index_puts_a_stale_stamped_spec_under_review_not_approved(docs_root):
    led = make_ledger(docs_root)
    a = _drifted_spec(led, docs_root)
    text = led.index().read_text(encoding="utf-8")
    assert "검토중" in _group_of(text, a.id)


def test_index_puts_a_tampered_adr_under_review_not_approved(docs_root):
    """The I-002 half. Separate test: `tampered` is a different field from `needs_review`."""
    led = make_ledger(docs_root)
    a = _tampered_adr(led, docs_root)
    text = led.index().read_text(encoding="utf-8")
    assert "검토중" in _group_of(text, a.id)


def test_index_still_puts_an_intact_stamped_spec_under_approved(docs_root):
    led = make_ledger(docs_root)
    a = _stamped_spec(led, docs_root)
    text = led.index().read_text(encoding="utf-8")
    assert "승인" in _group_of(text, a.id)


def test_index_writes_no_artifact_file(docs_root):
    led = make_ledger(docs_root)
    _drifted_spec(led, docs_root)
    _tampered_adr(led, docs_root)
    before = _digest(docs_root)
    led.index()
    assert _digest(docs_root) == before


# ── §5.4 the gate keeps refusing, and still does not write ──────────────────

def test_check_gate_refuses_on_a_stale_stamp_and_leaves_the_file_alone(docs_root, tmp_path):
    led = make_ledger(docs_root)
    a = _drifted_spec(led, docs_root)
    gate = Gate(tmp_path, now=lambda: NOW)
    gate.begin_implementation(a.id)

    before = a.path.read_bytes()
    res = gate.check_gate(["src/app.py"], led, ArbiterConfig())
    assert res["allowed"] is False
    assert res["status"] == "in_review"
    assert a.path.read_bytes() == before


# ── §5.5 `needs_review` has a reader ────────────────────────────────────────

def test_cli_status_distinguishes_a_stale_stamp_from_an_opened_critique(docs_root, capsys):
    """§3.1 — without this, `needs_review` is data nothing reads."""
    from typer.testing import CliRunner

    from khala.arbiter.cli import build_cli

    led = make_ledger(docs_root)
    stale = _drifted_spec(led, docs_root, "Stale")
    critiqued_id = led.record("spec", "Critiqued")
    c = Artifact.load(docs_root / "specs" / f"{critiqued_id}.md")
    c.meta["status"] = "in_review"  # the documented meaning: a critique was opened
    c.save()

    app = build_cli(root=docs_root, docs=docs_root, critic=None)
    result = CliRunner().invoke(app, ["status"])
    assert result.exit_code == 0, result.output

    lines = {ln.split()[0]: ln for ln in result.stdout.splitlines() if ln.strip()}
    assert "needs_review" in lines[stale.id]
    assert "needs_review" not in lines[critiqued_id]


# ── §5.6 the migration discriminator, over the real repository ──────────────

def test_every_in_review_artifact_in_this_repo_has_a_sidecar():
    """§3.5 — an in_review artifact with no sidecar was demoted, not critiqued.

    Over the real ledger, not a fixture: it must fail the day an artifact is stranded.
    """
    from pathlib import Path
    root = Path(__file__).resolve().parents[2]
    if not (root / "specs").is_dir():  # pragma: no cover - checkout without the ledger
        pytest.skip("not the khala checkout")
    led = Ledger(root, now=lambda: NOW)
    stranded = [
        a.meta["id"]
        for a in (Artifact.load(p) for p in led._all_paths())
        if a.meta.get("status") == "in_review"
        and not (root / ".reviews" / f"{a.meta['id']}.md").exists()
    ]
    assert stranded == [], (
        "in_review with no critique sidecar — demoted by status(), not reviewed: "
        + ", ".join(stranded)
    )
