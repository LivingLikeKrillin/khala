"""Ecosystem E2E — 외부 spec 인바운드(서브프로젝트 A): 메모 예치 + 선택 승격.

실제 Nexus A2A 서버(mount_a2a → 카드 + JSON-RPC + capability 게이트 + audit + 외부 ingest
매핑)를 in-memory 외부 스토어에 와이어. 승격은 specledger promote_external 로 직접. 기존
test_a2a_e2e_specledger_to_nexus.py 와 같은 형태(유일한 스텁은 DB 인덱싱).
"""

from __future__ import annotations

import hashlib

import pytest

pytest.importorskip("nexus")
pytest.importorskip("specledger")
pytest.importorskip("a2a.compat.v0_3.types")

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from structlog.testing import capture_logs  # noqa: E402

from nexus.a2a.config import A2AConfig  # noqa: E402
from nexus.a2a.external_ingest_skill import EXTERNAL_LABEL, ExternalIngestOutcome  # noqa: E402
from nexus.a2a.server import mount_a2a  # noqa: E402
from nexus.auth.principal import hash_token  # noqa: E402
from specledger.artifacts import Artifact  # noqa: E402
from specledger.ledger import Ledger  # noqa: E402
from specledger.promote import promote_external  # noqa: E402

_BASE = "http://nexus.test"
_WRITE = "ext-writer-token"
_READ = "read-only-token"
_PRINCIPALS = [
    {"name": "reader", "token_sha256": hash_token(_READ),
     "tenant": "acme", "clearance": "INTERNAL"},
    {"name": "depositor", "token_sha256": hash_token(_WRITE),
     "tenant": "acme", "clearance": "INTERNAL", "capabilities": ["ingest_external"]},
]


def _csf(body="# Payment\n\n결제 서비스 명세", tool="manifest", sid="p-1"):
    return {
        "id": f"ext-{tool}-{sid}", "kind": "PRD", "title": "Payment PRD",
        "provenance": {
            "source_tool": tool, "source_id": sid,
            "source_url": "https://manifest.app/p-1",
            "source_hash": hashlib.sha256(body.encode("utf-8")).hexdigest(),
        },
        "body": body,
    }


class _ExtStore:
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
        self.docs[key] = {"source_hash": shash}
        return ExternalIngestOutcome(
            resource_rid=f"doc_{doc['id']}", labels=[EXTERNAL_LABEL],
            chunks_indexed=0 if hit else 2, idempotent_hit=hit, source_hash=shash,
        )


def _app(ext_fn) -> FastAPI:
    app = FastAPI()
    mount_a2a(
        app, A2AConfig(enabled=True, base_url=_BASE, principals=_PRINCIPALS),
        answer_fn=lambda q, t, c: None, external_ingest_fn=ext_fn,
    )
    return app


def _send(client, token, csf):
    return client.post(
        "/a2a", headers={"Authorization": f"Bearer {token}"},
        json={"jsonrpc": "2.0", "id": "1", "method": "message/send",
              "params": {"message": {
                  "metadata": {"skill_id": "ingest_external_spec"},
                  "parts": [{"kind": "data", "data": csf}]}}},
    )


def test_deposit_then_idempotent_then_promote(tmp_path):
    store = _ExtStore()
    client = TestClient(_app(store.ingest_fn))

    # 1) 메모 예치 — label external_spec 로 인덱싱
    r = _send(client, _WRITE, _csf())
    task = r.json()["result"]
    assert task["status"]["state"] == "completed"
    assert ("acme", "ext-manifest-p-1") in store.docs

    # 2) 동일 재예치 — idempotent
    _send(client, _WRITE, _csf())
    assert store.hits == 1 and len(store.docs) == 1

    # 3) 선택 승격 — 호출자가 들고 있던 CSF 를 specledger DRAFT 로
    led = Ledger(tmp_path, now=lambda: "2026-06-24T00:00:00Z")
    out = promote_external(led, _csf(), "SPEC")
    art = Artifact.load(led._resolve(out["artifact_id"]))
    assert out["status"] == "DRAFT"
    assert art.meta["source_tool"] == "manifest"
    assert art.meta["promoted_from_source_hash"] == _csf()["provenance"]["source_hash"]


def test_read_only_token_denied_and_audited(tmp_path):
    store = _ExtStore()
    client = TestClient(_app(store.ingest_fn))
    with capture_logs() as logs:
        r = _send(client, _READ, _csf())
    assert r.json()["error"]["code"] == -32003  # forbidden
    assert store.ingests == 0
    audit = [x for x in logs if x.get("event") == "a2a.audit"]
    assert any(a["denied"] and a["skill"] == "ingest_external_spec" for a in audit)
