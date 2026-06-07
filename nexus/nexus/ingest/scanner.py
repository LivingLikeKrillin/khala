"""PII/Secret 스캐너.

config.yaml의 pii_patterns을 사용하여 민감 정보를 감지한다.
감지 시 즉시 quarantine 처리. 절대 chunk 생성 금지.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class ScanResult:
    """스캔 결과."""
    has_pii: bool = False
    pii_types: list[str] = field(default_factory=list)
    matches: list[dict] = field(default_factory=list)


# 신용카드 Luhn 검증
def _luhn_check(number: str) -> bool:
    """Luhn 알고리즘으로 신용카드 번호 검증."""
    digits = [int(d) for d in number if d.isdigit()]
    if len(digits) != 16:
        return False
    checksum = 0
    for i, d in enumerate(reversed(digits)):
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        checksum += d
    return checksum % 10 == 0


def scan_content(content: str, pii_patterns: dict[str, str]) -> ScanResult:
    """텍스트에서 PII/Secret 패턴 검사.

    Args:
        content: 검사할 텍스트
        pii_patterns: config.yaml에서 로드된 패턴 딕셔너리

    Returns:
        ScanResult with detected PII types
    """
    result = ScanResult()

    for pii_type, pattern in pii_patterns.items():
        try:
            matches = re.findall(pattern, content)
        except re.error as e:
            logger.warning("invalid_pii_pattern", pii_type=pii_type, error=str(e))
            continue

        if not matches:
            continue

        # 신용카드 번호는 Luhn 검증 추가
        if pii_type == "credit_card":
            matches = [m for m in matches if _luhn_check(m)]
            if not matches:
                continue

        result.has_pii = True
        result.pii_types.append(pii_type)
        result.matches.append({"type": pii_type, "count": len(matches)})
        logger.warning("pii_detected", pii_type=pii_type, count=len(matches))

    return result
