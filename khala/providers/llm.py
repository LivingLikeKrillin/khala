"""LLM 답변 생성 래퍼.

Claude API 직접 호출을 격리하여, 2.0에서 Multi-LLM(GPT-4o, Gemini 등)으로 교체 시
이 클래스만 수정하면 된다. Claude API를 직접 호출하지 말 것.

사용법:
    svc = LLMService()
    answer = await svc.generate(messages, evidence_packet)
"""

from __future__ import annotations

import os
from typing import Any, AsyncIterator

import anthropic


class LLMService:
    """LLM 답변 생성. Claude API 호출을 격리."""

    def __init__(
        self,
        model: str = "claude-sonnet-4-20250514",
        api_key: str | None = None,
    ) -> None:
        self.model = model
        self._client = anthropic.AsyncAnthropic(
            api_key=api_key or os.getenv("ANTHROPIC_API_KEY"),
        )

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
