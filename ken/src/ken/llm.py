"""LLM access behind a small protocol — isolates the Anthropic SDK.

Mirrors nexus's LLMService (provider isolation) but is SYNC for v0 CLI simplicity.
Tests use FakeLLM; no live API calls in the suite.
"""

from __future__ import annotations

import os
from typing import Protocol, runtime_checkable


@runtime_checkable
class LLMClient(Protocol):
    """The seam every ken LLM unit talks to."""

    def generate(self, system: str, user: str) -> str: ...


class AnthropicLLM:
    """Sync Claude wrapper. Isolates the anthropic SDK behind LLMClient.

    default Sonnet 4.6 (`claude-sonnet-4-6`); swap here for other models.
    """

    def __init__(
        self,
        model: str = "claude-sonnet-4-6",
        api_key: str | None = None,
    ) -> None:
        import anthropic

        self.model = model
        self._client = anthropic.Anthropic(api_key=api_key or os.getenv("ANTHROPIC_API_KEY"))

    def generate(self, system: str, user: str, max_tokens: int = 4096) -> str:
        resp = self._client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return "".join(b.text for b in resp.content if getattr(b, "type", None) == "text")


class FakeLLM:
    """Scripted LLM for tests — pops responses in call order; raises when exhausted."""

    def __init__(self, responses: list[str]) -> None:
        self._responses = list(responses)

    def generate(self, system: str, user: str) -> str:
        if not self._responses:
            raise RuntimeError("FakeLLM exhausted: no more scripted responses")
        return self._responses.pop(0)
