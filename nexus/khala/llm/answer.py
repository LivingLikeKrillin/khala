"""LLMService 호출 + 근거 기반 답변 생성.

Evidence packet을 LLM에 전달하여 근거 기반 답변을 생성한다.
LLM 실패 시에도 evidence snippet은 그대로 제공한다.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import structlog

from khala.llm.prompts import SYSTEM_PROMPT, build_user_prompt
from khala.providers.llm import LLMService
from khala.search.evidence_packet import EvidencePacket, format_for_llm

logger = structlog.get_logger(__name__)


@dataclass
class AnswerResult:
    """답변 결과."""
    answer: str = ""
    evidence_snippets: list[dict] = field(default_factory=list)
    graph_findings: dict | None = None
    provenance: list[dict] = field(default_factory=list)
    route_used: str = ""
    timing_ms: dict = field(default_factory=dict)
    llm_failed: bool = False


async def generate_answer(
    query: str,
    packet: EvidencePacket,
    llm_svc: LLMService,
    route_used: str = "",
    timing_ms: dict | None = None,
) -> AnswerResult:
    """근거 기반 답변 생성.

    Args:
        query: 사용자 질문
        packet: Evidence packet (snippets + graph + provenance)
        llm_svc: LLMService 인스턴스
        route_used: 사용된 검색 경로
        timing_ms: 검색 타이밍 정보

    Returns:
        AnswerResult
    """
    result = AnswerResult(
        route_used=route_used,
        timing_ms=timing_ms or {},
    )

    # Evidence snippets 변환
    result.evidence_snippets = [
        {
            "chunk_rid": s.chunk_rid,
            "doc_title": s.doc_title,
            "section_path": s.section_path,
            "source_uri": s.source_uri,
            "text": s.text,
            "score": s.score,
        }
        for s in packet.snippets
    ]

    # Graph findings 변환 (diff_flags 포함)
    if packet.graph:
        result.graph_findings = {
            "center": packet.graph.center_name,
            "designed_edges": [
                {"type": e.edge_type, "from": e.from_name, "to": e.to_name,
                 "confidence": e.confidence, "source_category": e.source_category}
                for e in packet.graph.edges
            ],
            "observed_edges": [
                {"type": o.edge_type, "from": o.from_name, "to": o.to_name,
                 "calls": o.call_count, "error_rate": o.error_rate,
                 "latency_p95": o.latency_p95, "trace_query_ref": o.trace_query_ref}
                for o in packet.graph.observed_edges
            ],
        }

    # Provenance (source_version 포함)
    result.provenance = [
        {
            "doc_rid": p.doc_rid,
            "source_uri": p.source_uri,
            "source_version": p.source_version,
        }
        for p in packet.provenance
    ]

    # LLM 호출
    if not packet.snippets:
        result.answer = "제공된 문서에서 해당 정보를 찾을 수 없습니다."
        return result

    evidence_text = format_for_llm(packet)
    user_prompt = build_user_prompt(query, evidence_text)

    try:
        import time
        llm_start = time.time()
        result.answer = await llm_svc.generate(SYSTEM_PROMPT, user_prompt)
        result.timing_ms["llm_ms"] = int((time.time() - llm_start) * 1000)
    except Exception as e:
        logger.error("llm_generation_failed", error=str(e))
        result.llm_failed = True
        result.answer = (
            "답변을 생성할 수 없습니다. 아래 근거를 직접 확인해주세요.\n\n"
            + evidence_text
        )

    return result
