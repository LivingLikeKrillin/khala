"""답변이 값을 **주장했는가**, 그냥 **언급했는가**.

2026-08-26 에 부분일치 채점기가 천장(15/15)에 붙었고, 절 채움을 껐다 켜도 그 숫자가 안 움직였다.
이유는 하나였다 — 값을 표에 적어 놓고 결론에서 물러선 답변을 통과시켰기 때문이다.

여기 고정하는 것은 그 **쌍**이다: 같은 값을 담은 두 답변이 서로 다른 판정을 받아야 한다.
본문은 전부 지어낸 것이다(조직 문서의 사실은 gitignore 된 라벨에만 둔다).
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.ko_eval_answer_quality import (  # noqa: E402
    asserts_value,
    facts_present,
    lead_segments,
    verdict_segments,
)

MUST = [["14일"]]
SURFACES = ["14일"]

#: 결론지은 답변 — 값이 **선두**에 선다.
CONCLUDED = """**회의실은 최대 14일 전부터 예약할 수 있습니다.**

[출처: 예약 규정]

---

| 근거 | 값 |
|---|---|
| 안내문(그림) | 30일 |
| 예약 규정 | 14일 |
"""

#: 물러선 답변 — **같은 값을 담고도** 결론을 안 낸다. 이 쌍이 이 채점기의 존재 이유다.
HEDGED = """**핵심 답변: 두 근거가 서로 다른 값을 말하고 있어 확인이 필요합니다.**

---

| 출처 | 예약 가능 시점 |
|---|---|
| 안내문(그림) | 30일 전 |
| 예약 규정 | 14일 전 |

- [출처: 예약 규정]에는 "14일 전부터"로 기재되어 있습니다.

**확인 전까지는 어느 값도 단정할 수 없습니다.** 담당자 확인을 권장합니다.
"""


def test_the_pair_is_split():
    """**가장 중요한 대조군.** 부분일치는 둘 다 통과시킨다 — 그것이 1판의 결함이었다."""
    assert all(facts_present(MUST, CONCLUDED)) is True
    assert all(facts_present(MUST, HEDGED)) is True          # 1판: 구별 못 함
    assert (asserts_value(SURFACES, CONCLUDED)) is True
    assert (asserts_value(SURFACES, HEDGED)) is False         # 2판: 갈린다


def test_a_verdict_at_the_end_counts_even_when_the_lead_defers():
    """선두만 보는 판은 이것을 떨어뜨렸다(실측 A4) — 접속 부사가 여는 결론도 주장이다."""
    text = """**근거들 사이에 충돌이 있습니다.**

## 정리

| 출처 | 값 |
|---|---|
| 안내문 | 30일 |
| 규정 | 14일 |

따라서 규정의 **14일**이 현행 기준이고, 안내문의 30일은 폐기된 값입니다.
"""
    assert all(facts_present(MUST, text)) is True
    assert (asserts_value(SURFACES, text)) is True


def test_a_value_quoted_as_the_previous_policy_is_not_an_assertion():
    """폐기된 정책의 인용은 답이 아니다. 부분일치는 이것도 통과시킨다(실측 A13)."""
    text = """## 예약 가능 시점

근거들이 서로 다른 시점의 정책을 담고 있습니다.

### 이전 정책

> "예약은 최대 14일 전부터 가능"

### 현행 정책

**요약**: 개정 이후 기준은 **30일 전**입니다.
"""
    assert all(facts_present(MUST, text)) is True
    assert (asserts_value(SURFACES, text)) is False


def test_a_table_row_alone_is_not_an_assertion():
    """표는 근거를 **늘어놓는** 자리다. 늘어놓기는 주장이 아니다."""
    text = """근거를 정리하면 다음과 같습니다.

| 출처 | 값 |
|---|---|
| 규정 | 14일 |
"""
    assert all(facts_present(MUST, text)) is True
    assert (asserts_value(SURFACES, text)) is False


def test_a_lead_heading_does_not_end_the_lead():
    """`## 답변` 으로 여는 답변의 선두는 그 다음 산문이다 — 헤딩은 전환이 아니라 머리말이다."""
    text = "## 답변\n\n최대 **14일** 전부터 예약할 수 있습니다.\n\n---\n\n| 출처 | 값 |\n|---|---|\n"
    assert lead_segments(text)
    assert (asserts_value(SURFACES, text)) is True


def test_the_hole_this_ruler_admits_to():
    """**이 채점기는 자리를 재지 확신을 재지 않는다.** 뚫리는 문구를 실물로 박아 둔다 —
    다음 판이 이것을 고치면 이 테스트가 먼저 빨간불이 되어 알려 준다."""
    text = "여러 근거가 있습니다.\n\n따라서 **14일**일 가능성이 있습니다.\n"
    assert verdict_segments(text)
    assert (asserts_value(SURFACES, text)) is True     # ⚠ 통과한다. 알고 있다.


def test_an_empty_answer_asserts_nothing():
    assert (asserts_value(SURFACES, "")) is False
    assert lead_segments("") == []


def test_a_question_that_asks_for_a_breakdown_is_outside_this_ruler():
    """**정의역 밖을 실물로 박아 둔다.** 나열을 요구하는 질문에서는 표가 곧 답이다 —
    이 채점기는 표를 '늘어놓기' 로 보므로 옳은 답을 떨어뜨린다. 규칙을 늘려 표를 받아들이면
    `HEDGED` 가 같이 통과하므로(값이 표에 있다) **고칠 것이 아니라 안 쓸 자리**다.
    2026-08-18 정책 8문항(홀드아웃)에 걸어 보고 알았다."""
    text = """로그인 방식에 따른 한도는 다음과 같습니다.

| 로그인 방식 | 생성 가능 수 |
|---|---|
| 비로그인 | 불가 |
| 지갑 연동 | 최대 10개 |
"""
    assert all(facts_present([["10개"]], text)) is True
    assert asserts_value(["10개"], text) is False     # ⚠ 오탐. 이 채점기의 질문이 아니다.


def test_the_ruler_takes_one_value_not_a_must_contain():
    """서명이 곧 정의역이다 — `list[list[str]]` 을 받으면 조용히 틀린 답을 낸다."""
    assert asserts_value([], "무엇이든") is False
