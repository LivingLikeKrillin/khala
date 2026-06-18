"""A2A audit trail (Phase 2, SPEC §3.1–§3.3, §6).

Every A2A task — granted AND denied — emits exactly one PII-safe ``a2a.audit`` structlog
record. The raw query text never appears; only ``query_sha256``/``query_len`` do.
"""

from __future__ import annotations

import hashlib
import json

from fastapi import FastAPI
from fastapi.testclient import TestClient
from structlog.testing import capture_logs

from nexus.a2a.audit import AUDIT_EVENT, query_sha256
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
    assert rec["query_sha256"] == hashlib.sha256(secret.encode("utf-8")).hexdigest()
    assert rec["query_len"] == len(secret)


def test_query_sha256_helper_is_stable():
    assert query_sha256("abc") == hashlib.sha256(b"abc").hexdigest()
