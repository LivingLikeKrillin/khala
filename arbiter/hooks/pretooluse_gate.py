"""Claude Code PreToolUse hook: blocks code edits unless the active spec is approved."""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from specledger.config import SpecledgerConfig  # noqa: E402
from specledger.gate import Gate  # noqa: E402
from specledger.ledger import Ledger  # noqa: E402

# known gap (MVP): the Bash tool can also write files (echo/tee/python -c) and is
# NOT intercepted here — only first-class file-edit tools are gated. Register this
# hook with a matcher of "Write|Edit|MultiEdit" in settings.json.
_EDIT_TOOLS = {"Write", "Edit", "MultiEdit"}


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _extract_paths(tool_input: dict) -> list[str]:
    paths = []
    if "file_path" in tool_input:
        paths.append(tool_input["file_path"])
    for edit in tool_input.get("edits", []) or []:
        if "file_path" in edit:
            paths.append(edit["file_path"])
    return paths


def decide(payload: dict, now=_utc_now) -> dict:
    if payload.get("tool_name") not in _EDIT_TOOLS:
        return {"allow": True, "reason": "non-edit tool"}
    cwd = Path(payload.get("cwd", ".")).resolve()
    root = Path(os.environ.get("SPECLEDGER_ROOT", cwd)).resolve()
    docs = Path(os.environ.get("SPECLEDGER_DOCS", cwd / "docs")).resolve()
    if not docs.exists():
        return {"allow": True, "reason": "no specledger docs root; not governed"}
    rel = []
    for p in _extract_paths(payload.get("tool_input", {})):
        # resolve() normalizes ".." so "docs/../src/x.py" cannot masquerade as a
        # docs/** allow-glob match and bypass the gate (path-traversal defense)
        ap = Path(p).resolve()
        try:
            rel.append(str(ap.relative_to(root)).replace("\\", "/"))
        except ValueError:
            rel.append(str(ap).replace("\\", "/"))
    gate = Gate(root, now=now)
    ledger = Ledger(docs, now=now)
    res = gate.check_gate(rel, ledger, SpecledgerConfig.load(root),
                          tool_name=payload.get("tool_name", ""))
    return {"allow": res["allowed"], "reason": res["reason"]}


def main() -> int:
    payload = json.load(sys.stdin)
    d = decide(payload)
    if d["allow"]:
        return 0
    print(f"[specledger] blocked: {d['reason']}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
