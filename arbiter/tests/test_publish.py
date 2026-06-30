from specledger.ledger import Ledger
from specledger.config import SpecledgerConfig
from specledger.publish import publish


class FakeSink:
    def __init__(self):
        self.payloads = []

    def ingest(self, payload):
        self.payloads.append(payload)
        return {"ok": True}


class BoomSink:
    def ingest(self, payload):
        raise RuntimeError("nexus down")


def test_publish_noop_without_nexus(tmp_path):
    led = Ledger(tmp_path, now=lambda: "t")
    sid = led.record("spec", "A")
    res = publish(led, sid, SpecledgerConfig())  # no sink consulted on the no-op path
    assert res["published"] is False


def test_publish_returns_structured_error_on_sink_failure(tmp_path):
    led = Ledger(tmp_path, now=lambda: "t")
    sid = led.record("spec", "A")
    cfg = SpecledgerConfig(nexus={"url": "http://x"})
    res = publish(led, sid, cfg, sink=BoomSink())
    assert res["published"] is False
    assert "nexus down" in res["reason"]


def test_publish_sends_payload(tmp_path):
    led = Ledger(tmp_path, now=lambda: "t")
    sid = led.record("spec", "A")
    sink = FakeSink()
    cfg = SpecledgerConfig(nexus={"url": "http://x"})
    res = publish(led, sid, cfg, sink=sink)
    assert res["published"] is True
    assert sink.payloads[0]["id"] == sid
    assert "body" in sink.payloads[0]
