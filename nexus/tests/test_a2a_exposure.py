"""A2A external-exposure posture (Phase 2, SPEC §3.4, §5.3).

The A2A surface shares the app's CORS, but an operator can declare extra A2A-specific
allowed origins for external callers. ``*`` is never used. The card stays public; the skill
stays token-gated.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.testclient import TestClient

from nexus.a2a.config import A2AConfig, resolve_a2a_cors_origins
from nexus.a2a.server import mount_a2a
from nexus.auth.principal import hash_token

_AUTH_ORIGINS = ["http://localhost:8000"]
_PRINCIPAL = {"name": "ext", "token_sha256": hash_token("tok"), "tenant": "acme", "clearance": "INTERNAL"}


def test_resolve_origins_inherits_auth_when_a2a_unset():
    cfg = A2AConfig(enabled=True)
    assert resolve_a2a_cors_origins(_AUTH_ORIGINS, cfg) == _AUTH_ORIGINS


def test_resolve_origins_unions_a2a_specific_origins():
    cfg = A2AConfig(enabled=True, allowed_origins=["https://agent.example.com"])
    origins = resolve_a2a_cors_origins(_AUTH_ORIGINS, cfg)
    assert "http://localhost:8000" in origins
    assert "https://agent.example.com" in origins


def test_resolve_origins_dedups_and_never_wildcards():
    cfg = A2AConfig(enabled=True, allowed_origins=["http://localhost:8000", "https://a.example.com"])
    origins = resolve_a2a_cors_origins(_AUTH_ORIGINS, cfg)
    assert origins.count("http://localhost:8000") == 1
    assert "*" not in origins


def test_disabled_a2a_does_not_contribute_origins():
    cfg = A2AConfig(enabled=False, allowed_origins=["https://should-not-apply.example.com"])
    assert resolve_a2a_cors_origins(_AUTH_ORIGINS, cfg) == _AUTH_ORIGINS


def test_from_dict_reads_allowed_origins():
    cfg = A2AConfig.from_dict({"a2a": {"enabled": True, "allowed_origins": ["https://x.example.com"]}})
    assert cfg.allowed_origins == ["https://x.example.com"]


def _cors_app() -> FastAPI:
    cfg = A2AConfig(enabled=True, allowed_origins=["https://agent.example.com"], principals=[_PRINCIPAL])
    app = FastAPI()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=resolve_a2a_cors_origins(_AUTH_ORIGINS, cfg),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    mount_a2a(app, cfg)
    return app


def test_allowed_origin_passes_cors_preflight():
    c = TestClient(_cors_app())
    r = c.options(
        "/a2a",
        headers={"Origin": "https://agent.example.com", "Access-Control-Request-Method": "POST"},
    )
    assert r.status_code == 200
    assert r.headers["access-control-allow-origin"] == "https://agent.example.com"


def test_disallowed_origin_is_rejected_by_cors():
    c = TestClient(_cors_app())
    r = c.options(
        "/a2a",
        headers={"Origin": "https://evil.example.com", "Access-Control-Request-Method": "POST"},
    )
    assert r.status_code == 400


def test_card_stays_publicly_fetchable():
    c = TestClient(_cors_app())
    assert c.get("/.well-known/agent-card.json").status_code == 200
