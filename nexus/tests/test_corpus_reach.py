"""라벨이 **지금 묻는 코퍼스에서** 답해질 수 있는가 (`OPEN.md` A86).

⛔ **왜 생겼나 (실측 2026-09-05).** `synthesis-recency` 4건이 전부 `귀속=upstream` 으로 나왔고
나는 그것을 *"코퍼스에 답이 없다"* 로 읽어 항목까지 올렸다. **틀렸다.** 요구한 사실은 전부
코퍼스에 있었다 — `design_docs` 에. 라벨 파일은 자기 테넌트를 안 적고 러너 기본값은 `default`
다. 테넌트를 `default,design_docs` 로 바꿔 다시 돌리니 **넷 중 셋이 곧바로 통과**했다.

`answer_fact_probe.py` 에는 2026-08-31 에 같은 사고를 적은 주석이 이미 있었다 — *"하니스가
`default` 하나만 물어서 설계 라벨이 떨어졌고, 나는 그것을 제품 회귀로 읽을 뻔했다."*
**주석은 사람이 읽어야 작동한다.** 그래서 검사로 옮긴다.
"""

from __future__ import annotations

from scripts.ko_eval_corpus_reach import (
    aiming_is_wrong,
    escape_like,
    groups_reached,
    unreachable_ids,
)


# ── 순수 판정 ────────────────────────────────────────────────────────────────

def test_underscore_is_escaped_because_identifiers_are_full_of_them():
    """⛔ `ILIKE` 에서 `_` 는 **아무 글자 하나**다.

    라벨의 요구 문자열은 식별자가 흔하다(`crew_partyroom_id_user_id_IDX`). 안 막으면 없는 것이
    있다고 읽히고, 그 방향의 오류는 **조용하다** — 이 검사가 막으려는 사고를 그대로 통과시킨다.
    """
    assert escape_like("a_b") == r"a\_b"
    assert escape_like("50%") == r"50\%"
    assert escape_like(r"a\b") == r"a\\b"


def test_a_group_is_reached_when_any_spelling_is():
    """묶음 안은 표기 후보다 — `must_contain`·`expect_all` 과 같은 규칙."""
    groups = [["hard-delete", "완전 삭제"], ["DjChangeType"]]
    assert groups_reached(groups, {"완전 삭제"}) == [True, False]
    assert groups_reached(groups, {"완전 삭제", "DjChangeType"}) == [True, True]


def test_aiming_is_wrong_only_in_the_degenerate_case():
    """**문턱을 만들지 않는다.** 전부 못 닿을 때만 멈춘다 — 비율은 지어낸 수가 된다."""
    assert aiming_is_wrong([[False], [False, False]]) is True
    assert aiming_is_wrong([[False], [True, False]]) is False   # 하나라도 닿으면 측정이다
    assert aiming_is_wrong([]) is False


def test_labels_with_nothing_to_reach_do_not_make_the_aim_look_wrong():
    """요구 사실이 없는 라벨(대조군)은 닿을 것이 원래 없다 — 분모에 넣으면 안 된다."""
    assert aiming_is_wrong([[], []]) is False
    assert aiming_is_wrong([[], [False]]) is True
    assert aiming_is_wrong([[], [True]]) is False


def test_unreachable_labels_are_named_not_silently_dropped():
    """일부만 못 닿으면 멈추지 않는다 — 진짜 문서 부재(FP1)일 수 있고 그건 사람이 가른다."""
    assert unreachable_ids(["a", "b", "c"], [[True], [False], []]) == ["b"]
