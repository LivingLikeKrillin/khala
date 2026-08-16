"""카드 생성 — 얇은 LLM 호출과 **경계 있는 순회** (SPEC §3.2).

이 파일이 이 방향에서 유일하게 비결정적인 곳이다. 그래서 작다. 나머지(후보 선택·파싱·규칙
재검사·낡음)는 `cards.py` 에 있고 전부 결정론이다.

순회에 경계가 있는 이유: §4 가 비용을 주요 위험으로 지목하고 §6.4 가 그것을 게이트하는데,
경계 없는 walk 가 바로 그 비용이 새는 곳이다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import structlog

from nexus.index.cards import Card, CardSpan, parse_card

logger = structlog.get_logger(__name__)

#: 프롬프트가 바뀌면 카드의 의미가 바뀐다. 버전을 카드에 실어 세대가 섞이지 않게 한다.
PROMPT_VERSION = "cards-v1"

#: 순회 상한. 전부 실행마다 기록된다 (§3.2).
MAX_HOPS = 2
MAX_SOURCE_BYTES = 24_000

_SYSTEM = """\
당신은 코드를 읽고 **업무 언어로** 짧게 서술합니다. 코드를 옮겨 적는 것이 아닙니다.

규칙:
1. `behavior` 는 이 코드가 실제로 하는 일을 서술합니다. 코드 줄을 그대로 인용하지 마십시오.
2. 소스의 문자열 리터럴을 그대로 쓰지 마십시오.
3. `domain_terms` 는 **업무에서 쓰는 표현**입니다. 식별자를 번역만 한 말(processPayment → "결제
   처리")은 값이 없습니다. 이 코드가 다루는 업무 개념을 쓰십시오.
4. `code_terms` 는 맨 식별자만, 최대 12개.
5. 확실하지 않으면 짧게 쓰십시오. 지어내지 마십시오.

JSON 만 출력하십시오:
{"subject": "...", "behavior": "...", "domain_terms": [...], "code_terms": [...]}
"""


@dataclass(frozen=True)
class GenerationInput:
    """카드 하나를 만드는 데 필요한 것. 소스는 여기까지만 오고 저장되지 않는다."""
    spans: list[CardSpan]
    sources: dict[str, str]      # span key -> 소스 (검사·프롬프트용, 저장 안 함)
    commit_sha: str


def span_key(span: CardSpan) -> str:
    return f"{span.file_path}:{span.start_line}-{span.end_line}"


def generator_id(model: str) -> str:
    """카드에 실릴 생성자 신원. 선언과 다른 카드는 읽지 않는다 (§3.2).

    문자열이 아니면 죽는다. 한 번은 호출자가 설정 dict 를 모델 자리에 넘겼고, 그대로 두었으면
    `auth.principals` 를 포함한 설정 전체가 모든 카드의 generator 필드에 실렸다.
    """
    if not isinstance(model, str) or not model.strip():
        raise TypeError(f"모델 이름이 문자열이 아닙니다: {type(model).__name__}")
    return f"{model}·{PROMPT_VERSION}·hops{MAX_HOPS}"


_CALL = re.compile(r"\b([A-Za-z_$][A-Za-z0-9_$]*)\s*\(")


def collect_sources(root: Path, spans: list[CardSpan],
                    *, max_bytes: int = MAX_SOURCE_BYTES) -> dict[str, str]:
    """span 들의 소스를 읽는다. **바이트 상한에서 끊는다** — 한 카드가 저장소를 다 읽지 않게.

    단, **대상 span 은 상한보다 커도 반드시 싣는다**(넘치면 잘라서). 소스가 하나도 실리지 않은
    프롬프트를 받은 모델은 서술하지 않고 지어낸다 — 비용을 아끼려다 카드를 환각으로 채우는 것이
    이 함수가 막아야 할 실패다. 상한은 *추가* 홉을 제한하는 장치다.
    """
    out: dict[str, str] = {}
    used = 0
    for i, s in enumerate(spans):
        path = root / s.file_path
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        body = "\n".join(lines[s.start_line - 1 : s.end_line])
        if i == 0:
            body = body[:max_bytes]
        elif used + len(body) > max_bytes:
            break
        out[span_key(s)] = body
        used += len(body)
    return out


def callees(source: str) -> set[str]:
    """호출된 이름들. 다음 홉의 후보 — 정규식이라 근사치이고, 근사여도 상한이 있어 안전하다."""
    return set(_CALL.findall(source))


def build_prompt(subject_symbol: str, sources: dict[str, str]) -> str:
    parts = [f"대상 심볼: {subject_symbol}", ""]
    for key, src in sources.items():
        parts += [f"--- {key} ---", src, ""]
    return "\n".join(parts)


async def generate_card(llm, subject_symbol: str, gi: GenerationInput,
                        *, model: str, max_tokens: int = 800) -> tuple[Card, object]:
    """카드 하나. 반환은 (카드, usage) — 비용은 호출자가 합산해 §6.4 로 보고한다.

    파싱 실패는 예외로 올린다. 반쯤 읽은 카드를 저장하는 것보다 낫다.
    """
    result = await llm.generate_full(
        _SYSTEM, build_prompt(subject_symbol, gi.sources), max_tokens)
    card = parse_card(result.text, spans=gi.spans, commit_sha=gi.commit_sha,
                      generator=generator_id(model))
    return card, result.usage
