"""MCP 가 대화 이력을 나르는가 — **그리고 규칙을 베껴 오지 않았는가.**

⛔ 이 표면만 이력을 못 받고 있었다. HTTP 와 A2A 는 `_search_channels` 를 거쳐 이미 쓰는데
MCP 도구 18개 중 `history` 인자를 받는 것이 0개였다. 그래서 에이전트가 가장 자연스럽게 잡는
표면에서 **여러 턴에 걸친 질문이 이어지지 않았다** — "그때 그 조치는" 이 무엇을 가리키는지
알 길이 없으니, 시스템은 거절하는 대신 엉뚱한 것을 찾아 답했다. 막히는 것보다 나쁘다.

여기서 보는 것은 셋이다:

  1. **에이전트가 보는 계약** — `input_schema` 에 실제로 인자가 있는가. 함수 시그니처만
     고치고 등록이 안 되면 도구 목록에는 안 보이고, 그 상태로도 이 파일의 행위 검사는 통과한다
  2. **양방향 전달** — 주면 실리고, 안 주면 키 자체가 안 나간다. 뒤엣것이 대조군이다.
     `null` 을 보내면 API 의 `list[Turn]` 기본값 분기를 못 타고 422 가 된다
  3. **사본이 없는가** — 상한과 거절 규칙의 정본은 `nexus.search.history` 하나다. 여기에
     옮겨 적으면 둘이 갈리고, 이 리포는 그 자리에서 이미 데였다(등급 목록이 사본에만 달랐다)
"""

from __future__ import annotations

import asyncio
import pathlib

import pytest

from nexus.mcp import server

_HISTORY = [
    {"role": "user", "content": "결제 승인이 왜 막혔어?"},
    {"role": "assistant", "content": "한도 검사에서 거절됐습니다."},
]


class _Recorder:
    """`_api_call` 대역. 보낸 본문을 그대로 붙잡아 둔다."""

    def __init__(self):
        self.body: dict | None = None

    async def __call__(self, method, path, **kwargs):
        self.body = kwargs.get("json")
        return {"success": True, "data": {"answer": "ok", "results": []}}


@pytest.fixture
def sent(monkeypatch):
    rec = _Recorder()
    monkeypatch.setattr(server, "_api_call", rec)
    return rec


# ── 1. 에이전트가 보는 계약 ────────────────────────────────────────────────

@pytest.mark.parametrize("tool", ["nexus_search", "nexus_answer"])
def test_the_tool_schema_declares_history(mcp_tools, tool):
    """도구 목록에 안 나오면 에이전트는 이 인자의 존재를 모른다."""
    props = mcp_tools[tool].input_schema.get("properties", {})
    assert "history" in props, f"{tool} 의 인자: {sorted(props)}"


@pytest.mark.parametrize("tool", ["nexus_search", "nexus_answer"])
def test_history_is_optional(mcp_tools, tool):
    """필수가 되면 단일턴 호출이 전부 깨진다."""
    assert "history" not in (mcp_tools[tool].input_schema.get("required") or [])


# ── 2. 양방향 전달 ─────────────────────────────────────────────────────────

@pytest.mark.parametrize("tool", ["nexus_search", "nexus_answer"])
def test_history_reaches_the_request_body(sent, tool):
    asyncio.run(getattr(server, tool)(query="그때 그 조치는 왜 실패했어?", history=_HISTORY))
    assert sent.body["history"] == _HISTORY


@pytest.mark.parametrize("tool", ["nexus_search", "nexus_answer"])
@pytest.mark.parametrize("empty", [None, []])
def test_no_history_sends_no_key(sent, tool, empty):
    """대조군. 키가 나가면 안 된다 — `null` 은 422 이고, 빈 배열은 굳이 보낼 이유가 없다.

    이 검사가 없으면 위의 검사는 '늘 실어 보내는' 구현에도 초록이고, 단일턴 호출이 전부
    깨진 뒤에야 드러난다."""
    asyncio.run(getattr(server, tool)(query="결제 한도는?", history=empty))
    assert "history" not in sent.body


def test_the_query_itself_is_not_appended(sent):
    """이번 질문은 이력에 들어가지 않는다 — 들어가면 재작성기가 자기 자신을 맥락으로 읽는다."""
    asyncio.run(server.nexus_answer(query="그건 언제부터야?", history=_HISTORY))
    assert sent.body["query"] == "그건 언제부터야?"
    assert all(t["content"] != "그건 언제부터야?" for t in sent.body["history"])


# ── 3. 사본 금지 ───────────────────────────────────────────────────────────

def test_the_limits_are_not_copied_into_this_surface():
    """⛔ 상한을 여기 적으면 정본이 둘이 된다. 표면은 나르기만 하고 판정은 API 가 한다."""
    src = pathlib.Path(server.__file__).read_text(encoding="utf-8")
    for copied in ("MAX_TURNS", "MAX_BYTES", "HistoryTooLarge", "MalformedHistory"):
        assert copied not in src, f"{copied} 가 MCP 표면에 복사됐다 — 정본은 search/history.py"


def test_the_canonical_rule_still_lives_in_one_place():
    """정본이 실제로 거기 있는가. 옮겨가면 위 검사가 빈 주장이 된다."""
    from nexus.search import history

    assert history.MAX_TURNS and history.MAX_BYTES
    assert issubclass(history.HistoryTooLarge, ValueError)
