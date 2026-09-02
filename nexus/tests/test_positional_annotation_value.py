"""이름 없이 적힌 어노테이션 인자를 읽는다 — 그리고 **엉뚱한 칸에 앉히지 않는다.**

**왜 (실측 2026-09-02).** 팀 코드(테스트 제외 899파일)에서 값이 앉은 모양을 셌다:

    static final 숫자 상수            66   읽음
    이름 있는 어노테이션 인자          59   읽음
    위치 인자 `@Min(1)`               29   **못 읽음**  ← 이 파일이 여는 자리
    가드절 `if (… > N)`               18   못 읽음 (⛔ 열지 않는다)
    @Scheduled(cron=)                  7   못 읽음
    상수를 참조하는 어노테이션 인자      1   못 읽음

⛔ **가드절과 같은 부류가 아니다.** 가드절을 읽는 것은 값 읽기가 아니라 코드 이해에 가깝고,
틀리면 확신하는 문장으로 나간다(A25). 위치 인자는 **같은 어노테이션인데 이름만 없는 것**이고,
자바 규칙이 그 자리를 `value` 로 못박아 두었다. 그래서 해석이 끼어들 여지가 없다.
"""

from __future__ import annotations

import pytest

from nexus.index.code_source import _attr_value


# ── 여는 것 ──────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("args,expected", [
    ("1", "1"), ("0", "0"), ("60", "60"), (" 500 ", "500"),
])
def test_a_single_unnamed_argument_is_the_value_element(args, expected):
    """자바 규칙 — 원소가 하나면 `value=` 를 생략할 수 있고, 그 자리가 `value` 다."""
    assert _attr_value(args, "value") == expected


def test_the_named_form_still_wins():
    """대조군 — 오늘 읽던 것이 그대로 읽혀야 한다."""
    assert _attr_value("value = 1", "value") == "1"
    assert _attr_value("max = 20", "max") == "20"
    assert _attr_value("min = 1, max = 20", "max") == "20"


def test_a_string_literal_with_a_comma_is_not_cut():
    """⛔ 쉼표로 쪼개면 조용히 잘린 값이 나간다. cron 표현식이 실제로 그 모양이다."""
    assert _attr_value('"0 0,30 * * * *"', "value") == '"0 0,30 * * * *"'


# ── 열지 않는 것 (대조군) ────────────────────────────────────────────────────

def test_a_positional_value_never_fills_another_attribute():
    """⛔ **이 파일에서 가장 중요한 검사.**

    `@Size.max` 를 묻는 claim 이 `@Min(1)` 로 채워지면, 답변의 *"코드는 …"* 자리에 남의 값이
    조용히 앉는다. 값이 틀린 것보다 나쁘다 — 틀린 채로 **확신**하기 때문이다.
    """
    assert _attr_value("1", "max") is None
    assert _attr_value("1", "min") is None
    assert _attr_value("1", "cron") is None


def test_a_named_form_does_not_leak_into_value():
    """`@Size(max = 20)` 에게 `value` 를 물으면 없다고 답해야 한다 — 20 이 아니다."""
    assert _attr_value("max = 20", "value") is None
    assert _attr_value("min = 1, max = 20", "value") is None


def test_an_empty_argument_list_is_nothing():
    for args in ("", "   "):
        assert _attr_value(args, "value") is None


def test_an_equals_inside_a_string_does_not_disguise_a_named_form():
    """문자열 안의 `=` 는 이름 있는 형태가 아니다 — 지운 뒤 판정하므로 위치 인자로 읽힌다."""
    assert _attr_value('"a=b"', "value") == '"a=b"'
