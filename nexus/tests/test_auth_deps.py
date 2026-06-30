"""get_principal dependency — runtime behaviour on a DB-free stub app."""

from __future__ import annotations

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from nexus.auth import AuthConfig, Principal, effective_scope, hash_token
from nexus.auth.deps import make_get_principal


def _client(cfg: AuthConfig) -> TestClient:
    app = FastAPI()
    get_principal = make_get_principal(lambda: cfg)

    @app.post("/probe")
    def probe(
        body: dict | None = None,
        principal: Principal = Depends(get_principal),
    ):
        body = body or {}
        tenant, clearance = effective_scope(
            principal, body.get("tenant"), body.get("classification_max")
        )
        return {"name": principal.name, "tenant": tenant, "clearance": clearance}

    return TestClient(app)


_ANALYST = {"name": "analyst", "token_sha256": hash_token("good-token"),
            "tenant": "acme", "clearance": "INTERNAL"}


def test_enforced_no_token_is_401():
    c = _client(AuthConfig(mode="enforced", principals=[_ANALYST]))
    r = c.post("/probe", json={})
    assert r.status_code == 401
    assert "authentication required" in r.json()["detail"]


def test_enforced_bad_token_is_401():
    c = _client(AuthConfig(mode="enforced", principals=[_ANALYST]))
    r = c.post("/probe", json={}, headers={"Authorization": "Bearer nope"})
    assert r.status_code == 401


def test_enforced_valid_token_resolves_scope():
    c = _client(AuthConfig(mode="enforced", principals=[_ANALYST]))
    r = c.post("/probe", json={}, headers={"Authorization": "Bearer good-token"})
    assert r.status_code == 200
    assert r.json() == {"name": "analyst", "tenant": "acme", "clearance": "INTERNAL"}


def test_confused_deputy_request_cannot_widen():
    c = _client(AuthConfig(mode="enforced", principals=[_ANALYST]))
    # INTERNAL token asks for RESTRICTED + a foreign tenant -> clamped
    r = c.post(
        "/probe",
        json={"tenant": "other-corp", "classification_max": "RESTRICTED"},
        headers={"Authorization": "Bearer good-token"},
    )
    assert r.json() == {"name": "analyst", "tenant": "acme", "clearance": "INTERNAL"}


def test_typo_clearance_is_200_public_not_500():
    c = _client(AuthConfig(mode="enforced", principals=[_ANALYST]))
    r = c.post(
        "/probe",
        json={"classification_max": "INTERNL"},  # typo
        headers={"Authorization": "Bearer good-token"},
    )
    assert r.status_code == 200
    assert r.json()["clearance"] == "PUBLIC"


def test_permissive_no_token_is_anonymous_public():
    c = _client(AuthConfig(mode="permissive", principals=[_ANALYST]))
    r = c.post("/probe", json={"classification_max": "RESTRICTED"})
    assert r.status_code == 200
    assert r.json() == {"name": "anonymous", "tenant": "default", "clearance": "PUBLIC"}


def test_permissive_still_honours_a_valid_token():
    c = _client(AuthConfig(mode="permissive", principals=[_ANALYST]))
    r = c.post("/probe", json={}, headers={"Authorization": "Bearer good-token"})
    assert r.json()["name"] == "analyst"
