"""A2A JSON-RPC server surface (SPEC §5.3, §5.5) with an injected answer service.

Drives the ``message/send`` flow end-to-end over the JSON-RPC wire (FastAPI TestClient is
the transport) without DB/LLM: the grounded-answer service is injected. Asserts discovery,
token gating, the returned Task shape, and that server-side scope narrowing is applied
before retrieval.
"""

from __future__ import annotations

import a2a.compat.v0_3.types as a2a_types
from fastapi import FastAPI
from fastapi.testclient import TestClient

from nexus.a2a.config import A2AConfig
from nexus.a2a.server import mount_a2a
from nexus.auth.principal import hash_token
from nexus.llm.answer import AnswerResult

_TOKEN = "a2a-good-token"
_PRINCIPAL = {
    "name": "ext-agent", "token_sha256": hash_token(_TOKEN),
    "tenant": "acme", "clearance": "INTERNAL",
}


def _grounded(query: str, tenant: str, clearance: str) -> AnswerResult:
    return AnswerResult(
        answer=f"answer for {query}",
        evidence_snippets=[{
            "chunk_rid": "c1", "doc_title": "D", "section_path": "S",
            "source_uri": "git://d.md", "text": "근거", "score": 0.9,
        }],
        provenance=[{"doc_rid": "d", "source_uri": "git://d.md", "source_version": "v1"}],
        route_used="vector",
    )


def _app(answer_fn=_grounded, principals=None) -> FastAPI:
    app = FastAPI()
    mount_a2a(
        app,
        A2AConfig(enabled=True, base_url="https://nexus.example.com",
                  principals=principals if principals is not None else [_PRINCIPAL]),
        answer_fn=answer_fn,
    )
    return app


def _send(client: TestClient, query: str, token: str | None = _TOKEN):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    return client.post(
        "/a2a",
        headers=headers,
        json={
            "jsonrpc": "2.0", "id": "req-1", "method": "message/send",
            "params": {"message": {
                "role": "user", "messageId": "m1", "kind": "message",
                "parts": [{"kind": "text", "text": query}],
            }},
        },
    )


def test_card_is_served_and_lists_skill():
    c = TestClient(_app())
    card = c.get("/.well-known/agent-card.json").json()
    assert a2a_types.AgentCard.model_validate(card).name == "Nexus"
    assert "retrieve_grounded" in [s["id"] for s in card["skills"]]


def test_send_returns_a_completed_task_with_grounded_artifact():
    c = TestClient(_app())
    r = _send(c, "결제 토픽?")
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == "req-1"
    task = body["result"]
    parsed = a2a_types.Task.model_validate(task)  # schema-valid Task
    assert parsed.status.state == a2a_types.TaskState.completed
    data = [p["data"] for p in task["artifacts"][0]["parts"] if p["kind"] == "data"][0]
    assert len(data["evidence"]) >= 1
    assert data["route"] == "vector"


def test_skill_execution_requires_a_token():
    c = TestClient(_app())
    r = _send(c, "결제 토픽?", token=None)
    assert r.status_code == 401


def test_unknown_token_is_denied():
    c = TestClient(_app())
    r = _send(c, "결제 토픽?", token="bogus")
    assert r.status_code == 401


def test_server_applies_principal_scope_before_retrieval():
    """The answer service must be called with the principal's fixed (tenant, clearance)."""
    seen: dict = {}

    def spy(query: str, tenant: str, clearance: str) -> AnswerResult:
        seen["tenant"], seen["clearance"] = tenant, clearance
        return _grounded(query, tenant, clearance)

    c = TestClient(_app(answer_fn=spy))
    _send(c, "q")
    assert seen == {"tenant": "acme", "clearance": "INTERNAL"}


def test_unknown_method_returns_jsonrpc_error():
    c = TestClient(_app())
    r = c.post(
        "/a2a",
        headers={"Authorization": f"Bearer {_TOKEN}"},
        json={"jsonrpc": "2.0", "id": 9, "method": "tasks/cancel", "params": {}},
    )
    assert r.status_code == 200
    assert r.json()["error"]["code"] == -32601  # method not found
