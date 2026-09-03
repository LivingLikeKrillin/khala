"""저술 검증기 — **점수를 보기 전에** 거는 두 규칙 (`tests/eval/answer-facts/README.md`).

⛔ 이 검사가 지키는 성질: 여기 있는 판정은 전부 **문서에 대한 것**이고 답변에 대한 것이 아니다.
시스템이 답하는지를 보고 라벨을 고치면 현직 시스템의 표현에 채점기를 맞추는 것이고, 그 채점기로
잰 수는 다음 모델·다음 실험군에 불리하게 기운다(규칙 5). 그래서 이 파일 어디에도 답변이 없다.
"""

from __future__ import annotations

from scripts.label_authoring_check import (
    NEEDED,
    authoring_problems,
    balance_after,
    holds_in,
    shape_problems,
)

GOLD = "공지는 CM 이상만 등록할 수 있고 최대 50자까지 가능하다."
CONTROL = "락은 동시성 문제를 다루는 개념이다."


def _q(**kw):
    base = {"id": "x1", "query": "공지는 누가 등록하나", "stratum": "mixed",
            "gold": ["a.md"], "must_contain": [["CM"]], "rationale": "권한이 본문에 있다"}
    base.update(kw)
    return base


# ── 모양 ─────────────────────────────────────────────────────────────────────

def test_a_complete_candidate_has_no_shape_problem():
    assert shape_problems(_q()) == []


def test_every_needed_field_is_actually_checked():
    """칸 하나를 빼면 반드시 걸려야 한다 — 안 걸리는 칸이 있으면 목록이 장식이다."""
    for f in NEEDED:
        assert shape_problems(_q(**{f: None})), f"{f} 가 없는데 안 걸린다"


def test_an_unknown_stratum_is_refused():
    assert shape_problems(_q(stratum="loanwords"))


# ── 저술 규칙 ① 요구가 gold 에서 성립한다 ────────────────────────────────────

def test_a_requirement_absent_from_the_gold_is_refused():
    """없으면 **어떤 답으로도 통과 못 하는** 질의다 — 그건 라벨이 아니라 함정이다."""
    got = authoring_problems(_q(must_contain=[["존재하지않는말"]]), GOLD, CONTROL)
    assert got and "gold 본문에 없다" in got[0]


def test_the_message_names_which_requirement_is_missing():
    """어느 요구가 빠졌는지 안 적으면 저술자가 전부를 다시 읽는다."""
    got = authoring_problems(_q(must_contain=[["CM"], ["없는말"]]), GOLD, CONTROL)
    assert "없는말" in got[0] and "CM" not in got[0].split("—")[1]


# ── 저술 규칙 ② 요구가 대조군에서 불성립한다 ─────────────────────────────────

def test_a_requirement_that_also_holds_in_the_control_is_refused():
    """아무 문서에나 있는 낱말은 그 문서를 **지목하지 못한다**."""
    got = authoring_problems(_q(must_contain=[["동시성"]]), GOLD + " 동시성", CONTROL)
    assert got and "대조군에서도" in got[0]


def test_a_requirement_that_holds_only_in_the_gold_passes():
    assert authoring_problems(_q(must_contain=[["CM"], ["50자"]]), GOLD, CONTROL) == []


def test_holds_in_uses_and_across_items_or_within_one():
    """항목은 AND, 항목 안의 후보는 OR — 채점기와 같은 규칙이어야 한다."""
    assert holds_in([["CM"], ["50자"]], GOLD)
    assert holds_in([["CM", "없는말"]], GOLD)
    assert not holds_in([["CM"], ["없는말"]], GOLD)


def test_no_requirement_at_all_is_not_silently_a_pass():
    """빈 요구를 통과시키면 아무것도 요구하지 않는 라벨이 들어온다."""
    assert not holds_in([], GOLD)
    assert not holds_in(None, GOLD)


# ── 층 균형 ──────────────────────────────────────────────────────────────────

def test_replacing_keeps_the_count_when_the_strata_match():
    """40건은 다섯 층에 8건씩으로 지어졌다 — 빼고 넣는 층이 같아야 그 모양이 산다."""
    existing = [{"id": f"q{i}", "answerable": True, "stratum": "mixed"} for i in range(8)]
    after = balance_after(existing, {"q0", "q1"},
                          [{"stratum": "mixed"}, {"stratum": "mixed"}])
    assert after["mixed"] == 8


def test_replacing_into_a_different_stratum_shows_up_as_imbalance():
    """⛔ 조용히 넘어가면 층별로 아무 말도 못 하게 된 것을 아무도 모른다."""
    existing = [{"id": f"q{i}", "answerable": True, "stratum": "mixed"} for i in range(8)]
    after = balance_after(existing, {"q0", "q1"},
                          [{"stratum": "spacing"}, {"stratum": "spacing"}])
    assert after["mixed"] == 6 and after["spacing"] == 2


def test_unanswerable_labels_are_not_counted():
    """분모는 답변가능 40이지 45가 아니다."""
    existing = [{"id": "q0", "answerable": False, "stratum": "mixed"}]
    assert balance_after(existing, set(), [])["mixed"] == 0


# ── 대조군이 gold 자신인 경우 ────────────────────────────────────────────────

def test_a_control_that_is_the_gold_is_recognised():
    """첫 실행에서 후보 8건 중 4건이 이 자리에서 뜻 없이 실패했다."""
    from scripts.label_authoring_check import control_is_the_gold
    assert control_is_the_gold(_q(gold=["a.md"]), "a.md", "어떤 제목")
    assert control_is_the_gold(_q(gold=["어떤 제목"]), "b.md", "어떤 제목")
    assert not control_is_the_gold(_q(gold=["a.md"]), "b.md", "다른 제목")


def test_rule_two_is_skipped_not_faked_when_the_control_is_the_gold():
    """건너뛰는 것이지 통과시키는 것이 아니다 — 규칙 ①은 그대로 판정한다."""
    assert authoring_problems(_q(must_contain=[["CM"]]), GOLD, None) == []
    got = authoring_problems(_q(must_contain=[["없는말"]]), GOLD, None)
    assert got and "gold 본문에 없다" in got[0]
