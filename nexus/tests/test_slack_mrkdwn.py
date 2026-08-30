"""슬랙이 실제로 그리는 것으로 바꾸는가.

⛔ **이 검사가 없어서 생긴 일 (2026-08-30).** 답변 마크다운이 `mrkdwn` 블록에 그대로 들어갔고,
파일럿 첫 질문에서 사용자가 `|------|------|` 가 화면에 그대로 보인다고 알려 줬다. 슬랙은
표도 헤딩도 모른다. **사람이 보는 표면을 실행하지 않으면 초록은 아무 뜻이 없다.**
"""

from __future__ import annotations

from nexus.slack.formatter import format_answer
from nexus.slack.mrkdwn import to_slack

TABLE = "\n".join([
    "| 항목 | 내용 |",
    "|------|------|",
    "| 트리거 | 30일 경과 |",
])


def test_a_table_never_reaches_the_screen_as_pipes():
    """⛔ 사용자가 실제로 본 것. 파이프와 하이픈이 글자 그대로 나갔다."""
    out = to_slack(TABLE)
    assert "|------|" not in out
    assert "```" in out
    assert "트리거" in out and "30일 경과" in out


def test_the_columns_line_up_when_the_text_is_korean():
    """한글은 고정폭에서 두 칸이다. 글자 수로 폭을 재면 열이 어긋나 표가 더 못 읽게 된다."""
    out = to_slack("\n".join([
        "| 키 | 값 |",
        "|---|---|",
        "| 가나다 | 1 |",
        "| a | 2 |",
    ])).splitlines()
    from nexus.slack.mrkdwn import _display_width
    rows = [ln for ln in out if ln and not ln.startswith("```")]
    # 문자 인덱스가 아니라 **표시 폭**으로 확인한다 — 한글이 두 칸이라 인덱스는 어긋난다.
    starts = [_display_width(ln[:ln.index("1" if "1" in ln else "2")]) for ln in rows[1:]]
    assert len(set(starts)) == 1, f"열이 어긋난다: {rows}"


def test_a_heading_becomes_bold_because_slack_has_no_headings():
    assert to_slack("## 조건 상세") == "*조건 상세*"


def test_bold_uses_one_asterisk_because_that_is_what_slack_reads():
    assert to_slack("**핵심 답변**: 30일") == "*핵심 답변*: 30일"


def test_a_horizontal_rule_is_dropped():
    """구분선 블록이 이미 따로 있다. 본문의 `---` 는 화면에서 잡음이다."""
    assert to_slack("앞\n\n---\n\n뒤") == "앞\n\n\n뒤"


def test_a_code_block_is_left_alone():
    """⛔ 대조군. 코드 블록 안의 파이프·별표는 사람이 보라고 쓴 글자다."""
    src = "```\n| a | b |\n**x**\n```"
    assert to_slack(src) == src


def test_a_plain_answer_is_unchanged():
    """대조군 — 바꿀 것이 없는 답변은 그대로 지나가야 한다."""
    plain = "30일이 지나면 자동 폐쇄됩니다.\n\n[출처: 파티룸 Entity 정책]"
    assert to_slack(plain) == plain


def test_the_formatter_actually_calls_the_converter():
    """⛔ **배선 검사.** 변환기가 있어도 포매터가 안 부르면 화면은 그대로다 —
    이 리포가 반복해서 데인 모양이다."""
    blocks = format_answer({"answer": TABLE, "evidence_snippets": []})
    body = blocks[0]["text"]["text"]
    assert "|------|" not in body
    assert "```" in body
