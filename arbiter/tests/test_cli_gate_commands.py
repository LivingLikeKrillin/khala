"""The CLI can open and close the gate it already knows how to check.

`begin_implementation` and `end_implementation` existed only as MCP tools, so a person
driving Arbiter from a terminal could run `check-gate`, be told "활성 spec 없음 —
begin_implementation 필요", and have no command to satisfy it. Doing this work required
importing `Gate` and calling it from a hand-written script — the exact complaint
`cli.py`'s own docstring makes about the governance core being unreachable by hand.
"""

from __future__ import annotations

import json

import pytest
from typer.testing import CliRunner

from khala.arbiter.artifacts import Artifact
from khala.arbiter.cli import build_cli
from helpers import FakeCritic

runner = CliRunner()


@pytest.fixture
def app(docs_root):
    return build_cli(root=docs_root, docs=docs_root, critic=FakeCritic())


def _run(app, *args):
    return runner.invoke(app, list(args))


def _marker(docs_root):
    return docs_root / ".arbiter" / "active.json"


def _approved_spec(app, docs_root) -> str:
    """A recorded SPEC, promoted and stamped, so the gate has something to allow."""
    sid = _run(app, "record", "spec", "Gate subject").output.strip().splitlines()[-1].strip()
    a = Artifact.load(docs_root / "specs" / f"{sid}.md")
    a.meta["status"] = "approved"
    a.meta["content_hash"] = a.recompute_hash()
    a.save()
    return sid


def test_begin_implementation_sets_the_active_spec(app, docs_root):
    sid = _approved_spec(app, docs_root)
    r = _run(app, "begin-implementation", sid)
    assert r.exit_code == 0, r.output
    assert sid in r.output
    assert json.loads(_marker(docs_root).read_text(encoding="utf-8"))["spec_id"] == sid


def test_begin_implementation_records_that_the_cli_set_it(app, docs_root):
    """`set_by` is the record of which surface opened the gate; the MCP tool writes "agent"."""
    sid = _approved_spec(app, docs_root)
    _run(app, "begin-implementation", sid)
    assert json.loads(_marker(docs_root).read_text(encoding="utf-8"))["set_by"] == "cli"


def test_begin_implementation_refuses_an_unknown_id_and_opens_nothing(app, docs_root):
    r = _run(app, "begin-implementation", "SPEC-does-not-exist")
    assert r.exit_code == 1
    assert not _marker(docs_root).exists()


def test_end_implementation_clears_the_active_spec(app, docs_root):
    sid = _approved_spec(app, docs_root)
    _run(app, "begin-implementation", sid)
    r = _run(app, "end-implementation")
    assert r.exit_code == 0, r.output
    assert not _marker(docs_root).exists()


def test_end_implementation_is_not_an_error_when_nothing_is_open(app, docs_root):
    """Mirrors Gate.end_implementation's unlink(missing_ok=True) — closing twice is fine."""
    r = _run(app, "end-implementation")
    assert r.exit_code == 0, r.output


def test_the_refusal_names_a_command_a_person_can_actually_type(app, docs_root):
    """The reason said `begin_implementation`, which was an MCP tool name and nothing else.

    Naming both surfaces, because the same string is shown to an agent through the
    pre-tool-use hook and to a person through `arbiter check-gate`.
    """
    reason = json.loads(_run(app, "check-gate", "src/app.py").output)["reason"]
    assert "arbiter begin-implementation" in reason
    assert "begin_implementation" in reason


def test_the_gate_can_now_be_satisfied_from_the_cli_alone(app, docs_root):
    """The point of the change: check → open → check, with no Python in between."""
    sid = _approved_spec(app, docs_root)

    before = json.loads(_run(app, "check-gate", "src/app.py").output)
    assert before["allowed"] is False
    assert before["spec_id"] is None

    _run(app, "begin-implementation", sid)
    after = json.loads(_run(app, "check-gate", "src/app.py").output)
    assert after["allowed"] is True
    assert after["spec_id"] == sid

    _run(app, "end-implementation")
    closed = json.loads(_run(app, "check-gate", "src/app.py").output)
    assert closed["allowed"] is False
