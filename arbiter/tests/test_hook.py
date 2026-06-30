from pathlib import Path
import importlib.util


_HOOK_PATH = Path(__file__).resolve().parent.parent / "hooks" / "pretooluse_gate.py"


def load_hook():
    spec = importlib.util.spec_from_file_location("pretooluse_gate", _HOOK_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _approved(tmp_path):
    from khala.arbiter.ledger import Ledger
    from khala.arbiter.artifacts import Artifact
    led = Ledger(tmp_path / "docs", now=lambda: "t")
    sid = led.record("spec", "A")
    artifact = Artifact.load(led._resolve(sid))
    artifact.meta["status"] = "approved"
    artifact.meta["content_hash"] = artifact.recompute_hash()
    artifact.save()
    from khala.arbiter.gate import Gate
    Gate(tmp_path, now=lambda: "t").begin_implementation(sid)
    return sid


def test_decide_allows_non_edit_tool(tmp_path):
    hook = load_hook()
    d = hook.decide({"tool_name": "Read", "tool_input": {"file_path": "src/x.py"},
                     "cwd": str(tmp_path)}, now=lambda: "t")
    assert d["allow"] is True


def test_decide_allows_source_with_approved_active_spec(tmp_path):
    _approved(tmp_path)
    hook = load_hook()
    d = hook.decide({"tool_name": "Edit", "tool_input": {"file_path": str(tmp_path / "src/x.py")},
                     "cwd": str(tmp_path)}, now=lambda: "t")
    assert d["allow"] is True


def test_decide_denies_source_without_marker(tmp_path):
    (tmp_path / "docs").mkdir()
    hook = load_hook()
    d = hook.decide({"tool_name": "Write", "tool_input": {"file_path": str(tmp_path / "src/x.py")},
                     "cwd": str(tmp_path)}, now=lambda: "t")
    assert d["allow"] is False
    assert "활성 spec" in d["reason"]


def test_decide_blocks_path_traversal_disguised_as_docs(tmp_path):
    # "docs/../src/evil.py" must NOT be let through as a docs/** allow-glob match
    (tmp_path / "docs").mkdir()
    hook = load_hook()
    sneaky = str(tmp_path / "docs" / ".." / "src" / "evil.py")
    d = hook.decide({"tool_name": "Write", "tool_input": {"file_path": sneaky},
                     "cwd": str(tmp_path)}, now=lambda: "t")
    assert d["allow"] is False  # normalized to src/evil.py -> default-deny
