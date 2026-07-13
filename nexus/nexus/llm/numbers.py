"""답변 숫자의 근거 대조 — SPEC-nexus-answer-number-verification.

LLM 이 뱉은 답변의 **유의미한 숫자**가, LLM 에게 실제로 보여준 것(evidence + query)에
실재하는지 결정론적으로 대조한다. "System decides, LLM narrates": 지어낸 통계는 시스템이
값-일치로 판정하고, LLM 은 서술만 한다. #134(인용 존재검증)의 숫자판.

순수 함수(I/O 없음, 무예외). 값-존재만 본다(단위/의미 아님) — 오탐(무고)보다 미탐(놓침)을
구조적으로 택한다. LLMware evidence_check_numbers 에서 착안, 구현은 독립.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# 버전/IP 등 점 2개 이상 토큰 — 숫자가 아니라 식별자. 추출 전에 제거(양쪽 텍스트 모두).
_VERSION = re.compile(r"\d+(?:\.\d+){2,}")
# 숫자 토큰: 선택적 통화기호 + 숫자(천단위 콤마 허용) + 선택적 소수 + 인접 % (부호는 안 잡음).
_NUM = re.compile(r"[$₩]?\d[\d,]*(?:\.\d+)?%?")


@dataclass(frozen=True)
class NumberCheck:
    value: str      # 원래 표면형(표시용): "47%"
    grounded: bool


@dataclass(frozen=True)
class NumberReport:
    numbers: list[NumberCheck]
    unverified_count: int


def _canonical(token: str) -> str:
    """토큰을 값 기준 정규형으로. % 클래스는 분리 유지(5% ≠ 5)."""
    has_pct = token.endswith("%")
    s = token.strip("$₩% ").replace(",", "")
    if "." in s:
        s = s.rstrip("0").rstrip(".")   # 5.00→5, 0.50→0.5, 3.140→3.14 (정수는 '.' 없어 안전)
    return f"{s}%" if has_pct else s


def _significant(canonical: str) -> bool:
    """검사 대상인가 — %거나, 소수거나, 정수값 >=10. bare 0~9 는 흔한 파생 카운트라 skip."""
    if canonical.endswith("%") or "." in canonical:
        return True
    try:
        return int(canonical) >= 10
    except ValueError:
        return False


def _numbers(text: str) -> list[str]:
    """텍스트에서 숫자 토큰 추출(버전 토큰 선제거)."""
    cleaned = _VERSION.sub(" ", text or "")
    return _NUM.findall(cleaned)


def validate_numbers(
    answer_text: str, evidence_text: str, query: str = ""
) -> NumberReport:
    """답변의 유의미한 숫자를 evidence+query 의 숫자와 값-대조. 순수·무예외."""
    grounding: set[str] = set()
    for t in _numbers(evidence_text) + _numbers(query):
        grounding.add(_canonical(t))

    seen: set[str] = set()
    checks: list[NumberCheck] = []
    for t in _numbers(answer_text):
        c = _canonical(t)
        if not _significant(c) or c in seen:
            continue
        seen.add(c)
        checks.append(NumberCheck(value=t, grounded=c in grounding))

    unverified = sum(1 for n in checks if not n.grounded)
    return NumberReport(numbers=checks, unverified_count=unverified)
