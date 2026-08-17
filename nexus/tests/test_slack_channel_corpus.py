"""채널마다 다른 코퍼스에 묻는다 — 그리고 **토큰이 곧 코퍼스다** (2026-08-18).

봇은 오랫동안 요청 본문에 `"tenant": "default"` 를 넣고 있었는데, 서버는 그 값을 무시한다
(`auth/scope.py`: 테넌트는 principal 의 것이고 요청은 넓힐 수 없다 — 테넌트 격리이자 존재
유출 방지). 그래서 그 줄은 아무 일도 하지 않으면서 **봇이 코퍼스를 고른다는 착각**만 만들었다.
실제로 고르는 것은 토큰이고, 채널을 코퍼스에 붙이는 일은 채널을 토큰에 붙이는 일이다.

여기서 거는 것 셋:
- 매핑된 채널은 그 코퍼스의 토큰으로 간다
- 매핑 없는 채널·깨진 매핑은 **기본 토큰**으로 간다 (침묵하거나 401 을 내지 않는다)
- 진단(`/visibility`)은 **답변과 같은 토큰**으로 나간다 — 아니면 다른 코퍼스의 상태를 보고한다
"""

from __future__ import annotations

import importlib

import pytest


@pytest.fixture
def bot(monkeypatch):
    for k in list(__import__("os").environ):
        if k.startswith("NEXUS_SLACK_CORPUS_"):
            monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("NEXUS_SLACK_TOKEN", "base-token")
    monkeypatch.setenv("NEXUS_SLACK_CORPUS_DESIGN", "design-token|design_docs|INTERNAL")
    monkeypatch.setenv("NEXUS_SLACK_CHANNELS", "C-DESIGN:design, C-OTHER:missing")
    import nexus.slack.bot as b
    return importlib.reload(b)


def test_a_mapped_channel_uses_its_own_corpus_token(bot):
    assert bot.token_for("C-DESIGN") == "design-token"


def test_an_unmapped_channel_stays_on_the_default_corpus(bot):
    assert bot.token_for("C-UNKNOWN") == "base-token"
    assert bot.token_for(None) == "base-token"


def test_a_mapping_to_a_missing_corpus_falls_back_rather_than_401(bot):
    """별칭은 있는데 토큰이 없는 경우. 없는 토큰으로 보내면 사용자에겐 그냥 고장으로 보인다."""
    assert bot.token_for("C-OTHER") == "base-token"


def test_the_request_body_no_longer_carries_a_tenant(bot, monkeypatch):
    """서버가 무시하는 값을 보내면, 읽는 사람이 봇에 코퍼스 선택권이 있다고 믿는다."""
    import httpx

    seen = {}

    def _handler(request: httpx.Request) -> httpx.Response:
        import json
        seen["body"] = json.loads(request.content.decode("utf-8"))
        seen["auth"] = request.headers.get("Authorization")
        return httpx.Response(200, json={"success": True, "data": {
            "answer": "ok", "evidence_snippets": [{"doc_title": "t"}]}})

    monkeypatch.setattr(bot, "_transport", lambda: httpx.MockTransport(_handler))
    import asyncio
    asyncio.run(bot._call_nexus_api("질문", token="design-token"))

    assert "tenant" not in seen["body"]
    assert seen["auth"] == "Bearer design-token"


def test_the_diagnostic_goes_out_on_the_same_token_as_the_answer(bot, monkeypatch):
    """계측기가 다른 코퍼스를 겨누면, '문서가 안 보인다' 는 보고가 엉뚱한 코퍼스의 사실이 된다."""
    import httpx

    seen = {}

    def _handler(request: httpx.Request) -> httpx.Response:
        seen["auth"] = request.headers.get("Authorization")
        return httpx.Response(200, json={"data": {"no_visible_documents": False}})

    monkeypatch.setattr(bot, "_transport", lambda: httpx.MockTransport(_handler))
    bot._visibility("design-token")

    assert seen["auth"] == "Bearer design-token"
