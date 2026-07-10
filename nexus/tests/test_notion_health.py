"""Notion 연결 진단 — SPEC-nexus-notion-connection-health §4.1~§4.3, §5, §6.

가짜 transport 로 모든 분기를 실제로 밟는다. 여기서 고정하는 불변식:

  1. `unknown` 은 절대 `unreachable` 로 무너지지 않는다. Notion 장애를 "당신의 페이지가
     사라졌다" 로 보고하면, 그 말을 믿은 사용자는 공유가 풀린 적 없는 페이지를 다시 공유하러 간다.
  2. 토큰이 `invalid` 거나 없으면 root 는 **한 번도 probe 되지 않는다**. 전부 401 로 답할
     테고, 그걸 unreachable 로 적으면 토큰의 죄를 페이지에 씌우는 것이다.
  3. 데이터베이스는 없는 페이지가 아니다. `/pages` 가 200 이 아니면 `/databases` 로 다시 묻는다.
  4. 응답에 예외 문자열이 실리지 않는다.
"""

from __future__ import annotations

import httpx
import pytest

from nexus.sources.notion_health import RootState, TokenState, probe_connection

_TOKEN = "ntn_secret_value_do_not_leak_0000000000"
_ROOT = "fc054c8f-cc62-409c-8154-deafb826cac9"


def _transport(handler):
    return httpx.MockTransport(handler)


def _json(status: int, body: dict | None = None) -> httpx.Response:
    return httpx.Response(status, json=body or {})


# ── §4.2 토큰 상태 ────────────────────────────────────────────────────────────

async def test_no_token_is_not_configured_and_probes_nothing():
    calls: list[str] = []

    def handler(request):
        calls.append(str(request.url))
        return _json(200)

    health = await probe_connection("", [_ROOT], transport=_transport(handler))

    assert health.token.state is TokenState.NOT_CONFIGURED
    assert calls == []                                  # Notion 을 부르지도 않는다
    assert [r.state for r in health.roots] == [RootState.UNKNOWN]


async def test_a_rejected_token_is_invalid_and_roots_are_never_probed():
    calls: list[str] = []

    def handler(request):
        calls.append(request.url.path)
        return _json(401, {"code": "unauthorized", "message": "API token is invalid."})

    health = await probe_connection(_TOKEN, [_ROOT], transport=_transport(handler))

    assert health.token.state is TokenState.INVALID
    assert calls == ["/v1/users/me"]                    # root 는 건드리지 않았다
    assert [r.state for r in health.roots] == [RootState.UNKNOWN]


async def test_a_live_token_reports_the_integration_and_workspace():
    def handler(request):
        if request.url.path == "/v1/users/me":
            return _json(200, {"type": "bot", "name": "실증 테스트",
                               "bot": {"workspace_name": "어느 워크스페이스"}})
        return _json(200, {"properties": {"title": {"type": "title",
                                                    "title": [{"plain_text": "System Architecture"}]}}})

    health = await probe_connection(_TOKEN, [_ROOT], transport=_transport(handler))

    assert health.token.state is TokenState.OK
    assert health.token.integration == "실증 테스트"
    assert health.token.workspace == "어느 워크스페이스"
    assert health.token.prefix == "ntn_"                 # 4자. 그 이상은 자격증명이다


@pytest.mark.parametrize("status", [429, 500, 502, 503])
async def test_any_other_token_status_is_unknown_not_invalid(status):
    health = await probe_connection(_TOKEN, [], transport=_transport(lambda r: _json(status)))
    assert health.token.state is TokenState.UNKNOWN


async def test_a_transport_error_on_the_token_probe_is_unknown_not_invalid():
    def handler(request):
        raise httpx.ConnectError("no route to host")

    health = await probe_connection(_TOKEN, [_ROOT], transport=_transport(handler))
    assert health.token.state is TokenState.UNKNOWN
    assert [r.state for r in health.roots] == [RootState.UNKNOWN]


# ── §4.3 root 상태 ────────────────────────────────────────────────────────────

def _token_ok(then):
    """/v1/users/me 는 통과시키고 나머지는 `then` 에 맡긴다."""
    def handler(request):
        if request.url.path == "/v1/users/me":
            return _json(200, {"name": "bot", "bot": {"workspace_name": "w"}})
        return then(request)
    return handler


async def test_a_reachable_page_reports_its_title():
    def then(request):
        assert request.url.path == f"/v1/pages/{_ROOT}"
        return _json(200, {"properties": {"Name": {"type": "title",
                                                   "title": [{"plain_text": "System Architecture"}]}}})

    health = await probe_connection(_TOKEN, [_ROOT], transport=_transport(_token_ok(then)))
    root = health.roots[0]
    assert root.state is RootState.REACHABLE
    assert root.title == "System Architecture"


async def test_a_database_is_not_a_missing_page():
    """`/pages` 가 200 이 아니면 `/databases` 로 다시 묻는다 — 404 일 때만이 아니라 (I-006)."""
    seen: list[str] = []

    def then(request):
        seen.append(request.url.path)
        if request.url.path.startswith("/v1/pages/"):
            return _json(400, {"code": "validation_error"})   # 404 가 아니다
        return _json(200, {"title": [{"plain_text": "팀 문서 DB"}]})

    health = await probe_connection(_TOKEN, [_ROOT], transport=_transport(_token_ok(then)))
    assert seen == [f"/v1/pages/{_ROOT}", f"/v1/databases/{_ROOT}"]
    assert health.roots[0].state is RootState.REACHABLE
    assert health.roots[0].title == "팀 문서 DB"


@pytest.mark.parametrize("status", [404, 403])
async def test_not_found_and_forbidden_are_the_same_state_and_the_same_sentence(status):
    """Notion 은 오늘 404 를 준다. 403 으로 바뀌어도 사용자에게 할 말은 같다 (I-005)."""
    health = await probe_connection(
        _TOKEN, [_ROOT], transport=_transport(_token_ok(lambda r: _json(status))))
    root = health.roots[0]
    assert root.state is RootState.UNREACHABLE
    assert "integration" in root.remedy and root.title is None


async def test_a_malformed_id_is_invalid_id_not_unreachable():
    health = await probe_connection(
        _TOKEN, ["nope"], transport=_transport(_token_ok(lambda r: _json(400))))
    assert health.roots[0].state is RootState.INVALID_ID


@pytest.mark.parametrize("status", [429, 500, 503])
async def test_notion_being_down_never_says_your_page_is_gone(status):
    health = await probe_connection(
        _TOKEN, [_ROOT], transport=_transport(_token_ok(lambda r: _json(status))))
    assert health.roots[0].state is RootState.UNKNOWN


async def test_a_root_timeout_is_unknown():
    def then(request):
        raise httpx.ReadTimeout("too slow")

    health = await probe_connection(_TOKEN, [_ROOT], transport=_transport(_token_ok(then)))
    assert health.roots[0].state is RootState.UNKNOWN


async def test_roots_are_probed_concurrently_and_each_is_reported():
    def then(request):
        rid = request.url.path.rsplit("/", 1)[-1]
        return _json(200 if rid.startswith("a") else 404,
                     {"properties": {"t": {"type": "title", "title": [{"plain_text": rid}]}}})

    health = await probe_connection(
        _TOKEN, ["aaa", "bbb", "aac"], transport=_transport(_token_ok(then)))
    assert [r.state for r in health.roots] == [
        RootState.REACHABLE, RootState.UNREACHABLE, RootState.REACHABLE]
    assert [r.root_id for r in health.roots] == ["aaa", "bbb", "aac"]   # 순서 보존


# ── §4.5 · §4.6 자격증명이 응답에 새지 않는다 ─────────────────────────────────

async def test_nothing_in_the_result_carries_the_token_or_an_exception_string():
    def handler(request):
        raise httpx.ConnectError(f"failed connecting with Authorization: Bearer {_TOKEN}")

    health = await probe_connection(_TOKEN, [_ROOT], transport=_transport(handler))
    blob = repr(health)

    assert _TOKEN not in blob
    assert "Authorization" not in blob and "Bearer" not in blob
    assert health.token.prefix == "ntn_"
    assert len(health.token.prefix) == 4


def test_redact_removes_the_token_by_value():
    from nexus.sources.notion_health import redact

    assert redact(f"boom {_TOKEN} boom", _TOKEN) == "boom [REDACTED] boom"
    assert redact("boom", _TOKEN) == "boom"
    assert redact("boom", "") == "boom"          # 토큰 없음 → 아무것도 지우지 않는다
    assert redact("", _TOKEN) == ""
