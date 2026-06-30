"""LLM 답변 생성 래퍼.

Claude API 직접 호출을 격리하여, 2.0에서 Multi-LLM(GPT-4o, Gemini 등)으로 교체 시
이 클래스만 수정하면 된다. Claude API를 직접 호출하지 말 것.

사용법:
    svc = LLMService()
    answer = await svc.generate(messages, evidence_packet)
"""

from __future__ import annotations

import os
from typing import AsyncIterator

import anthropic


class LLMService:
    """LLM 답변 생성. Claude API 호출을 격리."""

    # 현행 Sonnet 기본값. 직전 하드코딩(claude-sonnet-4-20250514)은 2026-06-15 EOL → 404.
    # 다음 EOL 은 코드가 아니라 NEXUS_LLM_MODEL 환경변수 한 줄로 넘긴다(.env 온램프).
    DEFAULT_MODEL = "claude-sonnet-4-6"

    def __init__(
        self,
        model: str | None = None,
        api_key: str | None = None,
    ) -> None:
        self.model = model or os.getenv("NEXUS_LLM_MODEL") or self.DEFAULT_MODEL
        resolved_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        # 키가 실제로 해석되었는지(빈 문자열·None 제외) — 호출 전에 알 수 있는 결정적 신호.
        # 무키는 '버그'가 아니라 '미설정'이므로, 호출자가 일시적 API 오류와 구분해 안내할 수 있게 노출.
        self.configured = bool(resolved_key)
        self._client = anthropic.AsyncAnthropic(api_key=resolved_key)

    async def generate(
        self,
        system_prompt: str,
        user_message: str,
        max_tokens: int = 4096,
    ) -> str:
        """근거 기반 답변 생성. 동기 응답."""
        response = await self._client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            system=system_prompt,
            messages=[{"role": "user", "content": user_message}],
        )
        return response.content[0].text

    async def stream(
        self,
        system_prompt: str,
        user_message: str,
        max_tokens: int = 4096,
    ) -> AsyncIterator[str]:
        """스트리밍 답변. 2.0 채팅 UI에서 SSE로 활용."""
        async with self._client.messages.stream(
            model=self.model,
            max_tokens=max_tokens,
            system=system_prompt,
            messages=[{"role": "user", "content": user_message}],
        ) as stream:
            async for text in stream.text_stream:
                yield text

    def get_model_name(self) -> str:
        return self.model
