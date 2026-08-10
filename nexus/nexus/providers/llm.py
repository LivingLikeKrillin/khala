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
from dataclasses import dataclass, replace
from typing import AsyncIterator

import httpx

_DEFAULT_BRIDGE_URL = "http://host.docker.internal:8900"
_BRIDGE_TIMEOUT = 180.0


@dataclass(frozen=True)
class Usage:
    """LLM 콜 1건의 토큰/비용. 미상은 None(0 아님) — 지어내지 않는다(SPEC §3)."""
    input_tokens: int | None
    output_tokens: int | None
    cost_usd: float | None
    model: str


@dataclass(frozen=True)
class LLMResult:
    text: str
    usage: Usage


def compute_cost(
    input_tokens: int | None, output_tokens: int | None, model: str, pricing: dict
) -> float | None:
    """USD 비용 = in/1e6*단가 + out/1e6*단가. 순수·무예외.

    다음 중 하나라도면 None(부분/추정 금지): 토큰 미상 · 모델이 단가표에 없음 ·
    엔트리가 불완전/비수치. 단가는 백만토큰당(per_mtok), 운영자 관리.
    """
    if input_tokens is None or output_tokens is None:
        return None
    entry = pricing.get(model)
    if not isinstance(entry, dict):
        return None
    try:
        in_price = float(entry["input_per_mtok"])
        out_price = float(entry["output_per_mtok"])
    except (KeyError, TypeError, ValueError):
        return None
    return input_tokens / 1e6 * in_price + output_tokens / 1e6 * out_price


def _bridge_transport():  # pragma: no cover - 테스트가 MockTransport 로 override
    """claude-code 백엔드용 httpx transport. 기본 None → 실제 네트워크. 테스트가 주입."""
    return None


def _load_pricing() -> dict:
    """config.yaml 의 llm.pricing 을 읽는다. best-effort — 실패/부재 시 {} (모든 cost=None)."""
    try:
        import yaml  # 지연 임포트
        from pathlib import Path

        cfg = yaml.safe_load(Path("config.yaml").read_text(encoding="utf-8")) or {}
        pricing = (cfg.get("llm") or {}).get("pricing") or {}
        return pricing if isinstance(pricing, dict) else {}
    except Exception:
        return {}


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

    async def generate_full(
        self, system_prompt: str, user_message: str, max_tokens: int
    ) -> LLMResult:
        resp = await self._get_client().messages.create(
            model=self.model, max_tokens=max_tokens,
            system=system_prompt, messages=[{"role": "user", "content": user_message}],
        )
        u = resp.usage
        return LLMResult(
            text=resp.content[0].text,
            usage=Usage(u.input_tokens, u.output_tokens, None, self.model),  # cost 는 service 가 채움
        )

    async def vision_extract(
        self, system_prompt: str, image_b64: str, media_type: str, max_tokens: int
    ) -> str:
        """이미지 1장 → 텍스트. **tool 정의 없음, 경로 없음, 이미지 1개** (ADR-0010 §6).

        요청에 tools 를 넣지 않는 것이 이 경로의 통제다 — 부를 tool 이 없으면 tool 호출도 없다.
        추출은 quarantine 게이트보다 **먼저** 돌기 때문에(그래야 스캐너가 픽셀 속 텍스트를 본다)
        판독기가 무엇이든 할 수 있으면 그 순서가 위험해진다.
        """
        resp = await self._get_client().messages.create(
            model=self.model, max_tokens=max_tokens, system=system_prompt,
            messages=[{"role": "user", "content": [
                {"type": "image",
                 "source": {"type": "base64", "media_type": media_type, "data": image_b64}},
            ]}],
        )
        text = resp.content[0].text if resp.content else ""
        # **stop_reason 을 함께 돌려준다.** 이걸 버리면 max_tokens 에서 잘린 응답이 완결된 추출과
        # 구별되지 않는다 — 조밀한 명세표가 절반만 담긴 채 "완전한 추출" 로 여섯 hop 을 통과한다.
        return text, getattr(resp, "stop_reason", None)

    async def stream(
        self, system_prompt: str, user_message: str, max_tokens: int,
        usage_out: list | None = None,
    ) -> AsyncIterator[str]:
        async with self._get_client().messages.stream(
            model=self.model, max_tokens=max_tokens,
            system=system_prompt, messages=[{"role": "user", "content": user_message}],
        ) as stream:
            async for text in stream.text_stream:
                yield text
            # 성공 완료 시에만 usage 를 남긴다(예외 시엔 여기 못 와서 sink 는 빈 채 — SPEC I-004).
            if usage_out is not None:
                final = await stream.get_final_message()
                fu = final.usage
                usage_out.append(Usage(fu.input_tokens, fu.output_tokens, None, self.model))


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

    async def generate_full(
        self, system_prompt: str, user_message: str, max_tokens: int
    ) -> LLMResult:
        async with httpx.AsyncClient(timeout=_BRIDGE_TIMEOUT, transport=_bridge_transport()) as c:
            resp = await c.post(
                f"{self.bridge_url}/v1/generate",
                headers={"X-Bridge-Token": self._token},
                json={"system": system_prompt, "prompt": user_message, "model": self.model},
            )
        resp.raise_for_status()   # 브리지 502/504 → 예외 → 호출부의 API-error 폴백
        # 브리지는 오늘 text 만 준다 → usage 미상(None). 지어내지 않는다(Unit C 에서 브리지 확장).
        return LLMResult(text=resp.json()["text"], usage=Usage(None, None, None, self.model))

    async def stream(
        self, system_prompt: str, user_message: str, max_tokens: int,
        usage_out: list | None = None,
    ) -> AsyncIterator[str]:
        # dev 폴백: claude -p 는 버퍼링이라 토큰 단위 스트림이 없다 → 전체를 한 번에 yield.
        r = await self.generate_full(system_prompt, user_message, max_tokens)
        yield r.text
        if usage_out is not None:
            usage_out.append(r.usage)


class LLMService:
    """LLM 답변 생성. 백엔드 선택을 격리한다."""

    # 현행 Sonnet 기본값. 직전 하드코딩(claude-sonnet-4-20250514)은 2026-06-15 EOL → 404.
    # 다음 EOL 은 코드가 아니라 NEXUS_LLM_MODEL 환경변수 한 줄로 넘긴다(.env 온램프).
    DEFAULT_MODEL = "claude-sonnet-4-6"

    def __init__(
        self, model: str | None = None, api_key: str | None = None,
        pricing: dict | None = None,
    ) -> None:
        self.model = model or os.getenv("NEXUS_LLM_MODEL") or self.DEFAULT_MODEL
        self._pricing = pricing if pricing is not None else _load_pricing()
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

    async def generate_full(
        self, system_prompt: str, user_message: str, max_tokens: int = 4096
    ) -> LLMResult:
        """답변 + 토큰/비용(usage). 비용은 여기서 config 단가로 채운다(백엔드는 토큰만)."""
        r = await self._backend.generate_full(system_prompt, user_message, max_tokens)
        cost = compute_cost(r.usage.input_tokens, r.usage.output_tokens, self.model, self._pricing)
        return LLMResult(text=r.text, usage=replace(r.usage, cost_usd=cost))

    async def generate(
        self, system_prompt: str, user_message: str, max_tokens: int = 4096
    ) -> str:
        """근거 기반 답변 생성. -> str 계약 불변(usage 무시). 기존 호출부 무변경."""
        return (await self.generate_full(system_prompt, user_message, max_tokens)).text

    async def vision_extract(
        self, system_prompt: str, image_b64: str, media_type: str, max_tokens: int = 2048
    ) -> str:
        """그림에서 텍스트를 읽는다 (SPEC-nexus-screenshot-text-extraction §4.2).

        백엔드가 이미지를 못 받으면 **조용히 텍스트로 되돌아가지 않는다** — 그러면 판독기가
        아무것도 못 본 채 그럴듯한 것을 지어낼 자리가 생긴다. 못 하면 못 한다고 말한다.
        """
        fn = getattr(self._backend, "vision_extract", None)
        if fn is None:
            raise NotImplementedError(
                f"{type(self._backend).__name__} 는 이미지를 받지 못한다. "
                "NEXUS_LLM_PROVIDER=anthropic 이 필요하다 (claude-code 브리지는 텍스트 전용).")
        return await fn(system_prompt, image_b64, media_type, max_tokens)

    async def stream(
        self, system_prompt: str, user_message: str, max_tokens: int = 4096,
        usage_out: list | None = None,
    ) -> AsyncIterator[str]:
        """스트리밍 답변. usage_out 주면 성공 완료 시 Usage(비용 포함) 1건 append."""
        sink: list | None = [] if usage_out is not None else None
        async for text in self._backend.stream(system_prompt, user_message, max_tokens, sink):
            yield text
        if usage_out is not None and sink:
            u = sink[0]
            cost = compute_cost(u.input_tokens, u.output_tokens, self.model, self._pricing)
            usage_out.append(replace(u, cost_usd=cost))

    def get_model_name(self) -> str:
        return self.model
