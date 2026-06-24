from __future__ import annotations

import pytest

pytest.importorskip("a2a.compat.v0_3.types")

from nexus.a2a.external_ingest_skill import (  # noqa: E402
    EXTERNAL_LABEL,
    ExternalIngestOutcome,
    build_external_ingest_artifact,
    compute_source_hash,
    extract_external_spec,
    validate_external_spec,
)

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from nexus.a2a.config import A2AConfig  # noqa: E402
from nexus.a2a.server import mount_a2a  # noqa: E402
from nexus.auth.principal import hash_token  # noqa: E402

_WRITE = "ext-writer-token"
_READ = "read-token"
_PRINCIPALS = [
    {"name": "reader", "token_sha256": hash_token(_READ),
     "tenant": "acme", "clearance": "INTERNAL"},
    {"name": "depositor", "token_sha256": hash_token(_WRITE),
     "tenant": "acme", "clearance": "INTERNAL", "capabilities": ["ingest_external"]},
]


def _csf(body="# Title\n\n본문", source_tool="manifest", source_id="p-1", title="Payment PRD"):
    return {
        "id": f"ext-{source_tool}-{source_id}",
        "kind": "PRD",
        "title": title,
        "provenance": {
            "source_tool": source_tool,
            "source_id": source_id,
            "source_url": "https://manifest.app/p-1",
            "source_hash": compute_source_hash(body),
        },
        "body": body,
    }


def _params(csf):
    return {"message": {"parts": [{"kind": "data", "data": csf}]}}


def test_extract_returns_doc_when_all_required_present():
    csf = _csf()
    assert extract_external_spec(_params(csf)) == csf


def test_extract_returns_none_when_provenance_missing():
    csf = _csf()
    del csf["provenance"]["source_hash"]
    assert extract_external_spec(_params(csf)) is None


def test_validate_accepts_well_formed_csf():
    assert validate_external_spec(_csf()) is None


def test_validate_rejects_id_not_matching_provenance():
    csf = _csf()
    csf["id"] = "ext-wrong-id"
    assert "id must be" in validate_external_spec(csf)


def test_validate_rejects_source_hash_mismatch():
    csf = _csf()
    csf["body"] = "tampered body"  # hash no longer matches
    assert "source_hash" in validate_external_spec(csf)


def test_build_artifact_completed_carries_labels_and_never_echoes_body():
    csf = _csf(body="비밀 본문")
    outcome = ExternalIngestOutcome(
        resource_rid="doc_x", labels=[EXTERNAL_LABEL], chunks_indexed=3,
        idempotent_hit=False, source_hash=csf["provenance"]["source_hash"],
    )
    artifact_json, state, reason = build_external_ingest_artifact(outcome, csf, "acme")
    assert state == "completed"
    assert reason is None
    blob = repr(artifact_json)
    assert EXTERNAL_LABEL in blob
    assert "비밀 본문" not in blob


def test_build_artifact_failed_on_error():
    outcome = ExternalIngestOutcome(
        resource_rid="", labels=[], chunks_indexed=0, idempotent_hit=False,
        source_hash="h", error="boom",
    )
    _aj, state, reason = build_external_ingest_artifact(outcome, _csf(), "acme")
    assert state == "failed"
    assert reason == "boom"


def test_build_artifact_quarantined_maps_to_failed():
    csf = _csf()
    outcome = ExternalIngestOutcome(
        resource_rid="doc_x", labels=[EXTERNAL_LABEL], chunks_indexed=0,
        idempotent_hit=False, source_hash=csf["provenance"]["source_hash"],
        quarantined=True,
    )
    _aj, state, reason = build_external_ingest_artifact(outcome, csf, "acme")
    assert state == "failed"
    assert "격리" in reason or "quarantined" in reason


def test_build_artifact_clean_still_completed_with_quarantined_false_default():
    csf = _csf()
    outcome = ExternalIngestOutcome(
        resource_rid="doc_x", labels=[EXTERNAL_LABEL], chunks_indexed=2,
        idempotent_hit=False, source_hash=csf["provenance"]["source_hash"],
    )
    _aj, state, reason = build_external_ingest_artifact(outcome, csf, "acme")
    assert state == "completed"
    assert reason is None


class _ExtStore:
    """in-memory stand-in for Nexus ingest+index, wired as external_ingest_fn."""

    def __init__(self):
        self.docs: dict[tuple[str, str], dict] = {}
        self.ingests = 0
        self.hits = 0

    def ingest_fn(self, doc: dict, tenant: str) -> ExternalIngestOutcome:
        self.ingests += 1
        shash = doc["provenance"]["source_hash"]
        key = (tenant, doc["id"])
        prior = self.docs.get(key)
        hit = prior is not None and prior["source_hash"] == shash
        if hit:
            self.hits += 1
        self.docs[key] = {"source_hash": shash, "body": doc["body"]}
        return ExternalIngestOutcome(
            resource_rid=f"doc_{doc['id']}", labels=[EXTERNAL_LABEL],
            chunks_indexed=0 if hit else 2, idempotent_hit=hit, source_hash=shash,
        )


def _app(ext_fn) -> FastAPI:
    app = FastAPI()
    mount_a2a(
        app,
        A2AConfig(enabled=True, base_url="http://nexus.test", principals=_PRINCIPALS),
        answer_fn=lambda q, t, c: None,
        external_ingest_fn=ext_fn,
    )
    return app


def _send(client, token, csf):
    body = {
        "jsonrpc": "2.0", "id": "1", "method": "message/send",
        "params": {"message": {
            "metadata": {"skill_id": "ingest_external_spec"},
            "parts": [{"kind": "data", "data": csf}],
        }},
    }
    return client.post("/a2a", headers={"Authorization": f"Bearer {token}"}, json=body)


def test_deposit_with_capability_ingests_and_labels():
    store = _ExtStore()
    client = TestClient(_app(store.ingest_fn))
    r = _send(client, _WRITE, _csf())
    assert r.status_code == 200
    task = r.json()["result"]
    assert task["status"]["state"] == "completed"
    assert ("acme", "ext-manifest-p-1") in store.docs


def test_read_only_token_denied_and_never_ingests():
    store = _ExtStore()
    client = TestClient(_app(store.ingest_fn))
    r = _send(client, _READ, _csf())
    assert r.json()["error"]["code"] == -32003  # forbidden
    assert store.ingests == 0


def test_idempotent_redeposit_recognised():
    store = _ExtStore()
    client = TestClient(_app(store.ingest_fn))
    _send(client, _WRITE, _csf())
    _send(client, _WRITE, _csf())
    assert len(store.docs) == 1
    assert store.hits == 1


def test_changed_body_reindexes():
    store = _ExtStore()
    client = TestClient(_app(store.ingest_fn))
    _send(client, _WRITE, _csf(body="v1"))
    _send(client, _WRITE, _csf(body="v2"))  # same id, new source_hash
    assert store.hits == 0


def test_invalid_csf_source_hash_rejected_before_ingest():
    store = _ExtStore()
    client = TestClient(_app(store.ingest_fn))
    bad = _csf()
    bad["body"] = "tampered"  # source_hash no longer matches body
    r = _send(client, _WRITE, bad)
    assert r.json()["error"]["code"] == -32602  # invalid params
    assert store.ingests == 0


from nexus.a2a.card import build_agent_card  # noqa: E402


def test_card_advertises_external_ingest_skill():
    card = build_agent_card(
        A2AConfig(enabled=True, base_url="http://nexus.test", principals=[])
    )
    ids = {s["id"] for s in card["skills"]}
    assert "ingest_external_spec" in ids
    assert "ingest_governed_doc" in ids  # 기존 것 회귀 없음
