"""형식 판정 규칙이 **실제로 판정하는가** (SPEC-nexus-multi-turn-narration §5.2).

이 파일의 대부분은 반례다. 더 순진한 규칙이 무엇을 통과시키는지가 규칙 선택의 근거이고,
그 근거가 검사로 남아 있지 않으면 다음 사람이 규칙을 "단순하게" 되돌린다.
"""

from __future__ import annotations

import pytest

from nexus.search import format_compliance as F


# ── "세 줄로" ─────────────────────────────────────────────────────────────────

def test_a_long_single_line_does_not_pass_as_three_sentences():
    """**이 검사가 규칙 선택의 이유다.**

    §1.1 이 관측한 실패는 1304자짜리 답변이었다. "줄 수 ≤ 3" 으로 세면 개행 없는 장문 한 줄이
    통과하고, 자가 바로 그 실패를 놓친다.
    """
    one_line = "로그인 정책은 " + "매우 " * 200 + "복잡합니다."
    assert "\n" not in one_line
    assert F.sentence_count(one_line) == 1          # 줄로 세면 1 → 통과했을 것
    # 문장으로 세도 1 이니 통과한다 — 길이는 "세 줄로" 의 요구가 아니다. 그것은 `shorter` 가 잰다.
    assert F.check("three_sentences", one_line) is True


def test_sentences_are_counted_across_endings_and_newlines():
    assert F.sentence_count("하나. 둘. 셋.") == 3
    assert F.sentence_count("하나\n둘\n셋") == 3
    assert F.sentence_count("하나. 둘. 셋. 넷.") == 4
    assert F.check("three_sentences", "하나. 둘. 셋. 넷.") is False


def test_korean_without_periods_still_counts():
    """한국어는 마침표를 자주 생략한다 — 개행을 경계로 안 치면 항상 1 문장이 된다."""
    assert F.sentence_count("첫 줄\n둘째 줄\n셋째 줄\n넷째 줄") == 4


def test_blank_lines_are_not_sentences():
    assert F.sentence_count("하나.\n\n\n둘.") == 2


# ── "표로" ────────────────────────────────────────────────────────────────────

def test_a_stray_pipe_is_not_a_table():
    """본문의 파이프 하나가 표로 세어지면, 표를 안 만든 답변이 통과한다."""
    assert F.has_table("조건 A | 조건 B 를 비교하면 다음과 같습니다.") is False


def test_a_header_without_a_separator_is_not_rendered_as_a_table():
    """구분선이 없으면 렌더러가 표로 안 그린다 — 사용자 눈에 표가 아니면 표가 아니다."""
    assert F.has_table("| 항목 | 값 |\n| 로그인 | 허용 |") is False


def test_a_real_table_passes():
    md = "| 항목 | 값 |\n|---|---|\n| 로그인 | 허용 |"
    assert F.has_table(md) is True
    assert F.check("table", md) is True


@pytest.mark.parametrize("sep", ["|---|---|", "| :-- | --: |", "|:---:|:---:|"])
def test_alignment_syntax_still_counts(sep):
    assert F.has_table(f"| a | b |\n{sep}\n| 1 | 2 |") is True


# ── "짧게" ────────────────────────────────────────────────────────────────────

def test_shorter_is_relative_to_the_previous_answer():
    """절대 문턱은 질문마다 뜻이 달라진다 — 300자가 짧은 질문도, 긴 질문도 있다."""
    assert F.check("shorter", "짧은 답", prior="아주 " * 100 + "긴 답") is True
    assert F.check("shorter", "아주 " * 100, prior="짧은 답") is False


# ── 목록 항목 ─────────────────────────────────────────────────────────────────

def test_both_bullet_and_numbered_items_are_found():
    text = "- 첫째 항목\n2. 둘째 항목\n* 셋째 항목"
    assert F.list_items(text) == ["첫째 항목", "둘째 항목", "셋째 항목"]


def test_a_sentence_with_a_dash_is_not_a_list_item():
    assert F.list_items("로그인 - 정책은 이렇다") == []


# ── 자가 조용히 통과시키지 않는가 ──────────────────────────────────────────────

def test_an_unknown_format_raises_instead_of_passing():
    """모르는 유형을 True 로 돌려주면, 오타 하나가 그 행을 영원히 통과시킨다."""
    with pytest.raises(KeyError):
        F.check("세줄로", "아무 답")


def test_every_declared_check_is_callable_with_both_arguments():
    """규칙마다 인자 수가 다르면 실행기가 유형별 분기를 갖게 되고, 그 분기가 갈라진다."""
    for kind in F.CHECKS:
        assert isinstance(F.check(kind, "답. 답. 답.", "이전 답변"), bool)
