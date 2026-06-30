"""Off by default (SPEC §3.6, invariant §6.4).

With the flag off, the A2A surface contributes no routes (card + JSON-RPC both 404) and
existing endpoints are untouched.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from nexus.a2a.config import A2AConfig
from nexus.a2a.server import mount_a2a


def _app(enabled: bool) -> FastAPI:
    app = FastAPI()

    @app.get("/existing")
    def existing():
        return {"ok": True}

    mount_a2a(app, A2AConfig(enabled=enabled, principals=[]))
    return app


def test_disabled_card_route_is_404():
    c = TestClient(_app(enabled=False))
    assert c.get("/.well-known/agent-card.json").status_code == 404


def test_disabled_jsonrpc_route_is_404():
    c = TestClient(_app(enabled=False))
    r = c.post("/a2a", json={"jsonrpc": "2.0", "id": 1, "method": "message/send", "params": {}})
    assert r.status_code == 404


def test_disabled_leaves_existing_endpoints_untouched():
    c = TestClient(_app(enabled=False))
    assert c.get("/existing").json() == {"ok": True}


def test_enabled_mounts_the_card_route():
    c = TestClient(_app(enabled=True))
    assert c.get("/.well-known/agent-card.json").status_code == 200


def test_real_app_has_no_a2a_routes_by_default():
    """With NEXUS_A2A_ENABLED unset (the default), the production app mounts no A2A surface."""
    from nexus.api import app

    paths = {getattr(r, "path", None) for r in app.routes}
    assert "/a2a" not in paths
    assert "/.well-known/agent-card.json" not in paths
