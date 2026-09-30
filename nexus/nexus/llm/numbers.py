"""답변 숫자의 근거 대조 — SPEC-nexus-answer-number-verification.

LLM 이 뱉은 답변의 **유의미한 숫자**가, LLM 에게 실제로 보여준 것(evidence + query + 요청자
자료)에 실재하는지 결정론적으로 대조한다. "System decides, LLM narrates": 지어낸 통계는 시스템이
값-일치로 판정하고, LLM 은 서술만 한다. #134(인용 존재검증)의 숫자판.

숫자마다 **어디서 찾았는지**(`found_in`)도 남긴다(2026-09-30). 참/거짓 하나로는 「근거에 있었다」와
「요청자 자료에서 옮겨 적었다」를 못 가르고, 소비자에게 그 둘은 뜻이 다르다. 한 값으로 고르지 않고
목록인 이유: 같은 수가 여러 곳에 있을 수 있고, 순위를 정하면 어느 순위든 무언가를 감춘다.

순수 함수(I/O 없음, 무예외). 값-존재만 본다(단위/의미 아님) — 오탐(무고)보다 미탐(놓침)을
구조적으로 택한다. LLMware evidence_check_numbers 에서 착안, 구현은 독립.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# 버전/IP 등 점 2개 이상 토큰 — 숫자가 아니라 식별자. 추출 전에 제거(양쪽 텍스트 모두).
_VERSION = re.compile(r"\d+(?:\.\d+){2,}")
# 숫자 토큰: 선택적 통화기호 + 정수부 + 선택적 소수 + 인접 % (부호는 안 잡음).
# 정수부는 **천 단위 쉼표가 제자리에 있을 때만** 쉼표를 받는다(`1,000` · `12,500`).
# ⛔ 옛 판 `\d[\d,]*` 는 문장부호 쉼표까지 먹었다(실측 2026-09-27) — `-15,` 가 "15," 로 나갔고
#    (표시만 틀림) `30,40` 을 한 수 3040 으로 읽었다(판정까지 틀림).
_NUM = re.compile(r"[$₩]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?%?")

#: 숫자를 찾을 수 있는 곳과 그 **순서**. 응답의 `found_in` 목록이 이 순서를 따른다.
SOURCES = ("evidence", "query", "context")


@dataclass(frozen=True)
class NumberCheck:
    value: str      # 원래 표면형(표시용): "47%"
    grounded: bool  # 모델에게 보여 준 것 어딘가에 있다 — `found_in` 이 비지 않았다와 같다
    #: 찾은 곳(`SOURCES` 순서). 비면 어디에도 없다 = 지어낸 수.
    found_in: tuple[str, ...] = ()


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
    answer_text: str, evidence_text: str, query: str = "", context: str = ""
) -> NumberReport:
    """답변의 유의미한 숫자를 evidence+query(+요청자 자료)의 숫자와 값-대조. 순수·무예외.

    `context` 는 요청자가 준 자료(`answer_context`)다. 모델에게 **보여 준 것**이므로 대조 범위에
    든다 — 빼면 자료에서 옮겨 적은 수(대상 번호 · 한도)가 「지어낸 수」로 세어져
    `unverified_numbers` 가 뜻을 잃는다. 근거에 있었는지를 따로 묻는 것은 다른 질문이다.
    """
    places = {
        "evidence": {_canonical(t) for t in _numbers(evidence_text)},
        "query": {_canonical(t) for t in _numbers(query)},
        "context": {_canonical(t) for t in _numbers(context)},
    }

    seen: set[str] = set()
    checks: list[NumberCheck] = []
    for t in _numbers(answer_text):
        c = _canonical(t)
        if not _significant(c) or c in seen:
            continue
        seen.add(c)
        found = tuple(s for s in SOURCES if c in places[s])
        checks.append(NumberCheck(value=t, grounded=bool(found), found_in=found))

    unverified = sum(1 for n in checks if not n.grounded)
    return NumberReport(numbers=checks, unverified_count=unverified)


def number_items(report: NumberReport) -> list[dict]:
    """응답의 `numbers` 항목. **두 답변 표면이 이 함수 하나로 만든다** — 표면마다 식을 적으면
    한쪽에만 칸이 붙고, 그 조합은 검사가 초록인 채로 조용히 갈린다(A44)."""
    return [{"value": n.value, "grounded": n.grounded, "found_in": list(n.found_in)}
            for n in report.numbers]
