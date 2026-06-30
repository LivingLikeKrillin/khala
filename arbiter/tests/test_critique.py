import pytest
from khala.arbiter.ledger import Ledger
from khala.arbiter.artifacts import Artifact, Status
from khala.arbiter.critique import critique, RUBRIC
from khala.arbiter.errors import CritiqueError
from helpers import FakeCritic


def led(docs_root):
    return Ledger(docs_root, now=lambda: "2026-06-06T13:00Z")


def test_critique_writes_sidecar_and_sets_in_review(docs_root):
    ledger = led(docs_root)
    sid = ledger.record("spec", "A")
    from khala.arbiter.sidecar import Sidecar
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
    from khala.arbiter.critique import AnthropicCritic
    client = _Client('[{"category":"scope-creep","severity":"low","description":"x"}]')
    crit = AnthropicCritic(client=client)
    assert crit.find_issues("body", [], RUBRIC) == [("scope-creep", "low", "x")]


def test_anthropic_critic_constructs_without_api_key(monkeypatch):
    """Server boot must not require the key: construction is keyless (lazy client)."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    from khala.arbiter.critique import AnthropicCritic
    AnthropicCritic()  # no KeyError — the key is only read when critique actually runs


def test_find_issues_without_key_raises_clear_error(monkeypatch):
    """Calling critique without a key fails with an actionable message, not a bare KeyError."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    from khala.arbiter.critique import AnthropicCritic
    crit = AnthropicCritic()
    with pytest.raises(Exception) as exc:
        crit.find_issues("body", [], RUBRIC)
    assert "ANTHROPIC_API_KEY" in str(exc.value)


def test_injected_client_never_reads_env(monkeypatch):
    """An injected client works with no key in the environment (offline/local)."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    from khala.arbiter.critique import AnthropicCritic
    client = _Client('[{"category":"undefined","severity":"low","description":"y"}]')
    crit = AnthropicCritic(client=client)
    assert crit.find_issues("body", [], RUBRIC) == [("undefined", "low", "y")]
