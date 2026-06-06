import pytest
from specledger.ledger import Ledger
from specledger.artifacts import Artifact, Status
from specledger.critique import critique, RUBRIC
from specledger.errors import CritiqueError
from helpers import FakeCritic


def led(docs_root):
    return Ledger(docs_root, now=lambda: "2026-06-06T13:00Z")


def test_critique_writes_sidecar_and_sets_in_review(docs_root):
    ledger = led(docs_root)
    sid = ledger.record("spec", "A")
    from specledger.sidecar import Sidecar
    issues = critique(ledger, sid, FakeCritic(), now=lambda: "2026-06-06T13:00Z")
    assert issues[0].issue_id == "I-001"
    sc = Sidecar.read(docs_root / ".reviews" / f"{sid}.md")
    assert sc.critiqued_hash == Artifact.load(ledger._resolve(sid)).recompute_hash()
    assert Artifact.load(ledger._resolve(sid)).status == Status.IN_REVIEW


def test_critique_passes_linked_adr_bodies(docs_root):
    ledger = led(docs_root)
    aid = ledger.record("adr", "Decision")
    sid = ledger.record("spec", "A")
    art = Artifact.load(ledger._resolve(sid))
    art.meta["linked_adrs"] = [aid]
    art.save()
    fc = FakeCritic()
    critique(ledger, sid, fc, now=lambda: "t")
    assert any("Decision" in body for body in fc.seen[1])


def test_critique_fail_closed(docs_root):
    ledger = led(docs_root)
    sid = ledger.record("spec", "A")
    with pytest.raises(CritiqueError):
        critique(ledger, sid, FakeCritic(boom=True), now=lambda: "t")
    assert Artifact.load(ledger._resolve(sid)).status == Status.DRAFT


class _Block:
    type = "text"

    def __init__(self, text):
        self.text = text


class _Resp:
    def __init__(self, text):
        self.content = [_Block(text)]


class _Client:
    def __init__(self, text):
        self._text = text
        self.messages = self

    def create(self, **kw):
        return _Resp(self._text)


def test_anthropic_critic_parses_json():
    from specledger.critique import AnthropicCritic
    client = _Client('[{"category":"scope-creep","severity":"low","description":"x"}]')
    crit = AnthropicCritic(client=client)
    assert crit.find_issues("body", [], RUBRIC) == [("scope-creep", "low", "x")]
