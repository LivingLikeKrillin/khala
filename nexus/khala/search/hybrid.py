"""BM25 + Vector + Graph 3-way 병렬 검색 + RRF Fusion.

모든 검색은 base_filter(tenant, classification, quarantine, status)를 적용한다.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

import structlog

from khala import db
from khala.index.bm25 import tokenize_korean, tokens_to_tsquery
from khala.models.resource import base_filter_sql
from khala.providers.embedding import EmbeddingService
from khala.repositories.graph import (
    GraphRepository,
    SubGraph,
)

logger = structlog.get_logger(__name__)


@dataclass
class SearchHit:
    """검색 결과 항목."""
    rid: str
    doc_rid: str
    doc_title: str = ""
    section_path: str = ""
    source_uri: str = ""
    source_version: str = ""
    snippet: str = ""
    score: float = 0.0
    bm25_rank: int | None = None
    vector_rank: int | None = None
    classification: str = "INTERNAL"


@dataclass
class SearchResult:
    """통합 검색 결과."""
    hits: list[SearchHit] = field(default_factory=list)
    graph: SubGraph | None = None
    route_used: str = ""
    timing_ms: dict = field(default_factory=dict)


async def _bm25_search(
    query: str,
    tenant: str,
    clearance: str,
    top_k: int = 20,
) -> list[tuple[str, int]]:
    """BM25 검색. (chunk_rid, rank) 반환."""
    tokens = tokenize_korean(query)
    tsquery = tokens_to_tsquery(tokens)

    if not tsquery:
        return []

    rows = await db.fetch_all(
        f"""
        SELECT c.rid, ts_rank(c.tsvector_ko, to_tsquery('simple', $1)) as rank_score
        FROM chunks c
        WHERE c.tsvector_ko @@ to_tsquery('simple', $1)
          AND c.tenant = $2
          AND c.classification <= $3::classification_level
          AND c.is_quarantined = false
          AND c.status = 'active'
        ORDER BY rank_score DESC
        LIMIT $4
        """,
        tsquery, tenant, clearance, top_k,
    )

    return [(r["rid"], i + 1) for i, r in enumerate(rows)]


async def _vector_search(
    query: str,
    embedding_svc: EmbeddingService,
    tenant: str,
    clearance: str,
    top_k: int = 20,
) -> list[tuple[str, int]]:
    """Vector 검색. (chunk_rid, rank) 반환."""
    try:
        query_embedding = await embedding_svc.embed_query(query)
    except Exception as e:
        logger.error("vector_search_embedding_failed", error=str(e))
        return []

    vec_str = "[" + ",".join(str(v) for v in query_embedding) + "]"

    rows = await db.fetch_all(
        f"""
        SELECT c.rid, c.embedding <=> $1::vector as distance
        FROM chunks c
        WHERE c.embedding IS NOT NULL
          AND c.tenant = $2
          AND c.classification <= $3::classification_level
          AND c.is_quarantined = false
          AND c.status = 'active'
        ORDER BY distance ASC
        LIMIT $4
        """,
        vec_str, tenant, clearance, top_k,
    )

    return [(r["rid"], i + 1) for i, r in enumerate(rows)]


def _rrf_fusion(
    bm25_results: list[tuple[str, int]],
    vector_results: list[tuple[str, int]],
    k: int = 60,
    final_top_k: int = 10,
) -> list[dict]:
    """RRF (Reciprocal Rank Fusion) 스코어 병합.

    score = Σ 1/(k + rank + 1)
    """
    scores: dict[str, dict] = {}

    for rid, rank in bm25_results:
        if rid not in scores:
            scores[rid] = {"rid": rid, "score": 0.0, "bm25_rank": None, "vector_rank": None}
        scores[rid]["score"] += 1.0 / (k + rank + 1)
        scores[rid]["bm25_rank"] = rank

    for rid, rank in vector_results:
        if rid not in scores:
            scores[rid] = {"rid": rid, "score": 0.0, "bm25_rank": None, "vector_rank": None}
        scores[rid]["score"] += 1.0 / (k + rank + 1)
        scores[rid]["vector_rank"] = rank

    ranked = sorted(scores.values(), key=lambda x: x["score"], reverse=True)
    return ranked[:final_top_k]


async def _enrich_hits(fused: list[dict], tenant: str) -> list[SearchHit]:
    """RRF 결과에 청크 메타데이터를 보강."""
    if not fused:
        return []

    rids = [f["rid"] for f in fused]
    placeholders = ", ".join(f"${i+1}" for i in range(len(rids)))

    rows = await db.fetch_all(
        f"""
        SELECT c.rid, c.doc_rid, c.section_path, c.chunk_text, c.source_uri,
               c.classification, c.source_version,
               d.title as doc_title
        FROM chunks c
        LEFT JOIN documents d ON c.doc_rid = d.rid
        WHERE c.rid IN ({placeholders})
        """,
        *rids,
    )

    row_map = {r["rid"]: r for r in rows}
    hits: list[SearchHit] = []

    for f in fused:
        r = row_map.get(f["rid"])
        if not r:
            continue
        snippet = r["chunk_text"][:300] + "..." if len(r["chunk_text"]) > 300 else r["chunk_text"]
        hits.append(SearchHit(
            rid=f["rid"],
            doc_rid=r["doc_rid"],
            doc_title=r["doc_title"] or "",
            section_path=r["section_path"],
            source_uri=r["source_uri"],
            source_version=r["source_version"] or "",
            snippet=snippet,
            score=f["score"],
            bm25_rank=f["bm25_rank"],
            vector_rank=f["vector_rank"],
            classification=r["classification"],
        ))

    return hits


async def hybrid_search(
    query: str,
    tenant: str = "default",
    clearance: str = "INTERNAL",
    top_k: int = 10,
    embedding_svc: EmbeddingService | None = None,
    graph_repo: GraphRepository | None = None,
    route: str = "hybrid_only",
    entity_rids: list[str] | None = None,
    config: dict | None = None,
) -> SearchResult:
    """3-way Hybrid 검색 실행.

    Args:
        query: 검색 쿼리
        tenant: 테넌트
        clearance: 사용자 보안 등급
        top_k: 최종 반환 수
        embedding_svc: EmbeddingService (없으면 BM25만)
        graph_repo: GraphRepository (graph 경로 시 사용)
        route: 검색 경로
        entity_rids: 감지된 엔티티 rid 목록 (graph 검색용)
        config: config.yaml 설정

    Returns:
        SearchResult
    """
    import time
    start = time.time()
    cfg = config or {}
    search_cfg = cfg.get("search", {})
    bm25_top_k = search_cfg.get("bm25_top_k", 20)
    vector_top_k = search_cfg.get("vector_top_k", 20)
    rrf_k = search_cfg.get("rrf_k", 60)

    result = SearchResult(route_used=route)

    # BM25 + Vector 병렬 실행
    bm25_task = asyncio.create_task(_bm25_search(query, tenant, clearance, bm25_top_k))

    vector_results: list[tuple[str, int]] = []
    if embedding_svc:
        vector_task = asyncio.create_task(
            _vector_search(query, embedding_svc, tenant, clearance, vector_top_k)
        )
        bm25_results, vector_results = await asyncio.gather(bm25_task, vector_task)
    else:
        bm25_results = await bm25_task

    bm25_ms = int((time.time() - start) * 1000)

    # RRF Fusion
    fused = _rrf_fusion(bm25_results, vector_results, k=rrf_k, final_top_k=top_k)

    # 메타데이터 보강
    result.hits = await _enrich_hits(fused, tenant)

    # Graph 보강 (route에 따라)
    if graph_repo and entity_rids and route in ("hybrid_then_graph", "graph_then_hybrid"):
        try:
            # 첫 번째 엔티티 기준으로 서브그래프 조회
            graph = await graph_repo.get_neighbors(entity_rids[0], hops=2)
            result.graph = graph
        except Exception as e:
            logger.warning("graph_search_failed", error=str(e))

    total_ms = int((time.time() - start) * 1000)
    result.timing_ms = {"total_ms": total_ms, "bm25_ms": bm25_ms}

    logger.info("hybrid_search_complete",
                hits=len(result.hits),
                route=route,
                total_ms=total_ms)

    return result
