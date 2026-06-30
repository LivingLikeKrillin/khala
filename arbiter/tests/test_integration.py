from khala.arbiter.ledger import Ledger
from khala.arbiter.gate import Gate
from khala.arbiter.config import ArbiterConfig
from khala.arbiter.artifacts import Artifact, Status
from khala.arbiter.critique import critique
from khala.arbiter.review import approve
from helpers import FakeCritic


def test_record_critique_fix_approve_then_gate_allows(tmp_path):
    docs = tmp_path / "docs"
    led = Ledger(docs, now=lambda: "t")
    gate = Gate(tmp_path, now=lambda: "t")
    cfg = ArbiterConfig()

    sid = led.record("spec", "Playlist Self-Update")
    gate.begin_implementation(sid)
    assert led.status(sid)[0]["status"] == "draft"
    assert gate.check_gate(["src/app.py"], led, cfg)["allowed"] is False

    critique(led, sid, FakeCritic(), now=lambda: "t")
    a = Artifact.load(led._resolve(sid))
    a.body += "\nadded the invariant\n"
    a.save()
    approve(led, sid, [{"issue_id": "I-001", "disposition": "accepted"}], "reviewer", now=lambda: "t")

    assert Artifact.load(led._resolve(sid)).status == Status.APPROVED
    assert gate.check_gate(["src/app.py"], led, cfg)["allowed"] is True


def test_tamper_after_approval_reblocks_gate(tmp_path):
    docs = tmp_path / "docs"
    led = Ledger(docs, now=lambda: "t")
    gate = Gate(tmp_path, now=lambda: "t")
    sid = led.record("spec", "A")
    critique(led, sid, FakeCritic(), now=lambda: "t")
    a = Artifact.load(led._resolve(sid))
    a.body += "\nfix\n"
    a.save()
    approve(led, sid, [{"issue_id": "I-001", "disposition": "accepted"}], "reviewer", now=lambda: "t")
    gate.begin_implementation(sid)
    assert gate.check_gate(["src/x.py"], led, ArbiterConfig())["allowed"] is True
    a2 = Artifact.load(led._resolve(sid))
    a2.body += "\nsneaky\n"
    a2.save()
    assert gate.check_gate(["src/x.py"], led, ArbiterConfig())["allowed"] is False
