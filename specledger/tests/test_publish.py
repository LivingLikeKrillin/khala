from specledger.ledger import Ledger
from specledger.config import SpecledgerConfig
from specledger.publish import publish


class FakeSink:
    def __init__(self):
        self.payloads = []

    def ingest(self, payload):
        self.payloads.append(payload)
        return {"ok": True}


def test_publish_noop_without_khala(tmp_path):
    led = Ledger(tmp_path, now=lambda: "t")
    sid = led.record("spec", "A")
    res = publish(led, sid, SpecledgerConfig(), sink=FakeSink())
    assert res["published"] is False


def test_publish_sends_payload(tmp_path):
    led = Ledger(tmp_path, now=lambda: "t")
    sid = led.record("spec", "A")
    sink = FakeSink()
    cfg = SpecledgerConfig(khala={"url": "http://x"})
    res = publish(led, sid, cfg, sink=sink)
    assert res["published"] is True
    assert sink.payloads[0]["id"] == sid
    assert "body" in sink.payloads[0]
