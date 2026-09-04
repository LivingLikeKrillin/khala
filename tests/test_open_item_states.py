"""열린 항목의 **상태** — 기다리는 것과 미룬 것을 갈라 센다.

⛔ **왜 있나 (2026-09-03, 사용자 지적).** 머리말이 *"미결 44"* 라고만 말하면 읽는 사람은
**처리해야 하는데 안 한 것 44건**으로 읽는다. 실제로는 41건이 *조건이 오면 다시 연다* 고
처분까지 적어 둔 항목이다. 한 수로 말할 수 있게 두면 반드시 그렇게 인용되므로, 검사기가
머리말에 **두 수를 다 요구한다.**
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("coc", ROOT / "scripts" / "check_open_counts.py")
coc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(coc)


def test_immediate_is_waiting():
    assert coc.state_of("즉시") == "대기"


def test_a_named_condition_is_deferred():
    assert coc.state_of("두 번째 조직") == "조건"


def test_an_empty_or_dash_trigger_is_deferred():
    """처분이 없는 줄을 '지금 할 일' 로 세면 목록이 실제보다 급해 보인다."""
    assert coc.state_of("") == "조건" and coc.state_of("—") == "조건"


def test_the_word_now_inside_an_explanation_is_not_a_fired_trigger():
    """⭐ 실제 오분류 둘 — 이 문장들은 **안 울렸다는 설명**이다."""
    assert coc.state_of("옛 이미지로 되돌아갈 일이 없어진 뒤. 지금 지우면 롤백한 …") == "조건"
    assert coc.state_of("**이 신호를 켜기 전.** 지금은 테넌트 허용목록이 비어 꺼져 있다") == "조건"


def test_a_future_date_is_still_deferred():
    assert coc.state_of("2026-11-10") == "조건"


# ── 머리말이 두 수를 다 말해야 한다 ──────────────────────────────────────────

BODY = """## 요약

| 구분 | 수 | x |
|---|---|---|
| **사람만 할 수 있는 것** | **1** | — |
| **내가 할 수 있는 것** | **1** | — |
| **대기** — 트리거가 울렸다 | **1** | — |
| **조건** — 트리거를 기다린다 | **1** | — |

## 1. 사람만 할 수 있는 것 (1)

| H1 | 무엇 | 즉시 |

## 2. 내가 할 수 있는 것 (1)

| A1 | 무엇 | 두 번째 조직 |

## 3. 결정
"""


def test_a_correct_file_passes():
    assert coc.problems(BODY) == []


def test_the_split_is_counted_not_mirrored():
    assert coc.by_state(BODY) == {"대기": 1, "조건": 1}


def test_a_missing_state_line_is_refused():
    """이것이 이 검사의 목적이다 — 한 수로만 말하는 파일을 못 만들게 한다."""
    got = coc.problems(BODY.replace("| **대기** — 트리거가 울렸다 | **1** | — |\n", ""))
    assert got and "대기" in got[0]


def test_a_stale_state_number_is_refused():
    got = coc.problems(BODY.replace("| **대기** — 트리거가 울렸다 | **1** |",
                                    "| **대기** — 트리거가 울렸다 | **7** |"))
    assert got and "머리말 7" in got[0]


def test_the_section_totals_are_still_checked():
    head = "## 1. 사람만 할 수 있는 것 "
    got = coc.problems(BODY.replace(head + "(1)", head + "(9)"))
    assert got
