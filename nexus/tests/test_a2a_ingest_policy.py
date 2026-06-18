"""ingest_governed_doc policy + routing over the JSON-RPC surface (Phase 3, SPEC §5.5, §6).

The write skill requires the ``ingest_governed`` capability: a read-only token is denied
(403, audited), a write-capable token succeeds. Skill selection is by message metadata.
Driven via TestClient with an injected ingest service (no DB).
"""

from __future__ import annotations

import a2a.compat.v0_3.types as a2a_types
from fastapi import FastAPI
from fastapi.testclient import TestClient
from structlog.testing import capture_logs

from nexus.a2a.config import A2AConfig
from nexus.a2a.ingest_skill import IngestOutcome
from nexus.a2a.server import mount_a2a
from nexus.auth.principal import hash_token

_READ_TOKEN = "read-only-token"
_WRITE_TOKEN = "writer-token"
_PRINCIPALS = [
    {"name": "reader", "token_sha256": hash_token(_READ_TOKEN), "tenant": "acme", "clearance": "INTERNAL"},
    {"name": "writer", "token_sha256": hash_token(_WRITE_TOKEN), "tenant": "acme",
     "clearance": "INTERNAL", "capabilities": ["ingest_governed"]},
]

_DOC = {
    "id": "SPEC-x", "title": "X", "status": "approved", "approved_by": "u",
    "content_hash": "sha256:abc", "body": "# X\nbody", "source": "specs/SPEC-x.md",
}


def _ingest(doc, tenant):
    return IngestOutcome(
        resource_rid="doc_123", classification="INTERNAL", chunks_indexed=3,
        quarantined=False, approved_hash=doc["content_hash"], idempotent_hit=False,
    )


def _app(ingest_fn=_ingest) -> FastAPI:
    app = FastAPI()
    mount_a2a(app, A2AConfig(enabled=True, principals=_PRINCIPALS),
              answer_fn=lambda q, t, c: None, ingest_fn=ingest_fn)
    return app


def _send_ingest(client: TestClient, token: str | None, doc=_DOC):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    return client.post(
        "/a2a", headers=headers,
        json={
            "jsonrpc": "2.0", "id": "r1", "method": "message/send",
            "params": {"message": {
                "role": "user", "messageId": "m1", "kind": "message",
                "metadata": {"skill_id": "ingest_governed_doc"},
                "parts": [{"kind": "data", "data": doc}],
            }},
        },
    )


def test_write_capable_token_ingests():
    c = TestClient(_app())
    r = _send_ingest(c, _WRITE_TOKEN)
    assert r.status_code == 200
    task = r.json()["result"]
    assert a2a_types.Task.model_validate(task).status.state == a2a_types.TaskState.completed
    data = [p["data"] for p in task["artifacts"][0]["parts"] if p["kind"] == "data"][0]
    assert data["resource_rid"] == "doc_123"
    assert data["approved_hash"] == "sha256:abc"


def test_read_only_token_is_forbidden_and_not_ingested():
    called = {"n": 0}

    def spy(doc, tenant):
        called["n"] += 1
        return _ingest(doc, tenant)

    c = TestClient(_app(ingest_fn=spy))
    with capture_logs() as logs:
        r = _send_ingest(c, _READ_TOKEN)
    assert r.status_code == 403
    assert called["n"] == 0  # never reached the ingest pipeline
    audit = [x for x in logs if x.get("event") == "a2a.audit"][0]
    assert audit["denied"] is True
    assert audit["skill"] == "ingest_governed_doc"


def test_ingest_without_token_is_unauthorized():
    c = TestClient(_app())
    assert _send_ingest(c, None).status_code == 401


def test_incomplete_doc_is_rejected():
    c = TestClient(_app())
    r = _send_ingest(c, _WRITE_TOKEN, doc={"id": "x"})
    assert r.status_code == 200
    assert r.json()["error"]["code"] == -32602  # invalid params


def test_writer_scope_passed_to_ingest_is_principal_tenant():
    seen = {}

    def spy(doc, tenant):
        seen["tenant"] = tenant
        return _ingest(doc, tenant)

    c = TestClient(_app(ingest_fn=spy))
    _send_ingest(c, _WRITE_TOKEN)
    assert seen["tenant"] == "acme"


def test_successful_ingest_is_audited():
    c = TestClient(_app())
    with capture_logs() as logs:
        _send_ingest(c, _WRITE_TOKEN)
    audit = [x for x in logs if x.get("event") == "a2a.audit"][0]
    assert audit["denied"] is False
    assert audit["skill"] == "ingest_governed_doc"
    assert audit["principal"] == "writer"


def test_idempotent_replay_surfaces_hit():
    def idem(doc, tenant):
        return IngestOutcome("doc_123", "INTERNAL", 0, False, doc["content_hash"], True)

    c = TestClient(_app(ingest_fn=idem))
    r = _send_ingest(c, _WRITE_TOKEN)
    data = [p["data"] for p in r.json()["result"]["artifacts"][0]["parts"] if p["kind"] == "data"][0]
    assert data["idempotent_hit"] is True
