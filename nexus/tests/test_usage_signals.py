"""LLM usage 신호 유도 — SPEC-nexus-llm-usage-persistence §5 (순수).

extract_signals 가 AnswerResult.usage 에서 prompt/completion_tokens·cost_usd 를 유도하고,
명시 인자가 각각 독립으로 우선하며, usage 없음/미가격은 None(0 아님)임을 검증.
"""

from __future__ import annotations

import types

from nexus.search.signals import extract_signals


def _result():
    return types.SimpleNamespace(hits=[], graph=None, route_used="hybrid_only")


def _answer(usage):
    return types.SimpleNamespace(citations=[], unverified_citations=0, llm_failed=False, usage=usage)


def _extract(answer, **kw):
    return extract_signals(_result(), answer, path="p", tenant="t", clearance="I", query="q", **kw)


def test_derives_usage_from_answer():
    r = _extract(_answer({"input_tokens": 100, "output_tokens": 50, "cost_usd": 0.001, "model": "m"}))
    assert r.prompt_tokens == 100
    assert r.completion_tokens == 50
    assert r.cost_usd == 0.001


def test_explicit_arg_overrides_independently():
    r = _extract(
        _answer({"input_tokens": 100, "output_tokens": 50, "cost_usd": 0.001, "model": "m"}),
        prompt_tokens=999,
    )
    assert r.prompt_tokens == 999          # 명시 우선
    assert r.completion_tokens == 50       # 나머지는 여전히 유도(독립)
    assert r.cost_usd == 0.001


def test_usage_none_all_none():
    r = _extract(_answer(None))
    assert (r.prompt_tokens, r.completion_tokens, r.cost_usd) == (None, None, None)


def test_tokens_set_but_cost_none_is_unpriced():
    r = _extract(_answer({"input_tokens": 100, "output_tokens": 50, "cost_usd": None, "model": "m"}))
    assert r.prompt_tokens == 100 and r.completion_tokens == 50
    assert r.cost_usd is None               # NULL ≠ 0


def test_no_answer_all_none():
    r = _extract(None)
    assert (r.prompt_tokens, r.completion_tokens, r.cost_usd) == (None, None, None)
