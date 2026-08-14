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


# ── 자가 세 문장짜리 답을 아홉 문장이라고 셌다 (2026-08-14, 실측) ──────────────
#
# U2 측정에서 `three_sentences` 가 양팔 0/30 으로 나왔다. 답변 원문을 열어 보니 모델은
# **요청대로 정확히 세 문장을 썼고**, 자가 그것을 9 로 셌다. 아래 둘이 원인이고, 둘 다
# 어느 팔이 이기는지와 무관하게 틀렸다 — 그것이 결과를 본 뒤에 고쳐도 되는 이유다.

def test_a_numbered_list_marker_is_not_a_sentence_boundary():
    """`1. ` 의 마침표는 문장 끝이 아니라 **목록 번호**다.

    안 걸러내면 두 배로 틀린다: 경계가 하나 생기고, 남은 `1` 이 그 자체로 한 문장이 된다.
    실측(f001)에서 세 문장짜리 답이 9 로 세어진 값의 절반이 여기서 나왔다.
    """
    assert F.sentence_count("1. 첫 문장입니다. 2. 둘째 문장입니다.") == 2
    numbered = ("1. HPA는 필요한 파드 수를 계산해 자동 조정합니다.\n"
                "2. 여러 메트릭이 있으면 가장 큰 값을 채택합니다.\n"
                "3. 준비되지 않은 파드는 보수적으로 처리합니다.")
    assert F.sentence_count(numbered) == 3
    assert F.check("three_sentences", numbered) is True


def test_a_trailing_citation_is_not_a_sentence():
    """`…합니다. [출처: 문서, 절]` 은 한 문장이다. 인용은 마크업이지 문장이 아니다.

    시스템 프롬프트가 **주장마다 인용을 강제**하므로, 이걸 세면 세 문장 요청은 구조적으로
    도달 불가능해진다 — 자가 시스템의 다른 규칙과 싸우는 꼴이다.
    """
    assert F.sentence_count("파드는 거부됩니다. [출처: 파드 시큐리티, 모드]") == 1
    cited = ("`kubectl scale` 로 레플리카 수를 바꿉니다. [출처: 스테이트풀셋 확장하기, 확장]\n\n"
             "축소 시 PVC 는 자동 삭제되지 않습니다. [출처: 스테이트풀 앱 실행, 스케일링]\n\n"
             "비정상 파드가 있으면 축소가 진행되지 않습니다. [출처: 스테이트풀셋 확장하기, 트러블슈팅]")
    assert F.sentence_count(cited) == 3
    assert F.check("three_sentences", cited) is True


def test_the_fix_does_not_let_a_long_answer_through():
    """**그물은 일부러 깨뜨려 확인한다.** 위 둘을 걷어내도 진짜 장문은 여전히 실패해야 한다 —
    안 그러면 자를 고친 게 아니라 끈 것이다. baseline 이 실제로 내던 모양이다."""
    long_answer = "\n\n".join(
        f"{i}. 항목 {i} 에 대한 설명입니다. 부연 설명이 이어집니다. [출처: 문서, {i}절]"
        for i in range(1, 6))
    assert F.sentence_count(long_answer) == 10
    assert F.check("three_sentences", long_answer) is False


def test_a_bare_number_is_not_swallowed_when_it_is_the_content():
    """번호 마커만 지운다 — 문장 안의 소수·버전은 건드리지 않는다.

    `3.5` 를 목록 번호로 오인해 지우면 자가 본문을 먹기 시작하고, 그러면 문장 수가
    조용히 줄어 **긴 답이 통과한다.** 완화는 언제나 이 방향으로 틀린다.
    """
    assert F.sentence_count("버전 3.5 를 씁니다. 그리고 4.0 도 지원합니다.") == 2


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
