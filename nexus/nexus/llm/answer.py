"""LLMService 호출 + 근거 기반 답변 생성.

Evidence packet을 LLM에 전달하여 근거 기반 답변을 생성한다.
LLM 실패 시에도 evidence snippet은 그대로 제공한다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

import structlog

from nexus.documents.staleness import annotate_staleness
from nexus.llm.failure import classify as classify_failure
from nexus.llm.citations import validate_citations
from nexus.llm.numbers import validate_numbers
from nexus.llm.prompts import build_prompts
from nexus.providers.llm import LLMService
from nexus.search.anchor_status import summarize
from nexus.search.doc_debt import summarize as summarize_debt
from nexus.search.evidence_packet import EvidencePacket, format_for_llm

logger = structlog.get_logger(__name__)


def _load_staleness_ttl() -> dict:
    """config.yaml 의 staleness.ttl_days. 부재/오류 시 {} + 경고 로그(조용한 비활성 방지)."""
    try:
        import yaml
        from pathlib import Path

        cfg = yaml.safe_load(Path("config.yaml").read_text(encoding="utf-8")) or {}
        ttl = (cfg.get("staleness") or {}).get("ttl_days")
        if isinstance(ttl, dict):
            return ttl
        logger.warning("staleness_ttl_missing", detail="staleness.ttl_days 부재 — 신선도 판정 비활성")
        return {}
    except Exception as e:
        logger.warning("staleness_ttl_load_failed", error=str(e))
        return {}


@dataclass
class AnswerResult:
    """답변 결과."""
    answer: str = ""
    evidence_snippets: list[dict] = field(default_factory=list)
    #: 근거 문서에 붙은 결정론적 부채(supersede·제목 중복). 없으면 None.
    doc_debts: list[dict] | None = None
    graph_findings: dict | None = None
    provenance: list[dict] = field(default_factory=list)
    route_used: str = ""
    timing_ms: dict = field(default_factory=dict)
    llm_failed: bool = False
    #: **왜** 실패했는가 (`nexus.llm.failure` 의 안정 코드) — 실패했을 때만 채워진다.
    #: 불리언 하나만으로는 "기다리면 되는 실패" 와 "사람이 결제해야 하는 실패" 가 구별되지
    #: 않고, 2026-08-13 슬랙 파일럿에서 크레딧 소진에 대고 "잠시 후 다시 시도" 라고 답했다.
    llm_failure_reason: str | None = None
    # 인용 사후검증(SPEC-nexus-citation-validation): 각 [출처: …] 가 근거 packet 에 실재하는가.
    citations: list[dict] = field(default_factory=list)
    unverified_citations: int = 0
    # 숫자 근거검증(SPEC-nexus-answer-number-verification): 답변의 유의미 숫자가 근거+질의에 실재하는가.
    numbers: list[dict] = field(default_factory=list)
    unverified_numbers: int = 0
    # LLM 토큰/비용(SPEC-nexus-llm-usage-capture): {input_tokens, output_tokens, cost_usd, model} | None.
    usage: dict | None = None
    # 근거 신선도(SPEC-nexus-answer-staleness-warning): TTL 초과 근거 개수. 스니펫별 staleness 는 evidence_snippets 에.
    n_stale: int = 0
    # 기권 — **코드가 내리는 판단**이지 답변 문장에서 읽어내는 것이 아니다.
    #
    # 기권은 이미 있었다: 근거가 하나도 없으면 LLM 을 부르지 않고 정해진 문장을 돌려준다. 그런데
    # 그 사실이 **문장 안에만** 있어서 기계가 읽을 수 없었다 — 한국어 문자열 대조 말고는. 그래서
    # 평가 라벨의 '답변불가' 5건이 어느 집계에도 안 들어갔다(KOREAN_SEARCH_QUALITY.md §2.3:
    # "Nexus 에 기권 기제가 없어 잴 것이 없다").
    #
    # **여기서 새 문턱을 만들지 않는다.** "점수가 낮으면 기권" 같은 규칙은 재보지 않은 숫자를
    # 게이트로 굳히는 짓이고, 이 리포는 그 실수를 오늘 세 번 했다. 드러내는 것은 이미 코드가
    # 내리고 있던 판단 하나뿐이다.
    abstained: bool = False
    abstain_reason: str = ""        # "" | "no_evidence"


def _shown_query(query: str, user_query: str | None) -> str:
    """모델이 **질의 자리에서 실제로 본** 텍스트. 숫자 근거검증의 대조 대상이다.

    검증기는 "LLM 이 본 것에 있는가" 를 묻는다(`nexus/llm/numbers.py`). U2 로 원문이 프롬프트에
    들어갔는데 이 대조 대상이 재작성 질의뿐이면, **사용자가 직접 쓴 숫자**("상위 25개만")를
    답변이 되풀이했다는 이유로 무근거 배지가 뜬다. 그것은 검증기의 완화가 아니라 사실 반영이다.
    """
    if user_query is None or user_query == query:
        return query
    return f"{query}\n{user_query}"


async def generate_answer(
    query: str,
    packet: EvidencePacket,
    llm_svc: LLMService,
    route_used: str = "",
    timing_ms: dict | None = None,
    user_query: str | None = None,
) -> AnswerResult:
    """근거 기반 답변 생성.

    Args:
        query: 검색에 사용한 질의 — 멀티턴에서는 재작성된 문장이다
        packet: Evidence packet (snippets + graph + provenance)
        llm_svc: LLMService 인스턴스
        route_used: 사용된 검색 경로
        timing_ms: 검색 타이밍 정보
        user_query: 사용자가 **실제로 친 문장**(`req.query` 그대로). `query` 와 같거나 None 이면
            프롬프트는 오늘과 바이트 단위로 같다 (SPEC-nexus-multi-turn-narration §4 I1·I3).

    Returns:
        AnswerResult
    """
    result = AnswerResult(
        route_used=route_used,
        timing_ms=timing_ms or {},
    )

    # Evidence snippets 변환 (updated_at 은 신선도 판정용 datetime 으로 넣었다가 아래서 판정 후 ISO 직렬화)
    snippets = [
        {
            "chunk_rid": s.chunk_rid,
            "doc_title": s.doc_title,
            "section_path": s.section_path,
            "source_uri": s.source_uri,
            "text": s.text,
            "score": s.score,
            "doc_type": s.doc_type,  # 축-A 타입(S3) — 웹 클라이언트 타입 배지용
            # 등급은 응답까지 간다 (ADR-0010 hop 5) — 배지를 달 수 있어야 한다.
            "provenance_tier": getattr(s, "provenance_tier", "authored"),
            # 이 문단이 부른 코드 이름의 현재 상태. 앵커가 없으면 `None` 이고, 그때 응답은
            # 오늘과 같은 모양이다. 표현계층이 셈을 다시 하지 않도록 **여기서 요약해** 보낸다.
            "code_anchors": summarize(getattr(s, "code_anchors", []),
                                      getattr(s, "code_deleted", [])),
            "updated_at": s.updated_at,
        }
        for s in packet.snippets
    ]
    # 근거 신선도 판정(결정론) — TTL 초과 근거를 스니펫별 staleness + 답변레벨 n_stale 로.
    snippets, result.n_stale = annotate_staleness(
        snippets, datetime.now(timezone.utc), _load_staleness_ttl())
    for sn in snippets:                      # datetime → ISO 문자열(응답 직렬화용)
        _ua = sn.get("updated_at")
        sn["updated_at"] = _ua.isoformat() if _ua else None
    result.evidence_snippets = snippets

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

    # 근거 문서 부채 — 응답까지 간다(표현계층이 배지를 달 수 있어야 한다).
    result.doc_debts = summarize_debt(getattr(packet, "debts", []))

    # Provenance (source_version 포함)
    result.provenance = [
        {
            "doc_rid": p.doc_rid,
            "source_uri": p.source_uri,
            "source_version": p.source_version,
            "approved_hash": p.approved_hash,
        }
        for p in packet.provenance
    ]

    # LLM 호출
    if not packet.snippets:
        result.answer = "제공된 문서에서 해당 정보를 찾을 수 없습니다."
        result.abstained, result.abstain_reason = True, "no_evidence"
        return result

    evidence_text = format_for_llm(packet)
    system_prompt, user_prompt = build_prompts(query, evidence_text, user_query)

    try:
        import time
        llm_start = time.time()
        llm_result = await llm_svc.generate_full(system_prompt, user_prompt)
        result.answer = llm_result.text
        _u = llm_result.usage
        result.usage = {"input_tokens": _u.input_tokens, "output_tokens": _u.output_tokens,
                        "cost_usd": _u.cost_usd, "model": _u.model}
        result.timing_ms["llm_ms"] = int((time.time() - llm_start) * 1000)
        # 인용 검증 — LLM 이 준 답을 packet 과 대조(코드가 판정, LLM 을 신뢰하지 않음).
        report = validate_citations(result.answer, packet)
        result.citations = [
            {"title": c.title, "section": c.section, "verified": c.verified,
             "provenance_tier": getattr(c, "provenance_tier", "authored")}
            for c in report.citations
        ]
        result.unverified_citations = report.unverified_count
        # 숫자 근거검증 — 답변의 유의미 숫자가 LLM 이 본 것(evidence_text + query)에 실재하는가.
        nreport = validate_numbers(result.answer, evidence_text, _shown_query(query, user_query))
        result.numbers = [
            {"value": n.value, "grounded": n.grounded} for n in nreport.numbers
        ]
        result.unverified_numbers = nreport.unverified_count
    except Exception as e:
        # 예외는 **여기서만** 분류한다. 이 자리를 지나면 남는 것은 문자열뿐이고, 문자열은
        # 공급자가 바꾼다 (nexus/llm/failure.py).
        result.llm_failure_reason = classify_failure(e)
        logger.error("llm_generation_failed", error=str(e), reason=result.llm_failure_reason)
        result.llm_failed = True
        result.answer = (
            "답변을 생성할 수 없습니다. 아래 근거를 직접 확인해주세요.\n\n"
            + evidence_text
        )

    return result
