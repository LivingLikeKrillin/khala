"""응답에서 본문 텍스트를 고르는 규칙 — 첫 블록이 텍스트라는 가정을 지운다.

`generate_full` 은 오래 `content[0].text` 였다. 오늘의 요청은 tool 도 thinking 도 선언하지
않으므로 첫 블록이 늘 텍스트였고, 그래서 아무 일도 없었다. 그 가정은 **도구를 선언하는 순간**
깨진다 — 첫 블록이 `server_tool_use` 이고 거기엔 `.text` 가 없다. 열기 전에 박아 둔다.
"""

from __future__ import annotations

from types import SimpleNamespace

from nexus.providers.llm import answer_text


def _text(t):
    return SimpleNamespace(type="text", text=t)


def test_plain_text_response_is_unchanged():
    """오늘의 경로 — 텍스트 한 덩이. 바뀌면 안 된다."""
    assert answer_text([_text("답변입니다")]) == "답변입니다"


def test_a_tool_use_block_before_the_text_does_not_break_it():
    """도구를 선언하면 첫 블록이 `server_tool_use` 다. 옛 코드는 여기서 죽었다."""
    blocks = [
        SimpleNamespace(type="server_tool_use", name="web_search", input={"query": "x"}),
        SimpleNamespace(type="web_search_tool_result", content=[]),
        _text("검색 결과에 따르면…"),
    ]
    assert answer_text(blocks) == "검색 결과에 따르면…"


def test_multiple_text_blocks_are_joined_in_order():
    """도구 호출을 사이에 두고 본문이 쪼개진다 — 뒷조각을 버리면 답이 잘린다."""
    blocks = [
        _text("먼저 "),
        SimpleNamespace(type="server_tool_use", name="web_search", input={}),
        _text("그리고 결론."),
    ]
    assert answer_text(blocks) == "먼저 그리고 결론."


def test_no_text_block_yields_empty_string_not_an_exception():
    """본문이 없으면 빈 문자열이다 — 그것이 사실이고, 답변 경로는 빈 답을 이미 다룬다."""
    assert answer_text([SimpleNamespace(type="server_tool_use", name="web_search")]) == ""
    assert answer_text([]) == ""
    assert answer_text(None) == ""


def test_a_block_without_a_type_counts_as_text():
    """실제 SDK 는 `type` 을 늘 채우지만 테스트 더블은 자주 생략한다.

    없는 것을 "텍스트가 아니다" 로 읽었더니 `test_llm_usage` 가 빨간불이 됐다 — 진짜 응답은
    멀쩡한데. 더블이 자를 흔드는 그 형태를 여기서 못 박는다.
    """
    assert answer_text([SimpleNamespace(text="근거 답변")]) == "근거 답변"
