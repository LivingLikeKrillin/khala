"""MCP `nexus_answer` 의 텍스트에 코드 값과 **소유자 판정**이 실리는가.

에이전트 소비자는 MCP 로 답을 받는다. HTTP 응답에 `code_values` 가 실려도 MCP 텍스트가
그것을 빠뜨리면 그 표면의 소비자만 판정을 못 본다 — 한 표면만 빠지는 모양(외부 평가 F2).
줄 만들기는 `mcp` 패키지 없이 도는 순수 함수로 두어 호스트에서도 검사한다.
"""

from __future__ import annotations

from nexus.mcp.lines import code_values_lines


def _row(**kw):
    base = {"statement": "닉네임 길이 상한 (서버 요청 검증)", "value": "20", "source": "a/Req.java",
            "drifted": False, "ruled_value": None, "ruled_source": None, "ruled_by": None,
            "ruled_on": None, "ruling_note": None, "ruling_conflict": False}
    base.update(kw)
    return base


def test_no_code_values_adds_no_lines():
    assert code_values_lines({}) == []
    assert code_values_lines({"code_values": []}) == []


def test_a_plain_code_value_is_listed_without_ruling_words():
    lines = code_values_lines({"code_values": [_row()]})
    assert lines[0] == "\n--- 코드 값 ---"
    assert "닉네임 길이 상한 (서버 요청 검증): 20 (a/Req.java)" in lines[1]
    assert not any("판정" in ln for ln in lines)


def test_a_ruling_is_shown_with_who_and_when_and_a_conflict_marker():
    lines = code_values_lines({"code_values": [_row(
        ruled_value="12", ruled_source="정책 문서", ruled_by="@owner", ruled_on="2026-08-31",
        ruling_note="코드 20 은 12 로 고칠 것", ruling_conflict=True)]})
    text = "\n".join(lines)
    assert "판정: 12" in text and "@owner" in text and "2026-08-31" in text
    assert "정책 문서" in text and "코드 20 은 12 로 고칠 것" in text
    assert "판정과 어긋" in text


def test_a_ruling_without_a_value_says_so_and_never_conflicts():
    lines = code_values_lines({"code_values": [_row(
        value="100", ruled_value=None, ruled_by="@owner", ruled_on="2026-08-31",
        ruling_note="코드 값 기각, 대체 값 미정", ruling_conflict=False)]})
    text = "\n".join(lines)
    assert "판정: 값 미정" in text and "기각" in text
    assert "판정과 어긋" not in text


def test_an_unreadable_code_value_with_a_ruling_is_still_listed():
    lines = code_values_lines({"code_values": [_row(
        statement="파티룸 정원", value="", source="", ruled_value="50", ruled_by="@owner",
        ruled_on="2026-08-31")]})
    text = "\n".join(lines)
    assert "파티룸 정원: (코드에서 읽지 못함)" in text and "판정: 50" in text
