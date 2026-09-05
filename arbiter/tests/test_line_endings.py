"""Every file the arbiter writes must land LF-only, on every platform.

`Path.write_text(..., encoding="utf-8")` leaves `newline` at None, which on Windows
translates each "\n" to "\r\n". Nothing wrong reaches git — `.gitattributes` carries
`* text=auto eol=lf` — but in the working tree a single `arbiter status` rewrites whole
files in line endings only. That noise once cost a CI investigation a full round: the
diff looked like the cause of a `governance (ledger integrity)` failure and was not.

Two tests, because one alone does not hold the line:

* the behavioural ones below fail on Windows before the fix and are *vacuous* on Linux,
  where os.linesep is already "\n";
* `test_no_writer_leaves_newline_to_the_platform` reads the source instead, so Linux CI
  also catches a new writer that forgets `newline="\n"`.
"""

from __future__ import annotations

import ast
from pathlib import Path

from khala.arbiter.artifacts import Artifact
from khala.arbiter.gate import Gate
from khala.arbiter.ledger import Ledger
from khala.arbiter.sidecar import Issue, Sidecar

NOW = lambda: "2026-09-05"  # noqa: E731


def _assert_lf_only(path: Path) -> None:
    raw = path.read_bytes()
    crlf = raw.count(b"\r\n")
    assert b"\r\n" not in raw, (
        f"{path.name} was written with CRLF line endings "
        f"({crlf} of them out of {len(raw.splitlines())} lines)"
    )


def test_artifact_save_writes_lf_only(docs_root):
    p = docs_root / "specs" / "SPEC-crlf.md"
    p.write_text(
        "---\nid: SPEC-crlf\ntype: spec\nstatus: draft\n---\nline one\nline two\n",
        encoding="utf-8",
        newline="\n",
    )
    a = Artifact.load(p)
    a.meta["status"] = "in_review"
    a.save()
    _assert_lf_only(p)


def test_sidecar_write_writes_lf_only(docs_root):
    p = docs_root / ".reviews" / "SPEC-crlf.md"
    Sidecar(
        target="SPEC-crlf",
        critiqued_hash="deadbeef",
        critiqued_at=NOW(),
        issues=[Issue("I1", "missing-invariant", "high", "no invariant", "open")],
        narrative="first line\nsecond line\n",
    ).write(p)
    _assert_lf_only(p)


def test_ledger_record_and_index_write_lf_only(docs_root):
    ledger = Ledger(docs_root, NOW)
    aid = ledger.record("spec", "line endings")
    _assert_lf_only(ledger.specs / f"{aid}.md")
    _assert_lf_only(ledger.index())


def test_ledger_status_repair_leaves_lf_only(docs_root):
    """`status()` rewrites a SPEC whose stamp no longer matches — the observed trigger."""
    ledger = Ledger(docs_root, NOW)
    p = docs_root / "specs" / "SPEC-stamped.md"
    p.write_text(
        "---\nid: SPEC-stamped\ntype: spec\nstatus: approved\n"
        "content_hash: notthehash\n---\nbody one\nbody two\n",
        encoding="utf-8",
        newline="\n",
    )
    assert [e["needs_review"] for e in ledger.status("SPEC-stamped")] == [True]
    _assert_lf_only(p)


def test_gate_exempt_log_writes_lf_only(tmp_path):
    gate = Gate(tmp_path, NOW)
    gate._log_exempt("docs/whatever.md", "Write")
    gate._log_exempt("docs/other.md", "Edit")
    _assert_lf_only(tmp_path / ".arbiter" / "exempt.log")


SRC = Path(__file__).resolve().parents[1] / "src" / "khala" / "arbiter"


def _newline_is_lf(call: ast.Call) -> bool:
    for kw in call.keywords:
        if kw.arg == "newline":
            return isinstance(kw.value, ast.Constant) and kw.value.value == "\n"
    return False


def _writes_text(call: ast.Call) -> bool:
    """True for a text-mode write call that would inherit the platform's newline."""
    name = call.func.attr if isinstance(call.func, ast.Attribute) else None
    if name == "write_text":
        return True
    if name != "open":
        return False
    mode = next((kw.value for kw in call.keywords if kw.arg == "mode"), None)
    if mode is None and call.args:
        mode = call.args[0]
    if not isinstance(mode, ast.Constant) or not isinstance(mode.value, str):
        return False
    return ("w" in mode.value or "a" in mode.value) and "b" not in mode.value


def test_no_writer_leaves_newline_to_the_platform():
    offenders = []
    for path in sorted(SRC.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and _writes_text(node) and not _newline_is_lf(node):
                offenders.append(f"{path.name}:{node.lineno}")
    assert not offenders, (
        "text writes that leave `newline` unset — these emit CRLF on Windows; pass "
        "newline=LF explicitly: " + ", ".join(offenders)
    )
