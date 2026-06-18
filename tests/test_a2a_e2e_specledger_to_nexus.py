"""Ecosystem E2E — specledger publishes to Nexus over A2A (Phase 3 exit criteria, in-process).

This is the *live end-to-end run* the Phase 3 SPEC §11/§3 asks for, in the form that is
deterministic and reproducible in CI: the **real** Nexus A2A server (`mount_a2a` → card +
JSON-RPC + capability gate + audit + ingest mapping) wired to the **real** specledger
`A2ANexusSink` + `publish()`, with no SDKs faked between them — the only stub is the DB-backed
ingest pipeline, replaced by an in-memory `_NexusStore` so the provenance loop is genuinely
exercised (the RAG indexing itself is covered by nexus's own suite).

Proves, across both tools over the wire:
- §3.2/§5.4 — a write-capable publish ingests the governed doc and its specledger `content_hash`
  round-trips as the ingest artifact's `approved_hash` (provenance preserved).
- §3.3/§5.5 — a read-only token is **denied** (403, audited); the pipeline is never reached.
- §3.4 — a quarantined doc and a denial both map to the graceful `{published: False, reason}`
  contract `publish()` already returns; idempotent re-publish yields one resource.
- §3.5 — classification is server-decided; the caller (specledger) never sends one.
"""

from __future__ import annotations

import pytest

# Cross-tool test: needs both packages + the A2A compat types. Skip cleanly otherwise so
# neither tool's isolated CI collects a hard failure.
pytest.importorskip("nexus")
pytest.importorskip("specledger")
pytest.importorskip("a2a.compat.v0_3.types")

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from structlog.testing import capture_logs  # noqa: E402

from nexus.a2a.config import A2AConfig  # noqa: E402
from nexus.a2a.ingest_skill import IngestOutcome  # noqa: E402
from nexus.a2a.server import mount_a2a  # noqa: E402
from nexus.auth.principal import hash_token  # noqa: E402
from specledger.artifacts import Artifact  # noqa: E402
from specledger.config import SpecledgerConfig  # noqa: E402
from specledger.ledger import Ledger  # noqa: E402
from specledger.publish import INGEST_SKILL, A2ANexusSink, publish  # noqa: E402

_BASE = "http://nexus.test"
_WRITE_TOKEN = "writer-token"
_READ_TOKEN = "read-only-token"
_PRINCIPALS = [
    {"name": "reader", "token_sha256": hash_token(_READ_TOKEN),
     "tenant": "acme", "clearance": "INTERNAL"},
    {"name": "specledger", "token_sha256": hash_token(_WRITE_TOKEN),
     "tenant": "acme", "clearance": "INTERNAL", "capabilities": ["ingest_governed"]},
]


class _NexusStore:
    """In-memory stand-in for Nexus ingest+index, wired as the server's ``ingest_fn``."""

    def __init__(self):
        self.docs: dict[tuple[str, str], dict] = {}
        self.ingests = 0
        self.hits = 0
        self.seen_classification_from_caller: list = []

    def ingest_fn(self, doc: dict, tenant: str) -> IngestOutcome:
        self.ingests += 1
        # §3.5: the caller must never send a classification — record whatever (if anything)
        # arrived so the test can assert it was absent / ignored.
        self.seen_classification_from_caller.append(doc.get("classification"))
        key = (tenant, doc["id"])
        prior = self.docs.get(key)
        hit = prior is not None and prior["approved_hash"] == doc["content_hash"]
        if hit:
            self.hits += 1
        self.docs[key] = {  # server decides classification, not the caller
            "approved_hash": doc["content_hash"],
            "classification": "INTERNAL",
            "body": doc["body"],
            "title": doc.get("title", ""),
        }
        return IngestOutcome(
            resource_rid=f"doc_{doc['id']}", classification="INTERNAL",
            chunks_indexed=0 if hit else 2, quarantined=False,
            approved_hash=doc["content_hash"], idempotent_hit=hit,
        )


def _quarantine_ingest(doc: dict, tenant: str) -> IngestOutcome:
    return IngestOutcome(
        resource_rid="", classification="UNKNOWN", chunks_indexed=0,
        quarantined=True, approved_hash=doc["content_hash"], idempotent_hit=False,
    )


class _TestClientTransport:
    """Drive the real Nexus ASGI app in-process as the A2ANexusSink's HTTP transport.

    Mirrors ``_UrllibTransport``'s ``(status, json)`` contract; strips the configured base so
    the well-known card path and the card-advertised rpc url both reach the TestClient.
    """

    def __init__(self, client: TestClient, base: str):
        self._c = client
        self._base = base

    def _path(self, url: str) -> str:
        return url[len(self._base):] if url.startswith(self._base) else url

    def get_json(self, url):
        r = self._c.get(self._path(url))
        return r.status_code, (r.json() if r.content else {})

    def post_json(self, url, headers, body):
        r = self._c.post(self._path(url), headers=headers, json=body)
        return r.status_code, (r.json() if r.content else {})


def _nexus_app(ingest_fn) -> FastAPI:
    app = FastAPI()
    mount_a2a(
        app,
        A2AConfig(enabled=True, base_url=_BASE, principals=_PRINCIPALS),
        answer_fn=lambda q, t, c: None,
        ingest_fn=ingest_fn,
    )
    return app


def _sink(app: FastAPI, token: str | None) -> A2ANexusSink:
    transport = _TestClientTransport(TestClient(app), _BASE)
    return A2ANexusSink(_BASE, token=token, transport=transport)


def _stamped_spec(tmp_path, body="# Payment Topics\n\n결제 서비스는 payment.events 토픽을 발행한다."):
    """Record a spec and stamp it as approved (content_hash in frontmatter), as `approve` does."""
    led = Ledger(tmp_path, now=lambda: "2026-06-18T00:00:00Z")
    sid = led.record("spec", "Payment Topics")
    art = Artifact.load(led._resolve(sid))
    art.body = body
    art.meta["status"] = "approved"
    art.meta["approved_by"] = "alice"
    art.meta["content_hash"] = art.recompute_hash()
    art.save()
    return led, sid, art.meta["content_hash"]


# ── §3.2/§5.4 — write-capable publish ingests; content_hash → approved_hash round-trips ──


def test_publish_over_a2a_ingests_and_preserves_provenance(tmp_path):
    led, sid, chash = _stamped_spec(tmp_path)
    store = _NexusStore()
    sink = _sink(_nexus_app(store.ingest_fn), token=_WRITE_TOKEN)

    res = publish(led, sid, SpecledgerConfig(nexus={"url": _BASE}), sink=sink)

    assert res["published"] is True
    # the doc reached the server under the principal's tenant (server-scoped, not caller-set)
    assert ("acme", sid) in store.docs
    stored = store.docs[("acme", sid)]
    # §5.4: specledger's content_hash is what Nexus persists as approved_hash
    assert stored["approved_hash"] == chash
    # §3.5: the caller never sent a classification; the server decided INTERNAL
    assert store.seen_classification_from_caller == [None]
    assert stored["classification"] == "INTERNAL"


def test_sink_sees_real_card_with_both_skills(tmp_path):
    """The real card advertises retrieve_grounded + ingest_governed_doc; the sink confirms it."""
    led, sid, _ = _stamped_spec(tmp_path)
    sink = _sink(_nexus_app(_NexusStore().ingest_fn), token=_WRITE_TOKEN)
    publish(led, sid, SpecledgerConfig(nexus={"url": _BASE}), sink=sink)  # forces discovery
    card = sink._card
    skill_ids = {s["id"] for s in card["skills"]}
    assert INGEST_SKILL in skill_ids
    assert "retrieve_grounded" in skill_ids


# ── §3.3/§5.5 — read-only token denied, audited, pipeline never reached ──


def test_read_only_token_is_denied_and_never_ingests(tmp_path):
    led, sid, _ = _stamped_spec(tmp_path)
    store = _NexusStore()
    sink = _sink(_nexus_app(store.ingest_fn), token=_READ_TOKEN)

    with capture_logs() as logs:
        res = publish(led, sid, SpecledgerConfig(nexus={"url": _BASE}), sink=sink)

    assert res["published"] is False
    assert "forbidden" in res["reason"]
    assert store.ingests == 0  # default-deny: the pipeline was never reached
    audit = [x for x in logs if x.get("event") == "a2a.audit"]
    assert any(a["denied"] and a["skill"] == INGEST_SKILL for a in audit)


# ── §3.4 — graceful parity: quarantine + idempotency ──


def test_quarantined_doc_maps_to_unpublished(tmp_path):
    led, sid, _ = _stamped_spec(tmp_path)
    sink = _sink(_nexus_app(_quarantine_ingest), token=_WRITE_TOKEN)

    res = publish(led, sid, SpecledgerConfig(nexus={"url": _BASE}), sink=sink)

    assert res["published"] is False
    assert "격리" in res["reason"] or "quarantined" in res["reason"]


def test_idempotent_republish_yields_one_resource(tmp_path):
    led, sid, _ = _stamped_spec(tmp_path)
    store = _NexusStore()
    app = _nexus_app(store.ingest_fn)
    cfg = SpecledgerConfig(nexus={"url": _BASE})

    first = publish(led, sid, cfg, sink=_sink(app, token=_WRITE_TOKEN))
    second = publish(led, sid, cfg, sink=_sink(app, token=_WRITE_TOKEN))

    assert first["published"] is True and second["published"] is True
    assert len(store.docs) == 1          # one resource, not two
    assert store.hits == 1               # the replay was recognised as idempotent
