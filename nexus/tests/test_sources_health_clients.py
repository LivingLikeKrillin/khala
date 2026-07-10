"""연결 진단의 에이전트 표면 — SPEC-nexus-notion-connection-health §4.5.

같은 엔드포인트, 세 클라이언트. 그리고 **403 을 초록으로 칠하지 않는다** — capability 가 없어
못 봤다는 것과 연결이 멀쩡하다는 것은 다른 말이다.
"""

from __future__ import annotations

import pytest

from nexus.mcp import server as mcp_server


def test_the_health_tool_is_registered():
    assert "nexus_sources_health" in mcp_server.mcp._tool_manager._tools


@pytest.fixture
def calls(monkeypatch):
    seen: list[tuple] = []
    reply: dict = {"success": True, "data": {}}

    async def fake(method, path, **kwargs):
        seen.append((method, path))
        return reply

    monkeypatch.setattr(mcp_server, "_api_call", fake)
    return seen, (lambda d: reply.clear() or reply.update(d))


async def test_health_reports_the_integration_and_each_root(calls):
    seen, set_reply = calls
    set_reply({"success": True, "data": {
        "token": {"state": "ok", "integration": "실증 테스트",
                  "workspace": "어느 워크스페이스", "prefix": "ntn_"},
        "roots": [
            {"root_id": "aaa", "state": "reachable", "title": "System Architecture", "remedy": ""},
            {"root_id": "bbb", "state": "unreachable", "title": None,
             "remedy": "Notion 에서 연결(Connections)에 integration 을 추가하세요."},
        ],
        "checked_at": "2026-07-10T00:00:00Z"}})

    out = await mcp_server.nexus_sources_health()

    assert seen[0] == ("get", "/sources/notion/health")
    assert "실증 테스트" in out and "어느 워크스페이스" in out
    assert "System Architecture" in out
    assert "bbb" in out and "Connections" in out          # 처방을 그대로 전달한다


async def test_an_invalid_token_is_not_dressed_up_as_working(calls):
    _, set_reply = calls
    set_reply({"success": True, "data": {
        "token": {"state": "invalid", "integration": None, "workspace": None, "prefix": "ntn_"},
        "roots": [], "checked_at": "2026-07-10T00:00:00Z"}})

    out = await mcp_server.nexus_sources_health()
    assert "거부" in out or "invalid" in out
    assert "정상" not in out


async def test_a_403_surfaces_as_a_failure_not_as_a_healthy_connection(calls):
    """capability 가 없어 못 봤다는 것과 연결이 멀쩡하다는 것은 다른 말이다."""
    _, set_reply = calls
    set_reply({"success": False, "error": "capability required: manage_sources"})

    out = await mcp_server.nexus_sources_health()
    assert "manage_sources" in out
    assert "ok" not in out.lower()


async def test_sync_status_reports_pages_that_had_no_body(calls):
    """31개를 연결했는데 12개만 적재됐다. 나머지가 어디 갔는지 화면이 말해야 한다.

    `empty` 는 counts 에 이미 있었다. 어느 표면도 읽지 않았을 뿐이다 — 사용자는
    "왜 12개지?" 에 답을 얻을 수 없었다.
    """
    _, set_reply = calls
    set_reply({"success": True, "data": {
        "run_id": "r1", "status": "succeeded", "reconcile": False, "dry_run": False,
        "counts": {"ingested": 12, "idempotent": 0, "skipped": 0, "empty": 19},
        "plan": {}}})

    out = await mcp_server.nexus_sync_status()
    assert "19" in out
    assert "빈" in out or "본문 없" in out
