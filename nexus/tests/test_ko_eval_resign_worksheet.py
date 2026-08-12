"""재서명 워크시트 — 사람에게 보여 줄 것을 계산하는 부분 (SPEC-nexus-answer-quality-ruler §3.3).

이 워크시트의 유일한 임무는 **서명하는 사람이 무엇에 서명하는지 정확히 보게 하는 것**이다. 그래서
여기 테스트는 두 가지를 지킨다:

1. **워크시트의 '성립' 과 채점기의 '성립' 이 같은 함수다.** 워크시트가 관대한 사본을 쓰면
   '본문에 있다' 고 확인하고 서명한 요구를 자가 답변에서 떨어뜨린다. 두 쪽을 같은 입력으로
   비교해 그 갈라짐을 막는다.
2. **본문 대조는 청크 번호가 아니라 텍스트를 본다.** 재청킹은 번호를 전부 밀어 버린다 — 번호로
   비교하면 한 글자도 안 바뀐 문서가 '전부 바뀜' 으로 보이고, 그런 워크시트를 몇 번 받으면
   사람은 읽지 않고 서명하기 시작한다. 통과만이 아니라 **오탐이 안 나는 것**을 함께 건다.
"""

from __future__ import annotations

import unicodedata

from scripts.ko_eval_answer_quality import delivered_text, facts_present, score_answer
from scripts.ko_eval_resign_worksheet import EXCERPT, _diff_chunks, _excerpt, _requirement_state


# ── 요구 검사: 채점기와 같은 규칙인가 ────────────────────────────────────────

def test_items_are_and_alternatives_are_or():
    body = "버전 필드로 충돌을 감지한다"
    assert facts_present([["버전"], ["충돌", "트랜잭션"]], body) == [True, True]
    assert facts_present([["버전"], ["롤백", "재시도"]], body) == [True, False]


def test_no_requirement_is_no_measurement():
    assert facts_present(None, "아무 본문") == []
    assert facts_present([], "아무 본문") == []


def test_whitespace_is_collapsed_but_not_deleted():
    """양쪽에서 건다 — 축약은 되고, 삭제는 안 된다.

    관대한 쪽으로 넓히면(공백 제거) 워크시트만 통과하고 채점기는 떨어뜨리는 조합이 생긴다.
    """
    assert facts_present([["버전 필드"]], "이 문서는  버전   필드 를 쓴다") == [True]
    assert facts_present([["버전 필드"]], "이 문서는 버전필드를 쓴다") == [False]


def test_decomposed_hangul_still_matches():
    body = unicodedata.normalize("NFD", "낙관적 락을 쓴다")
    assert facts_present([["낙관적"]], body) == [True]


def test_worksheet_and_grader_agree_on_the_same_text():
    """워크시트의 ✓/✗ 와 채점기의 `facts` 가 같은 답변 텍스트에서 갈라지지 않는다."""
    answer = "제공된 문서에 수치는 없습니다.\n낙관적 락은 버전 필드로 충돌을 감지합니다."
    must = [["버전"], ["충돌"], ["재시도"]]
    graded = score_answer("q", answer, [{"verified": True, "title": "T"}], {"T"}, must).facts
    worksheet = [ok for _, ok, _ in _requirement_state(must, delivered_text(answer))]
    assert worksheet == graded == [True, True, False]


def test_requirement_state_names_the_spelling_that_matched():
    state = _requirement_state([["트랙", "곡"]], "상한은 100곡이다")
    assert state == [("트랙 | 곡", True, "곡")]
    assert _requirement_state([["트랙"]], "상한은 100곡이다") == [("트랙", False, "")]


# ── 본문 대조: 번호가 아니라 텍스트 ──────────────────────────────────────────

def _chunk(idx: int, text: str, section: str = "1. 개요"):
    return (section, idx, text)


def test_identical_bodies_have_no_diff():
    body = [_chunk(0, "가"), _chunk(1, "나")]
    assert _diff_chunks(body, body) == ([], [])


def test_renumbering_alone_is_not_a_change():
    """재청킹으로 번호만 밀린 문서를 '전부 바뀜' 으로 보고하면 워크시트는 읽히지 않는다."""
    before = [_chunk(0, "가"), _chunk(1, "나")]
    after = [_chunk(7, "가"), _chunk(8, "나")]
    assert _diff_chunks(before, after) == ([], [])


def test_reformatting_whitespace_is_not_a_change():
    before = [_chunk(0, "가 나 다")]
    after = [_chunk(0, "가  나\n다")]
    assert _diff_chunks(before, after) == ([], [])


def test_added_text_is_reported_with_its_chunk():
    before = [_chunk(0, "가")]
    after = [_chunk(0, "가"), _chunk(1, "새로 들어온 문단", section="3. 화면")]
    added, removed = _diff_chunks(before, after)
    assert removed == []
    assert added == [("3. 화면", 1, "새로 들어온 문단")]


def test_removed_text_is_reported():
    before = [_chunk(0, "가"), _chunk(1, "사라질 문단")]
    after = [_chunk(0, "가")]
    added, removed = _diff_chunks(before, after)
    assert added == []
    assert [t for _, _, t in removed] == ["사라질 문단"]


def test_replacement_shows_both_sides():
    added, removed = _diff_chunks([_chunk(0, "옛 문단")], [_chunk(0, "새 문단")])
    assert [t for _, _, t in added] == ["새 문단"]
    assert [t for _, _, t in removed] == ["옛 문단"]


def test_empty_before_means_everything_is_new():
    added, removed = _diff_chunks([], [_chunk(0, "가"), _chunk(1, "나")])
    assert len(added) == 2 and removed == []


# ── 발췌 ─────────────────────────────────────────────────────────────────────

def test_excerpt_truncates_long_text_and_marks_it():
    out = _excerpt("가" * (EXCERPT + 50))
    assert len(out) < EXCERPT + 50
    assert out.endswith("…")


def test_excerpt_keeps_short_text_and_flattens_lines():
    assert _excerpt("한 줄\n두 줄") == "한 줄 두 줄"
