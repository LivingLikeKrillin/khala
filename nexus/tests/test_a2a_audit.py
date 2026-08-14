"""A2A audit trail (Phase 2, SPEC §3.1–§3.3, §6).

Every A2A task — granted AND denied — emits exactly one PII-safe ``a2a.audit`` structlog
record. The raw query text never appears — and since 2026-08-14 neither does any fingerprint
of it, only ``query_len`` (SPEC-nexus-audit-query-hash).
"""

from __future__ import annotations

import hashlib
import json

from fastapi import FastAPI
from fastapi.testclient import TestClient
from structlog.testing import capture_logs

from nexus.a2a.audit import AUDIT_EVENT, record_audit
from nexus.a2a.config import A2AConfig
from nexus.a2a.server import mount_a2a
from nexus.auth.principal import hash_token
from nexus.llm.answer import AnswerResult

_TOKEN = "a2a-good-token"
_PRINCIPAL = {"name": "ext-agent", "token_sha256": hash_token(_TOKEN),
              "tenant": "acme", "clearance": "INTERNAL"}


def _grounded(query: str, tenant: str, clearance: str) -> AnswerResult:
    return AnswerResult(
        answer=f"answer for {query}",
        evidence_snippets=[{"chunk_rid": "c1", "doc_title": "D", "section_path": "S",
                            "source_uri": "git://d.md", "text": "근거", "score": 0.9}],
        provenance=[{"doc_rid": "d", "source_uri": "git://d.md", "source_version": "v1"}],
        route_used="vector",
    )


def _app(answer_fn=_grounded) -> FastAPI:
    app = FastAPI()
    mount_a2a(app, A2AConfig(enabled=True, principals=[_PRINCIPAL]), answer_fn=answer_fn)
    return app


def _send(client: TestClient, query: str, token: str | None = _TOKEN, method: str = "message/send"):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    return client.post(
        "/a2a", headers=headers,
        json={
            "jsonrpc": "2.0", "id": "r1", "method": method,
            "params": {"message": {"role": "user", "messageId": "m1", "kind": "message",
                                   "parts": [{"kind": "text", "text": query}]}},
        },
    )


def _audits(logs: list[dict]) -> list[dict]:
    return [r for r in logs if r.get("event") == AUDIT_EVENT]


def test_granted_task_emits_one_audit_record():
    c = TestClient(_app())
    with capture_logs() as logs:
        _send(c, "결제 토픽?")
    records = _audits(logs)
    assert len(records) == 1
    rec = records[0]
    assert rec["denied"] is False
    assert rec["principal"] == "ext-agent"
    assert rec["tenant"] == "acme"
    assert rec["clearance"] == "INTERNAL"
    assert rec["route"] == "vector"
    assert rec["evidence_count"] == 1
    assert rec["task_state"] == "completed"
    assert isinstance(rec["latency_ms"], int)


def test_unauthorized_emits_denial_audit():
    c = TestClient(_app())
    with capture_logs() as logs:
        r = _send(c, "기밀?", token=None)
    assert r.status_code == 401
    records = _audits(logs)
    assert len(records) == 1
    assert records[0]["denied"] is True
    assert records[0]["reason"] == "unauthorized"
    # no privileged content on a denial
    assert records[0]["principal"] is None
    assert records[0]["route"] is None


def test_method_not_found_emits_denial_audit():
    c = TestClient(_app())
    with capture_logs() as logs:
        _send(c, "q", method="tasks/cancel")
    records = _audits(logs)
    assert len(records) == 1
    assert records[0]["denied"] is True
    assert records[0]["reason"] == "method_not_found"


def test_empty_query_emits_denial_audit():
    c = TestClient(_app())
    with capture_logs() as logs:
        _send(c, "   ")  # whitespace-only → empty
    records = _audits(logs)
    assert len(records) == 1
    assert records[0]["denied"] is True
    assert records[0]["reason"] == "empty_query"


def test_audit_never_contains_raw_query_text():
    secret = "내 비밀번호는 hunter2 이고 주민번호는 901201-1234567"
    c = TestClient(_app())
    with capture_logs() as logs:
        _send(c, secret)
    rec = _audits(logs)[0]
    blob = json.dumps(rec, ensure_ascii=False)
    assert secret not in blob
    assert "hunter2" not in blob
    # 2026-08-14 뒤집힘 (SPEC-nexus-audit-query-hash): 지문도 남지 않는다. 그 값은
    # `search_query_text` 의 평문에서 재계산돼 `principal` 로 이어지는 경로였다.
    assert "query_sha256" not in rec
    assert hashlib.sha256(secret.encode("utf-8")).hexdigest() not in blob
    assert rec["query_len"] == len(secret)


def test_the_hashing_helper_no_longer_exists():
    """남겨 두면 다음 사람이 다시 쓴다 (SPEC §3.3.2)."""
    from nexus.a2a import audit as A
    assert not hasattr(A, "query_sha256")


async def test_record_audit_without_pool_is_structlog_only():
    """The durable sink is best-effort: with no DB pool it emits structlog and never connects."""
    from nexus import db

    assert db.has_pool() is False  # unit env: no DB pool exists
    secret = "비밀 질의 hunter2"
    with capture_logs() as logs:
        await record_audit(skill="retrieve_grounded", query=secret, principal="p",
                            tenant="acme", clearance="INTERNAL", route="vector",
                            evidence_count=1, task_state="completed")
    rec = _audits(logs)[0]
    # structlog record is emitted, PII-safe (raw query never present)
    assert rec["skill"] == "retrieve_grounded"
    assert secret not in json.dumps(rec, ensure_ascii=False)
    assert "query_sha256" not in rec   # 2026-08-14 뒤집힘 (SPEC-nexus-audit-query-hash)
    assert rec["query_len"] == len(secret)
