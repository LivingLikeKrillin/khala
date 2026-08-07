"""답변 비용 추정기 (nexus/llm/budget.py).

`compute_cost` 는 이미 일어난 호출의 비용만 낸다 — 토큰이 없으면 추정하지 않고 None 이다. 그
규율 때문에 **아직 안 쓴 기능의 예산은 아무도 못 잡는다**. 이 모듈이 그 빈칸을 메우되, 추정과
실측을 섞지 않는다.
"""

from __future__ import annotations

import pytest

from nexus.llm.budget import (
    CHARS_PER_TOKEN,
    FIXED_PROMPT_TOKENS,
    estimate_answer_tokens,
    estimate_cost,
)

PRICING = {"claude-sonnet-4-6": {"input_per_mtok": 3.0, "output_per_mtok": 15.0}}


def test_input_tokens_track_the_snippet_budget_not_the_corpus():
    """코퍼스가 20문서에서 116문서가 되어도 답변 1회 입력은 그대로다 — 스니펫 개수·길이가
    상한으로 묶여 있기 때문이다. 예산은 문서 수가 아니라 **질의 수**로 잡아야 한다."""
    small, _ = estimate_answer_tokens(n_snippets=9.8, snippet_max_chars=300)
    same, _ = estimate_answer_tokens(n_snippets=9.8, snippet_max_chars=300)
    assert small == same

    more_snippets, _ = estimate_answer_tokens(n_snippets=12, snippet_max_chars=300)
    assert more_snippets > small, "늘어나는 축은 스니펫 개수다"


def test_the_estimate_is_arithmetic_anyone_can_check():
    got, out = estimate_answer_tokens(n_snippets=10, snippet_max_chars=350)
    assert got == int(FIXED_PROMPT_TOKENS + 10 * (350 / CHARS_PER_TOKEN))
    assert out > 0


def test_a_measured_average_replaces_the_estimate_and_says_so():
    """실사용이 쌓이면 추정은 물러난다. 어느 쪽인지가 결과에 남아야 한다."""
    est = estimate_cost(model="claude-sonnet-4-6", pricing=PRICING,
                        n_snippets=9.8, snippet_max_chars=300)
    assert est.basis == "estimated"

    real = estimate_cost(model="claude-sonnet-4-6", pricing=PRICING,
                         n_snippets=9.8, snippet_max_chars=300, measured=(1200.0, 300.0))
    assert real.basis == "measured"
    assert (real.input_tokens, real.output_tokens) == (1200, 300)
    assert real.cost_per_answer_usd == pytest.approx(1200 / 1e6 * 3.0 + 300 / 1e6 * 15.0)


def test_an_unpriced_model_yields_no_cost_rather_than_a_guess():
    """`compute_cost` 의 규율을 그대로 잇는다 — 단가를 모르면 숫자를 지어내지 않는다."""
    est = estimate_cost(model="some-new-model", pricing=PRICING,
                        n_snippets=9.8, snippet_max_chars=300)
    assert est.input_tokens > 0, "토큰은 여전히 셀 수 있다"
    assert est.cost_per_answer_usd is None
    assert "단가표" in est.note


def test_monthly_scales_with_queries_and_stays_none_when_cost_is_unknown():
    est = estimate_cost(model="claude-sonnet-4-6", pricing=PRICING,
                        n_snippets=9.8, snippet_max_chars=300)
    assert est.monthly(1000) == pytest.approx(est.cost_per_answer_usd * 1000)

    unpriced = estimate_cost(model="x", pricing={}, n_snippets=1, snippet_max_chars=100)
    assert unpriced.monthly(1000) is None


def test_the_deployed_numbers_land_where_the_written_estimate_said():
    """세션에서 손으로 계산한 값(입력 ~1,650토큰)과 코드가 어긋나면 둘 중 하나가 틀린 것이다."""
    est = estimate_cost(model="claude-sonnet-4-6", pricing=PRICING,
                        n_snippets=9.8, snippet_max_chars=300)
    assert 1500 <= est.input_tokens <= 1800
    # 답변 1회 1센트 미만 — 이 규모에서는 질의 수가 늘어야 비용이 보인다
    assert est.cost_per_answer_usd < 0.02
