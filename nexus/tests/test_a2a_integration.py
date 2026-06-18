"""End-to-end interop with an off-the-shelf A2A SDK client (SPEC §3 exit criteria 1–2).

Drives the **real** ``a2a-sdk`` client (card resolver + ``ClientFactory`` + ``send_message``)
against the Nexus A2A surface in-process via an httpx ASGI transport — no DB/LLM (the
grounded-answer service is stubbed). Proves a third-party A2A agent can discover Nexus,
delegate a query, and receive the full grounded answer (answer + evidence + provenance +
confidence + route) over A2A.
"""

from __future__ import annotations

import httpx
from a2a.client import A2ACardResolver, ClientConfig, ClientFactory
from a2a.types import a2a_pb2 as pb
from fastapi import FastAPI
from google.protobuf.json_format import MessageToDict
from httpx import ASGITransport

from nexus.a2a.config import A2AConfig
from nexus.a2a.server import mount_a2a
from nexus.auth.principal import hash_token
from nexus.llm.answer import AnswerResult

_TOKEN = "a2a-good-token"
_BASE = "http://nexus.test"
_PRINCIPAL = {"name": "ext-agent", "token_sha256": hash_token(_TOKEN),
              "tenant": "acme", "clearance": "INTERNAL"}


def _stub(query: str, tenant: str, clearance: str) -> AnswerResult:
    return AnswerResult(
        answer=f"근거 기반 답변: {query}",
        evidence_snippets=[
            {"chunk_rid": "c1", "doc_title": "Payment", "section_path": "Topics",
             "source_uri": "git://docs/payment.md", "text": "payment.events 발행", "score": 0.9},
            {"chunk_rid": "c2", "doc_title": "Catalog", "section_path": "Events",
             "source_uri": "git://docs/events.md", "text": "결제 완료 이벤트", "score": 0.6},
        ],
        provenance=[{"doc_rid": "d1", "source_uri": "git://docs/payment.md", "source_version": "v2"}],
        route_used="graph",
    )


def _app() -> FastAPI:
    app = FastAPI()
    mount_a2a(app, A2AConfig(enabled=True, base_url=_BASE, principals=[_PRINCIPAL]), answer_fn=_stub)
    return app


def _httpx(app: FastAPI, token: str | None = _TOKEN) -> httpx.AsyncClient:
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    return httpx.AsyncClient(transport=ASGITransport(app=app), base_url=_BASE, headers=headers)


async def test_offtheshelf_client_discovers_card_and_lists_skill():
    """Exit criterion 1: a reference SDK client fetches the card and lists the skill."""
    async with _httpx(_app()) as hc:
        card = await A2ACardResolver(hc, _BASE).get_agent_card()

    assert card.name == "Nexus"
    assert "retrieve_grounded" in [s.id for s in card.skills]
    assert card.capabilities.streaming is False


async def test_offtheshelf_client_sends_task_and_receives_grounded_answer():
    """Exit criterion 2: the client delegates a query and gets answer + evidence packet."""
    async with _httpx(_app()) as hc:
        client = await ClientFactory(
            ClientConfig(httpx_client=hc, streaming=False)
        ).create_from_url(_BASE)

        msg = pb.Message(message_id="m1", role=pb.ROLE_USER)
        msg.parts.append(pb.Part(text="결제 서비스가 발행하는 토픽이 뭐야?"))
        events = [ev async for ev in client.send_message(pb.SendMessageRequest(message=msg))]

    assert len(events) == 1
    assert events[0].HasField("task")
    task = MessageToDict(events[0].task)

    assert task["status"]["state"] == "TASK_STATE_COMPLETED"
    parts = task["artifacts"][0]["parts"]
    # (a) narrated answer
    text = [p["text"] for p in parts if "text" in p and p["text"]][0]
    assert "근거 기반 답변" in text
    # (b) structured evidence packet — every grounding field present over the wire
    data = [p["data"] for p in parts if "data" in p][0]
    assert len(data["evidence"]) == 2
    assert data["evidence"][0]["source_uri"] == "git://docs/payment.md"
    assert len(data["provenance"]) == 1
    assert data["confidence"] in ("LOW", "MEDIUM", "HIGH")
    assert data["route"] == "graph"
    assert data["policy"] == {"tenant": "acme", "clearance_applied": "INTERNAL"}


async def test_offtheshelf_client_without_token_is_denied():
    """Exit criterion (policy parity): skill execution requires a token over the SDK path."""
    async with _httpx(_app(), token=None) as hc:
        client = await ClientFactory(
            ClientConfig(httpx_client=hc, streaming=False)
        ).create_from_url(_BASE)

        msg = pb.Message(message_id="m1", role=pb.ROLE_USER)
        msg.parts.append(pb.Part(text="기밀?"))
        try:
            [ev async for ev in client.send_message(pb.SendMessageRequest(message=msg))]
        except Exception as exc:  # noqa: BLE001 — SDK raises a client error on the 401
            assert "401" in str(exc) or "unauthor" in str(exc).lower()
        else:
            raise AssertionError("expected the tokenless send to be denied")
