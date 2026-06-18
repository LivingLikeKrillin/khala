"""Per-principal rate limiting on the A2A surface (SPEC §21).

A sliding-window limiter, keyed per principal, gates skill execution after auth — a flood from
one token can't exhaust the surface (default-deny posture extended to volume). Disabled by
default (``rate_limit_per_min=0``). An over-limit call is a JSON-RPC error + 429 + an audited
``rate_limited`` denial.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient
from structlog.testing import capture_logs

from nexus.a2a.audit import AUDIT_EVENT
from nexus.a2a.config import A2AConfig
from nexus.a2a.ratelimit import RateLimiter
from nexus.a2a.server import mount_a2a
from nexus.auth.principal import hash_token
from nexus.llm.answer import AnswerResult

_TOKEN = "rl-token"
_PRINCIPAL = {"name": "ext-agent", "token_sha256": hash_token(_TOKEN),
              "tenant": "acme", "clearance": "INTERNAL"}


# ── RateLimiter unit (injected clock for determinism) ──


def test_limiter_allows_up_to_max_then_blocks():
    t = [0.0]
    rl = RateLimiter(max_per_window=2, window_s=60.0, clock=lambda: t[0])
    assert rl.allow("p") is True
    assert rl.allow("p") is True
    assert rl.allow("p") is False  # third in the same window is blocked


def test_limiter_window_slides():
    t = [0.0]
    rl = RateLimiter(2, 60.0, clock=lambda: t[0])
    rl.allow("p")
    rl.allow("p")
    assert rl.allow("p") is False
    t[0] = 60.1  # window elapsed
    assert rl.allow("p") is True


def test_limiter_is_per_key():
    t = [0.0]
    rl = RateLimiter(1, 60.0, clock=lambda: t[0])
    assert rl.allow("a") is True
    assert rl.allow("b") is True   # different principal, own budget
    assert rl.allow("a") is False


def test_limiter_zero_is_disabled():
    rl = RateLimiter(0, 60.0)
    assert all(rl.allow("p") for _ in range(100))


# ── server integration ──


def _grounded(query: str, tenant: str, clearance: str) -> AnswerResult:
    return AnswerResult(
        answer="ok",
        evidence_snippets=[{"chunk_rid": "c1", "doc_title": "D", "section_path": "S",
                            "source_uri": "git://d.md", "text": "근거", "score": 0.9}],
        provenance=[{"doc_rid": "d", "source_uri": "git://d.md", "source_version": "v1"}],
        route_used="vector",
    )


def _send(client: TestClient, token: str | None = _TOKEN):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    return client.post(
        "/a2a", headers=headers,
        json={"jsonrpc": "2.0", "id": "r1", "method": "message/send",
              "params": {"message": {"role": "user", "messageId": "m1", "kind": "message",
                                     "parts": [{"kind": "text", "text": "q"}]}}},
    )


def _app(rate_limit_per_min: int) -> FastAPI:
    app = FastAPI()
    mount_a2a(app, A2AConfig(enabled=True, principals=[_PRINCIPAL],
                             rate_limit_per_min=rate_limit_per_min), answer_fn=_grounded)
    return app


def test_over_limit_returns_429_and_audits_denial():
    c = TestClient(_app(rate_limit_per_min=2))
    assert _send(c).status_code == 200
    assert _send(c).status_code == 200
    with capture_logs() as logs:
        r = _send(c)
    assert r.status_code == 429
    rec = [x for x in logs if x.get("event") == AUDIT_EVENT][0]
    assert rec["denied"] is True
    assert rec["reason"] == "rate_limited"
    assert rec["principal"] == "ext-agent"


def test_disabled_by_default_allows_many():
    c = TestClient(_app(rate_limit_per_min=0))
    for _ in range(5):
        assert _send(c).status_code == 200
