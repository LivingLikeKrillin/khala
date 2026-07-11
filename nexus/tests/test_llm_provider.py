"""LLMService provider seam — SPEC-nexus-claude-code-llm-dev-backend §4·§7.

anthropic(기본)과 claude-code(브리지) 백엔드를 고르는 seam. claude-code 는 라이브 `claude`·브리지
없이 httpx transport 주입으로 검증한다. 호출부(api.py×2·a2a·cli)는 무변경이어야 하므로 공개
인터페이스(generate/stream/get_model_name/configured) 형태는 그대로.
"""

from __future__ import annotations

import json

import httpx
import pytest

from nexus.providers import llm
from nexus.providers.llm import LLMService


# ── §4.1 provider 선택 ────────────────────────────────────────────────────────

def test_default_provider_is_anthropic_and_reflects_key(monkeypatch):
    monkeypatch.delenv("NEXUS_LLM_PROVIDER", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-xyz")
    assert LLMService().configured is True


def test_anthropic_is_unconfigured_without_a_key(monkeypatch):
    monkeypatch.delenv("NEXUS_LLM_PROVIDER", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert LLMService().configured is False


def test_unknown_provider_raises_at_construction(monkeypatch):
    monkeypatch.setenv("NEXUS_LLM_PROVIDER", "gpt5-turbo")
    with pytest.raises(ValueError):
        LLMService()


# ── §4.2 claude-code 백엔드 → 브리지 ──────────────────────────────────────────

@pytest.fixture
def bridge(monkeypatch):
    seen = {}

    def handler(request):
        seen["url"] = str(request.url)
        seen["token"] = request.headers.get("X-Bridge-Token")
        seen["json"] = json.loads(request.content)
        return httpx.Response(200, json={"text": "브리지가 만든 근거 답변"})

    monkeypatch.setenv("NEXUS_LLM_PROVIDER", "claude-code")
    monkeypatch.setenv("NEXUS_LLM_BRIDGE_URL", "http://bridge.test:8900")
    monkeypatch.setenv("NEXUS_LLM_BRIDGE_TOKEN", "tok-1")
    monkeypatch.setattr(llm, "_bridge_transport", lambda: httpx.MockTransport(handler))
    return seen


async def test_generate_posts_system_and_prompt_to_bridge(bridge):
    out = await LLMService().generate("너는 근거만 말한다", "결제 토픽?")
    assert out == "브리지가 만든 근거 답변"
    assert "/v1/generate" in bridge["url"]
    assert bridge["token"] == "tok-1"                    # §5 shared secret
    assert bridge["json"]["system"] == "너는 근거만 말한다"
    assert bridge["json"]["prompt"] == "결제 토픽?"


async def test_stream_yields_the_whole_answer_once(bridge):
    chunks = [c async for c in LLMService().stream("s", "u")]
    assert chunks == ["브리지가 만든 근거 답변"]           # dev fallback: 단일 yield


async def test_claude_code_is_configured_when_bridge_url_set(bridge):
    assert LLMService().configured is True


async def test_bridge_error_raises_rather_than_reporting_unconfigured(monkeypatch):
    monkeypatch.setenv("NEXUS_LLM_PROVIDER", "claude-code")
    monkeypatch.setenv("NEXUS_LLM_BRIDGE_URL", "http://bridge.test:8900")
    monkeypatch.setattr(
        llm, "_bridge_transport",
        lambda: httpx.MockTransport(lambda r: httpx.Response(502, json={"error": "boom"})))
    svc = LLMService()
    assert svc.configured is True                        # 설정은 됐다
    with pytest.raises(Exception):                       # 실패는 호출 시점 raise = API-error 경로
        await svc.generate("s", "u")


def test_get_model_name_still_works(monkeypatch):
    monkeypatch.setenv("NEXUS_LLM_PROVIDER", "claude-code")
    monkeypatch.setenv("NEXUS_LLM_MODEL", "claude-sonnet-4-6")
    assert LLMService().get_model_name() == "claude-sonnet-4-6"
