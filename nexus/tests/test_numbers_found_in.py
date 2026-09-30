"""숫자마다 **어디서 찾았는지**(`found_in`) — 그리고 숫자 뒤 쉼표는 표기에 안 붙는다.

⛔ **왜 생겼나 (2026-09-27, 설명 층 자문).** `grounded` 는 참/거짓 하나라 「근거에 있었다」와
「요청자가 준 자료에서 옮겨 적었다」를 못 가른다. 진단 경로에서 둘은 뜻이 다르다 — 이유에 든 정책
값은 근거에 있어야 하고, 대상 번호는 자료에 있으면 된다. 한 값으로 고르려면 순위를 정해야 하고,
어느 순위든 무언가를 감춘다(같은 30 이 정책 문서와 스냅숏에 다 있을 수 있다). 그래서 **목록**이다
(편지 15, 소유자 승인 2026-09-30).

⛔ **그리고 표기 결함 (편지 16, 실측).** 천 단위 쉼표를 받으려던 패턴 `[\\d,]*` 이 문장부호 쉼표까지
먹었다 — `-15,` 가 `"15,"` 로, `₩1,000,` 이 `"₩1,000,"` 으로 나갔다. 대조는 쉼표를 지운 정규형이라
그 판정은 맞았고 표시만 틀렸다. 그런데 같은 패턴이 `30,40` 을 **한 수 3040** 으로 읽었다 — 그건
판정까지 틀린다.
"""

from __future__ import annotations

from nexus.llm.numbers import number_items, validate_numbers

_EVIDENCE = "정원은 30 명이고 대기 한도는 2.5 초다."
_QUERY = "재시도 500 번이면 어떻게 되나?"
_CONTEXT = "대상 picking-arm-2 · 재시도 한도 17 · 스냅숏의 정원 30"


def _found(report) -> dict:
    return {n.value: n.found_in for n in report.numbers}


def test_each_number_says_where_it_was_found():
    r = validate_numbers("정원 30 · 대기 2.5 · 재시도 500 · 한도 17 · 그리고 99",
                         _EVIDENCE, _QUERY, context=_CONTEXT)
    f = _found(r)
    assert f["30"] == ("evidence", "context"), "둘 다에 있으면 둘 다 — 하나를 고르면 하나를 감춘다"
    assert f["2.5"] == ("evidence",)
    assert f["500"] == ("query",)
    assert f["17"] == ("context",)
    assert f["99"] == (), "어디에도 없는 수는 빈 목록이다"


def test_grounded_means_found_somewhere():
    """`grounded` 의 뜻은 그대로다 — 「모델에게 보여 준 것 어딘가에 있다」. 목록이 비었는가와 같다."""
    r = validate_numbers("정원 30 · 한도 17 · 그리고 99", _EVIDENCE, _QUERY, context=_CONTEXT)
    assert all(n.grounded == bool(n.found_in) for n in r.numbers)
    assert r.unverified_count == sum(1 for n in r.numbers if not n.found_in) == 1


def test_the_response_item_carries_the_list():
    """두 답변 표면이 **이 한 함수**로 항목을 만든다 — 모양이 표면마다 갈리지 않게."""
    items = number_items(validate_numbers("정원 30", _EVIDENCE, context=_CONTEXT))
    assert items == [{"value": "30", "grounded": True, "found_in": ["evidence", "context"]}]


# ── 표기 ──────────────────────────────────────────────────────────────────────

def test_a_trailing_comma_is_not_part_of_the_number():
    """편지 16 에 적은 실측 그대로다. 고치기 전 값은 `"15,"` · `"₩1,000,"` 였다."""
    r = validate_numbers("기준은 30 이고 30.0 과 2.5, 2.50, -15, ₩1,000, 47%, 판 1.2.3, 개수 7", "")
    assert [n.value for n in r.numbers] == ["30", "2.5", "15", "₩1,000", "47%"]


def test_two_numbers_joined_by_a_comma_are_two_numbers():
    """⛔ 옛 패턴은 이것을 한 수 3040 으로 읽어서 **판정까지** 틀렸다."""
    r = validate_numbers("값은 30,40 이다", "근거에는 40 이 있다")
    assert [(n.value, n.grounded) for n in r.numbers] == [("30", False), ("40", True)]


def test_thousands_separators_still_read_as_one_number():
    r = validate_numbers("총 1,000,000 건 · 비용 ₩12,500", "총 1000000 건 · 비용 12500 원")
    assert [(n.value, n.grounded) for n in r.numbers] == [("1,000,000", True), ("₩12,500", True)]
