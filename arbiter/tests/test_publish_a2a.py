"""specledger as an A2A client (SPEC §5.3); A2A is the sole publish transport (SPEC §16).

`A2ANexusSink` is a thin JSON-RPC client (no SDK, urllib by default) that discovers Nexus's
agent card, confirms the `ingest_governed_doc` skill, sends the governed-doc DataPart with the
write token, and maps a denied/failed task to the graceful `{published: False, reason}` contract
`publish()` already returns. The bespoke `NexusHttpSink` HTTP POST has been retired — `publish()`
always builds an `A2ANexusSink`.
"""

import specledger.publish as publish_module
from specledger.config import SpecledgerConfig
from specledger.ledger import Ledger
from specledger.publish import (
    INGEST_SKILL,
    A2ANexusSink,
    _build_sink,
    publish,
)


class FakeTransport:
    """In-memory stand-in for the urllib transport: canned card + rpc responses."""

    def __init__(self, card=None, card_status=200, rpc=None, rpc_status=200):
        self._card = card if card is not None else _card_with_ingest()
        self._card_status = card_status
        self._rpc = rpc if rpc is not None else _completed_task()
        self._rpc_status = rpc_status
        self.card_url = None
        self.posts = []  # (url, headers, body)

    def get_json(self, url):
        self.card_url = url
        return self._card_status, self._card

    def post_json(self, url, headers, body):
        self.posts.append((url, headers, body))
        return self._rpc_status, self._rpc


def _card_with_ingest(skills=(INGEST_SKILL, "retrieve_grounded")):
    return {
        "name": "Nexus",
        "url": "http://nexus.test/a2a",
        "skills": [{"id": s} for s in skills],
    }


def _completed_task(state="completed"):
    return {
        "jsonrpc": "2.0",
        "id": "1",
        "result": {"status": {"state": state}, "artifacts": []},
    }


def _failed_task(reason="거버넌스 문서가 격리되었습니다 (quarantined)"):
    return {
        "jsonrpc": "2.0",
        "id": "1",
        "result": {
            "status": {"state": "failed", "message": {"parts": [{"text": reason}]}},
            "artifacts": [],
        },
    }


def _rpc_error(code=-32003, message="forbidden: ingest_governed capability required"):
    return {"jsonrpc": "2.0", "id": "1", "error": {"code": code, "message": message}}


# ── transport: A2A is the sole sink; bespoke NexusHttpSink retired (SPEC §16) ──


def test_publish_builds_a2a_sink_from_url():
    cfg = SpecledgerConfig(nexus={"url": "http://nexus.test"})
    assert isinstance(_build_sink(cfg), A2ANexusSink)


def test_publish_builds_a2a_sink_from_base_url():
    cfg = SpecledgerConfig(nexus={"base_url": "http://nexus.test"})
    assert isinstance(_build_sink(cfg), A2ANexusSink)


def test_nexus_http_sink_is_retired():
    """The bespoke point-to-point HTTP sink is gone — A2A is the only transport."""
    assert not hasattr(publish_module, "NexusHttpSink")


# ── A2ANexusSink behaviour ──


def test_a2a_sink_discovers_card_and_sends_data_part():
    transport = FakeTransport()
    sink = A2ANexusSink("http://nexus.test", token="write-tok", transport=transport)
    sink.ingest({"id": "SPEC-1", "title": "T", "status": "approved",
                 "content_hash": "abc", "body": "x"})

    # card discovered at the well-known path
    assert transport.card_url == "http://nexus.test/.well-known/agent-card.json"
    # one rpc POST, to the card-advertised url, carrying the write token
    url, headers, body = transport.posts[0]
    assert url == "http://nexus.test/a2a"
    assert headers["Authorization"] == "Bearer write-tok"
    # message/send with skill_id + a single data part carrying the payload
    msg = body["params"]["message"]
    assert body["method"] == "message/send"
    assert msg["metadata"]["skill_id"] == INGEST_SKILL
    part = msg["parts"][0]
    assert part["kind"] == "data"
    assert part["data"]["content_hash"] == "abc"


def test_a2a_sink_raises_when_card_lacks_skill():
    transport = FakeTransport(card=_card_with_ingest(skills=("retrieve_grounded",)))
    sink = A2ANexusSink("http://nexus.test", transport=transport)
    try:
        sink.ingest({"id": "S", "title": "T", "status": "approved",
                     "content_hash": "h", "body": "b"})
        raise AssertionError("expected raise on missing skill")
    except RuntimeError as exc:
        assert INGEST_SKILL in str(exc)
    # never POSTed when the skill is absent
    assert transport.posts == []


def test_a2a_sink_raises_on_card_discovery_failure():
    transport = FakeTransport(card={}, card_status=404)
    sink = A2ANexusSink("http://nexus.test", transport=transport)
    try:
        sink.ingest({"id": "S", "title": "T", "status": "approved",
                     "content_hash": "h", "body": "b"})
        raise AssertionError("expected raise on card discovery failure")
    except RuntimeError:
        pass


def test_a2a_sink_raises_on_jsonrpc_error():
    transport = FakeTransport(rpc=_rpc_error(), rpc_status=403)
    sink = A2ANexusSink("http://nexus.test", token="read-only", transport=transport)
    try:
        sink.ingest({"id": "S", "title": "T", "status": "approved",
                     "content_hash": "h", "body": "b"})
        raise AssertionError("expected raise on denial")
    except RuntimeError as exc:
        assert "forbidden" in str(exc)


def test_a2a_sink_raises_on_failed_task():
    transport = FakeTransport(rpc=_failed_task("quarantined"))
    sink = A2ANexusSink("http://nexus.test", transport=transport)
    try:
        sink.ingest({"id": "S", "title": "T", "status": "approved",
                     "content_hash": "h", "body": "b"})
        raise AssertionError("expected raise on failed task")
    except RuntimeError as exc:
        assert "quarantined" in str(exc)


# ── publish() integration: payload provenance + graceful parity ──


def test_publish_payload_carries_content_hash(tmp_path):
    led = Ledger(tmp_path, now=lambda: "t")
    sid = led.record("spec", "body text")
    art_path = led._resolve(sid)
    # simulate an approval stamp: content_hash written to frontmatter
    from specledger.artifacts import Artifact
    art = Artifact.load(art_path)
    art.meta["content_hash"] = "stamped-hash-123"
    art.save()

    class CaptureSink:
        def __init__(self):
            self.payload = None

        def ingest(self, payload):
            self.payload = payload
            return {}

    sink = CaptureSink()
    publish(led, sid, SpecledgerConfig(nexus={"url": "http://x"}), sink=sink)
    assert sink.payload["content_hash"] == "stamped-hash-123"


def test_publish_a2a_denied_is_graceful(tmp_path):
    led = Ledger(tmp_path, now=lambda: "t")
    sid = led.record("spec", "A")
    transport = FakeTransport(rpc=_rpc_error(), rpc_status=403)
    sink = A2ANexusSink("http://nexus.test", token="read-only", transport=transport)
    res = publish(led, sid, SpecledgerConfig(nexus={"url": "http://x"}), sink=sink)
    assert res["published"] is False
    assert "forbidden" in res["reason"]


def test_publish_a2a_completed_is_published(tmp_path):
    led = Ledger(tmp_path, now=lambda: "t")
    sid = led.record("spec", "A")
    sink = A2ANexusSink("http://nexus.test", token="write", transport=FakeTransport())
    res = publish(led, sid, SpecledgerConfig(nexus={"url": "http://x"}), sink=sink)
    assert res["published"] is True
