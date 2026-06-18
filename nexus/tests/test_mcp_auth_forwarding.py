"""MCP forwards its service token as Authorization: Bearer (it resolves nothing itself)."""

from __future__ import annotations

from nexus.mcp import server


def test_auth_header_present_when_token_set(monkeypatch):
    monkeypatch.setenv("NEXUS_MCP_TOKEN", "svc-token-xyz")
    assert server._auth_headers() == {"Authorization": "Bearer svc-token-xyz"}


def test_no_auth_header_when_token_unset(monkeypatch):
    monkeypatch.delenv("NEXUS_MCP_TOKEN", raising=False)
    assert server._auth_headers() == {}
