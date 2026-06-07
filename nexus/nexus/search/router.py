"""Query Route 판별 (규칙 기반).

쿼리 유형에 따라 검색 경로를 결정한다.
LLM이 아닌 deterministic 규칙으로 판별.
"""

from __future__ import annotations

import re

import structlog

logger = structlog.get_logger(__name__)


def determine_route(
    query: str,
    requested_route: str = "auto",
    entity_names: list[str] | None = None,
) -> str:
    """쿼리 분석 후 최적 검색 경로 결정.

    Routes:
    - hybrid_only: BM25 + Vector만 사용
    - hybrid_then_graph: Hybrid 후 graph 보강
    - graph_then_hybrid: Graph 우선, hybrid 보완

    Args:
        query: 사용자 쿼리
        requested_route: 사용자 지정 경로 (auto면 자동 판별)
        entity_names: 감지된 엔티티 이름 목록

    Returns:
        검색 경로 문자열
    """
    if requested_route != "auto":
        return requested_route

    # 그래프 관련 키워드
    graph_keywords_ko = ["의존성", "호출", "관계", "연결", "통신", "아키텍처", "토폴로지", "서비스 맵"]
    graph_keywords_en = ["dependency", "call", "relation", "connect", "topology", "architecture"]

    # diff 관련 키워드
    diff_keywords = ["diff", "불일치", "차이", "shadow", "관측", "실제"]

    query_lower = query.lower()

    # 엔티티가 2개 이상 감지되면 graph 우선
    if entity_names and len(entity_names) >= 2:
        return "graph_then_hybrid"

    # 그래프 키워드 감지
    for kw in graph_keywords_ko + graph_keywords_en:
        if kw in query_lower:
            return "hybrid_then_graph"

    # diff 키워드
    for kw in diff_keywords:
        if kw in query_lower:
            return "graph_then_hybrid"

    # 기본: hybrid only
    return "hybrid_only"
