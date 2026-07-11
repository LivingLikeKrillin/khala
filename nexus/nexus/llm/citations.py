"""인용 사후검증 — SPEC-nexus-citation-validation.

LLM 이 뱉은 `[출처: 문서 제목, 섹션]` 인용을, LLM 에게 실제로 보여준 근거 스니펫 제목과 대조한다.
"System decides, LLM narrates": 인용이 실재하는지는 시스템이 판정하고, LLM 은 제안만 한다.

순수 함수(I/O 없음). 존재하지 않는 출처(packet 에 없던 제목)를 잡는다 — 실재하는 제목을 잘못된
주장에 붙인 것(entailment)은 범위 밖.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# [출처: ... ] — 닫는 대괄호까지. 안 닫히면 매치 안 됨(무시 → 크래시 금지).
_CITE = re.compile(r"\[출처:\s*([^\]]+?)\s*\]")


@dataclass(frozen=True)
class Citation:
    title: str
    section: str
    verified: bool


@dataclass(frozen=True)
class CitationReport:
    citations: list[Citation]
    unverified_count: int


def _norm(s: str) -> str:
    """공백 축약 + trim + 소문자 — 표면 차이로 인한 오탐 방지."""
    return re.sub(r"\s+", " ", s.strip()).lower()


def _classify(inner: str, known: dict[str, str]) -> Citation:
    """인용 안쪽 텍스트를 (title, section, verified) 로 분류.

    제목에 콤마가 있을 수 있으므로(Notion 페이지·파일명) 첫 콤마로 순진하게 자르지 않는다:
    전체를 제목으로 먼저 시도하고, 아니면 콤마 분할점을 뒤에서부터(긴 제목 우선) 훑어
    앞부분이 알려진 제목과 정확히 일치하면 verified + 뒷부분을 섹션으로.
    """
    innorm = _norm(inner)
    if innorm in known:                       # 전체가 제목(섹션 없음, 제목에 콤마 포함 가능)
        return Citation(title=known[innorm], section="", verified=True)
    parts = inner.split(",")
    for i in range(len(parts) - 1, 0, -1):    # 긴 제목 우선(제목 안 콤마 흡수)
        title_part = ",".join(parts[:i]).strip()
        section_part = ",".join(parts[i:]).strip()
        tnorm = _norm(title_part)
        if tnorm in known:
            return Citation(title=known[tnorm], section=section_part, verified=True)
    return Citation(title=inner, section="", verified=False)   # packet 에 없는 출처


def validate_citations(answer_text: str, packet) -> CitationReport:
    """답변의 모든 [출처: …] 를 packet.snippets 제목과 대조. 순수·무예외."""
    known = {_norm(s.doc_title): s.doc_title
             for s in getattr(packet, "snippets", []) if getattr(s, "doc_title", "")}
    citations = [_classify(m.group(1), known) for m in _CITE.finditer(answer_text or "")]
    unverified = sum(1 for c in citations if not c.verified)
    return CitationReport(citations=citations, unverified_count=unverified)
