"""LLM 토큰/비용 포착 — SPEC-nexus-llm-usage-capture §5.

generate_full/stream(usage_out=)가 provider 가 보고한 토큰 + config 단가 기반 비용을 노출한다.
generate()->str 및 기존 호출부는 무변경. 결정론·무예외(비용 미상은 None, 지어내지 않음).
"""

from __future__ import annotations

import types

import httpx
import pytest

from nexus.providers import llm
from nexus.providers.llm import LLMResult, LLMService, Usage, compute_cost

_MODEL = "claude-sonnet-4-6"
_PRICING = {_MODEL: {"input_per_mtok": 3.0, "output_per_mtok": 15.0}}


# ── compute_cost (순수) ───────────────────────────────────────────────────────

def test_compute_cost_table_hit():
    # 100/1e6*3 + 50/1e6*15 = 0.0003 + 0.00075
    assert compute_cost(100, 50, _MODEL, _PRICING) == pytest.approx(0.00105)


def test_compute_cost_model_absent_is_none():
    assert compute_cost(100, 50, "unpriced-model", _PRICING) is None


def test_compute_cost_none_tokens_is_none():
    assert compute_cost(None, 50, _MODEL, _PRICING) is None
    assert compute_cost(100, None, _MODEL, _PRICING) is None


def test_compute_cost_malformed_or_partial_entry_is_none():
    assert compute_cost(100, 50, _MODEL, {_MODEL: {"input_per_mtok": 3.0}}) is None  # output 없음
    assert compute_cost(100, 50, _MODEL, {_MODEL: {"input_per_mtok": "x", "output_per_mtok": 1}}) is None
    assert compute_cost(100, 50, _MODEL, {}) is None                                  # 빈 표


# ── claude-code 백엔드 (브리지, usage 없음) ───────────────────────────────────

@pytest.fixture
def bridge(monkeypatch):
    def handler(request):
        return httpx.Response(200, json={"text": "브리지 답변"})
    monkeypatch.setenv("NEXUS_LLM_PROVIDER", "claude-code")
    monkeypatch.setenv("NEXUS_LLM_BRIDGE_URL", "http://bridge.test:8900")
    monkeypatch.setenv("NEXUS_LLM_MODEL", _MODEL)
    monkeypatch.setattr(llm, "_bridge_transport", lambda: httpx.MockTransport(handler))


async def test_claude_code_generate_full_has_none_usage(bridge):
    r = await LLMService(pricing=_PRICING).generate_full("s", "u")
    assert isinstance(r, LLMResult)
    assert r.text == "브리지 답변"
    assert r.usage == Usage(input_tokens=None, output_tokens=None, cost_usd=None, model=_MODEL)


async def test_plain_generate_still_returns_str(bridge):
    out = await LLMService(pricing=_PRICING).generate("s", "u")
    assert out == "브리지 답변"                      # -> str 계약 불변


async def test_stream_usage_out_appends_one_usage(bridge):
    sink: list = []
    chunks = [c async for c in LLMService(pricing=_PRICING).stream("s", "u", usage_out=sink)]
    assert chunks == ["브리지 답변"]
    assert len(sink) == 1
    assert sink[0].model == _MODEL and sink[0].cost_usd is None


async def test_stream_without_usage_out_unchanged(bridge):
    chunks = [c async for c in LLMService(pricing=_PRICING).stream("s", "u")]
    assert chunks == ["브리지 답변"]                 # back-compat


# ── anthropic 백엔드 (클라이언트 주입, usage 있음) ────────────────────────────

def _fake_anthropic_client(in_tok=100, out_tok=50):
    resp = types.SimpleNamespace(
        content=[types.SimpleNamespace(text="근거 답변")],
        usage=types.SimpleNamespace(input_tokens=in_tok, output_tokens=out_tok),
    )

    class _Messages:
        async def create(self, **kw):
            return resp

    return types.SimpleNamespace(messages=_Messages())


async def test_anthropic_generate_full_carries_tokens_and_cost(monkeypatch):
    monkeypatch.delenv("NEXUS_LLM_PROVIDER", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-x")
    monkeypatch.setenv("NEXUS_LLM_MODEL", _MODEL)
    svc = LLMService(pricing=_PRICING)
    svc._backend._get_client = lambda: _fake_anthropic_client(100, 50)

    r = await svc.generate_full("s", "u")
    assert r.text == "근거 답변"
    assert r.usage.input_tokens == 100 and r.usage.output_tokens == 50
    assert r.usage.model == _MODEL
    assert r.usage.cost_usd == pytest.approx(0.00105)
    # generate() 는 여전히 bare 문자열
    assert await svc.generate("s", "u") == "근거 답변"
