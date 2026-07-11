"""LLM 답변 생성 래퍼.

Claude API 직접 호출을 격리하여, Multi-LLM(GPT-4o, Gemini 등)이나 로컬 백엔드로 교체 시
이 모듈만 수정하면 된다. Claude API를 직접 호출하지 말 것.

provider seam (SPEC-nexus-claude-code-llm-dev-backend): `NEXUS_LLM_PROVIDER` 로 백엔드를 고른다.
  anthropic   (기본) — Claude API. `ANTHROPIC_API_KEY` 필요.
  claude-code (dev)  — 호스트에서 도는 Claude Code 를 브리지 경유로 사용. 유료 키 불필요.
호출부(api.py·a2a·cli)는 무변경 — 선택은 LLMService 안에서 일어나고 공개 인터페이스는 그대로다.

사용법:
    svc = LLMService()
    answer = await svc.generate(system_prompt, user_message)
"""

from __future__ import annotations

import os
from typing import AsyncIterator

import httpx

_DEFAULT_BRIDGE_URL = "http://host.docker.internal:8900"
_BRIDGE_TIMEOUT = 180.0


def _bridge_transport():  # pragma: no cover - 테스트가 MockTransport 로 override
    """claude-code 백엔드용 httpx transport. 기본 None → 실제 네트워크. 테스트가 주입."""
    return None


class _AnthropicBackend:
    """Claude API 백엔드. 클라이언트는 지연 생성(키 없이 구성돼도 구성 시점엔 안 터진다)."""

    def __init__(self, model: str, api_key: str | None) -> None:
        self.model = model
        self._resolved_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        self.configured = bool(self._resolved_key)
        self._client = None

    def _get_client(self):
        if self._client is None:
            import anthropic
            self._client = anthropic.AsyncAnthropic(api_key=self._resolved_key)
        return self._client

    async def generate(self, system_prompt: str, user_message: str, max_tokens: int) -> str:
        resp = await self._get_client().messages.create(
            model=self.model, max_tokens=max_tokens,
            system=system_prompt, messages=[{"role": "user", "content": user_message}],
        )
        return resp.content[0].text

    async def stream(
        self, system_prompt: str, user_message: str, max_tokens: int
    ) -> AsyncIterator[str]:
        async with self._get_client().messages.stream(
            model=self.model, max_tokens=max_tokens,
            system=system_prompt, messages=[{"role": "user", "content": user_message}],
        ) as stream:
            async for text in stream.text_stream:
                yield text


class _ClaudeCodeBackend:
    """dev 백엔드. 호스트 브리지(claude -p)로 POST. 유료 키 없음.

    `configured` 는 브리지 URL 이 있으면 True — 백엔드는 *설정된* 것이다. 브리지가 닿지 않는 건
    호출 시점 오류(=API-error 경로)지, '미설정'이 아니다(운영자가 키를 잊었다고 오도하면 안 된다).
    """

    def __init__(self, model: str) -> None:
        self.model = model
        self.bridge_url = (os.getenv("NEXUS_LLM_BRIDGE_URL") or _DEFAULT_BRIDGE_URL).rstrip("/")
        self._token = os.getenv("NEXUS_LLM_BRIDGE_TOKEN", "")
        self.configured = bool(self.bridge_url)

    async def generate(self, system_prompt: str, user_message: str, max_tokens: int) -> str:
        async with httpx.AsyncClient(timeout=_BRIDGE_TIMEOUT, transport=_bridge_transport()) as c:
            resp = await c.post(
                f"{self.bridge_url}/v1/generate",
                headers={"X-Bridge-Token": self._token},
                json={"system": system_prompt, "prompt": user_message, "model": self.model},
            )
        resp.raise_for_status()   # 브리지 502/504 → 예외 → 호출부의 API-error 폴백
        return resp.json()["text"]

    async def stream(
        self, system_prompt: str, user_message: str, max_tokens: int
    ) -> AsyncIterator[str]:
        # dev 폴백: claude -p 는 버퍼링이라 토큰 단위 스트림이 없다 → 전체를 한 번에 yield.
        yield await self.generate(system_prompt, user_message, max_tokens)


class LLMService:
    """LLM 답변 생성. 백엔드 선택을 격리한다."""

    # 현행 Sonnet 기본값. 직전 하드코딩(claude-sonnet-4-20250514)은 2026-06-15 EOL → 404.
    # 다음 EOL 은 코드가 아니라 NEXUS_LLM_MODEL 환경변수 한 줄로 넘긴다(.env 온램프).
    DEFAULT_MODEL = "claude-sonnet-4-6"

    def __init__(self, model: str | None = None, api_key: str | None = None) -> None:
        self.model = model or os.getenv("NEXUS_LLM_MODEL") or self.DEFAULT_MODEL
        provider = (os.getenv("NEXUS_LLM_PROVIDER") or "anthropic").strip().lower()
        if provider == "anthropic":
            self._backend: _AnthropicBackend | _ClaudeCodeBackend = _AnthropicBackend(
                self.model, api_key)
        elif provider == "claude-code":
            self._backend = _ClaudeCodeBackend(self.model)
        else:
            raise ValueError(
                f"알 수 없는 NEXUS_LLM_PROVIDER: {provider!r} "
                "(기대값: 'anthropic' 또는 'claude-code')")
        # 호출 전 결정적 신호: 키/브리지가 실제로 해석됐는가. 호출자가 일시적 API 오류와 구분해 안내.
        self.configured = self._backend.configured

    async def generate(
        self, system_prompt: str, user_message: str, max_tokens: int = 4096
    ) -> str:
        """근거 기반 답변 생성. 동기 응답."""
        return await self._backend.generate(system_prompt, user_message, max_tokens)

    async def stream(
        self, system_prompt: str, user_message: str, max_tokens: int = 4096
    ) -> AsyncIterator[str]:
        """스트리밍 답변. 채팅 UI에서 SSE로 활용."""
        async for text in self._backend.stream(system_prompt, user_message, max_tokens):
            yield text

    def get_model_name(self) -> str:
        return self.model
