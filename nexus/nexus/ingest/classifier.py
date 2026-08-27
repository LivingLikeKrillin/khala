"""Classification 규칙 엔진.

분류 순서: PII 스캔 → 경로 규칙 → 확장자 규칙 → frontmatter → 기본값(INTERNAL).
LLM으로 classification을 결정하지 않는다. 이것은 deterministic 규칙이다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from fnmatch import fnmatch
from pathlib import Path

import structlog

from nexus.ingest.scanner import ScanResult, scan_content

logger = structlog.get_logger(__name__)


@dataclass
class ClassificationResult:
    """분류 결과."""
    classification: str = "INTERNAL"
    doc_type: str = "markdown"
    language: str = "ko"
    is_quarantined: bool = False
    quarantine_reason: str = ""
    pii_types: list[str] = field(default_factory=list)


def _detect_language(text: str) -> str:
    """간단한 한국어/영어 비율 판별."""
    if not text:
        return "ko"
    korean_chars = len(re.findall(r"[\uac00-\ud7af]", text))
    total_alpha = len(re.findall(r"[a-zA-Z\uac00-\ud7af]", text))
    if total_alpha == 0:
        return "ko"
    ratio = korean_chars / total_alpha
    if ratio > 0.5:
        return "ko"
    elif ratio < 0.1:
        return "en"
    return "mixed"


def _detect_doc_type(relative_path: str, frontmatter: dict) -> str:
    """문서 유형 판별."""
    if fm_type := frontmatter.get("doc_type"):
        return fm_type

    path_lower = relative_path.lower()
    if "api" in path_lower or "contract" in path_lower:
        return "api_spec"
    if "pipeline" in path_lower or "spec" in path_lower:
        return "spec"
    if "design" in path_lower or "architecture" in path_lower:
        return "design_doc"
    if "policy" in path_lower or "security" in path_lower:
        return "policy"
    if "config" in path_lower:
        return "config"
    return "markdown"


def classify(
    relative_path: str,
    content: str,
    frontmatter: dict,
    config: dict,
) -> ClassificationResult:
    """파일을 분류하고 quarantine 여부를 결정한다.

    Args:
        relative_path: 문서 상대 경로
        content: 파일 본문
        frontmatter: YAML frontmatter 딕셔너리
        config: config.yaml 전체 설정

    Returns:
        ClassificationResult
    """
    result = ClassificationResult()

    # 1. PII 스캔 (최우선)
    pii_patterns = config.get("pii_patterns", {})
    scan_result: ScanResult = scan_content(content, pii_patterns)
    if scan_result.has_pii:
        result.is_quarantined = True
        result.quarantine_reason = f"PII detected: {', '.join(scan_result.pii_types)}"
        result.pii_types = scan_result.pii_types
        result.classification = "RESTRICTED"
        logger.warning("file_quarantined", path=relative_path, reason=result.quarantine_reason)
        return result  # quarantine이면 바로 리턴

    # 2. 경로 규칙
    for rule in config.get("path_rules", []):
        if fnmatch(relative_path, rule["pattern"]):
            result.classification = rule["classification"]
            break

    # 3. 확장자 규칙
    ext = Path(relative_path).suffix.lower()
    for rule in config.get("file_type_rules", []):
        if ext in rule["extensions"]:
            # RESTRICTED는 더 높은 등급이므로 기존보다 높을 때만 적용
            if rule["classification"] == "RESTRICTED":
                result.classification = "RESTRICTED"
            break

    # 4. Frontmatter 명시 분류 (기존 RESTRICTED 유지)
    if fm_class := frontmatter.get("classification"):
        fm_upper = fm_class.upper()
        if fm_upper in ("PUBLIC", "INTERNAL", "RESTRICTED"):
            # 규칙이 RESTRICTED로 판정한 것은 frontmatter로 내릴 수 없음
            if result.classification != "RESTRICTED" or fm_upper == "RESTRICTED":
                result.classification = fm_upper

    # 5. 언어 감지
    result.language = _detect_language(content)

    # 6. 문서 유형 감지
    result.doc_type = _detect_doc_type(relative_path, frontmatter)

    return result


def quarantined_chunk_indexes(chunks, pii_patterns: dict) -> set[int]:
    """PII 가 **실제로 들어 있는 청크**의 인덱스.

    **왜 문서가 아니라 청크인가.** 2026-08-28 라이브 실측: 148KB 짜리 설계 plan 이 통째로
    사라져 있었다(2026-08-16 부터, 청크 0건 = 유령). 원인은 자바 테스트의 16자리 사용자 ID
    아홉 개 중 **하나가 우연히 Luhn 을 통과**한 것이었다. 같은 날 다른 문서 하나는 *JWT 를
    가리는 것을 검증하는 테스트 문서*라서 예시 토큰에 걸렸다.

    한 조각 때문에 문서를 통째로 버리면, 걸린 조각이 오검출일 때 **팀 지식이 조용히 사라진다.**
    걸린 조각만 빼면 비밀은 여전히 색인되지 않으면서 나머지 본문은 산다. 청크 텍스트를 그대로
    검사하므로, 경계에 걸쳐 잘린 비밀은 어느 쪽에도 온전히 남지 않는다.
    """
    if not pii_patterns:
        return set()
    from nexus.ingest.scanner import scan_content
    return {i for i, c in enumerate(chunks)
            if scan_content(c.chunk_text, pii_patterns).has_pii}
