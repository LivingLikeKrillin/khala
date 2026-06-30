from khala.arbiter.gate import Gate
from khala.arbiter.ledger import Ledger
from khala.arbiter.artifacts import Artifact
from khala.arbiter.config import ArbiterConfig


def test_begin_sets_single_active(tmp_path):
    g = Gate(tmp_path, now=lambda: "t")
    g.begin_implementation("SPEC-a", set_by="agent")
    assert g.active_spec() == "SPEC-a"
    g.begin_implementation("SPEC-b", set_by="user")
    assert g.active_spec() == "SPEC-b"


def test_end_clears(tmp_path):
    g = Gate(tmp_path, now=lambda: "t")
    g.begin_implementation("SPEC-a", set_by="agent")
    g.end_implementation()
    assert g.active_spec() is None


def _approved_spec(docs_root):
    led = Ledger(docs_root, now=lambda: "t")
    sid = led.record("spec", "A")
    artifact = Artifact.load(led._resolve(sid))
    artifact.meta["status"] = "approved"
    artifact.meta["content_hash"] = artifact.recompute_hash()
    artifact.save()
    return led, sid


def test_gate_denies_without_marker(tmp_path):
    led, _ = _approved_spec(tmp_path / "docs")
    g = Gate(tmp_path, now=lambda: "t")
    res = g.check_gate(["src/app.py"], led, ArbiterConfig())
    assert res["allowed"] is False
    assert "활성 spec" in res["reason"]


def test_gate_allows_when_active_spec_approved(tmp_path):
    led, sid = _approved_spec(tmp_path / "docs")
    g = Gate(tmp_path, now=lambda: "t")
    g.begin_implementation(sid)
    res = g.check_gate(["src/app.py"], led, ArbiterConfig())
    assert res["allowed"] is True
    assert res["spec_id"] == sid


def test_gate_denies_when_active_spec_unapproved(tmp_path):
    led = Ledger(tmp_path / "docs", now=lambda: "t")
    sid = led.record("spec", "A")  # draft
    g = Gate(tmp_path, now=lambda: "t")
    g.begin_implementation(sid)
    res = g.check_gate(["src/app.py"], led, ArbiterConfig())
    assert res["allowed"] is False
    assert res["status"] == "draft"


def test_allow_globs_bypass_gate(tmp_path):
    led = Ledger(tmp_path / "docs", now=lambda: "t")
    g = Gate(tmp_path, now=lambda: "t")
    res = g.check_gate(["docs/readme.md", "tests/test_x.py"], led, ArbiterConfig())
    assert res["allowed"] is True


def test_exempt_path_allows_and_logs(tmp_path):
    led = Ledger(tmp_path / "docs", now=lambda: "t")
    g = Gate(tmp_path, now=lambda: "t")
    cfg = ArbiterConfig(exempt_paths=["scripts/**"])
    res = g.check_gate(["scripts/gen.py"], led, cfg, tool_name="Write")
    assert res["allowed"] is True
    log = (tmp_path / ".arbiter" / "exempt.log").read_text(encoding="utf-8")
    assert "scripts/gen.py" in log
    assert "Write" in log  # tool name threaded into the exempt audit log


def test_mixed_allowed_and_denied_paths_denies(tmp_path):
    # one allow-glob path + one ungoverned source path -> whole call denied
    led = Ledger(tmp_path / "docs", now=lambda: "t")
    g = Gate(tmp_path, now=lambda: "t")
    res = g.check_gate(["docs/readme.md", "src/evil.py"], led, ArbiterConfig())
    assert res["allowed"] is False
