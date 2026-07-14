"""BM25 + Vector + Graph 3-way 병렬 검색 + RRF Fusion.

모든 검색은 base_filter(tenant, classification, quarantine, status)를 적용한다.
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass, field
from datetime import datetime

import structlog

from nexus import db
from nexus.index.bm25 import tokenize_korean, tokens_to_tsquery
from nexus.providers.embedding import EmbeddingService
from nexus.repositories.graph import (
    EdgeResult,
    GraphRepository,
    ObservedEdgeResult,
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
    approved_hash: str = ""  # documents.approved_hash — accountable-review stamp (SPEC §5.4)
    doc_type: str = ""  # documents.doc_type — 축-A 타입(S3 intake 보존)
    updated_at: datetime | None = None  # documents.updated_at — 신선도 판정용(SPEC-nexus-answer-staleness-warning)


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
        """
        SELECT c.rid, ts_rank_cd(c.tsvector_ko, to_tsquery('simple', $1)) as rank_score
        FROM chunks c
        WHERE c.tsvector_ko @@ to_tsquery('simple', $1)
          AND c.tenant = $2
          AND c.classification <= $3::classification_level
          AND c.is_quarantined = false
          AND c.status = 'active'
          AND EXISTS (SELECT 1 FROM documents d
                      WHERE d.rid = c.doc_rid AND d.status = 'active')
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
        """
        SELECT c.rid, c.embedding <=> $1::vector as distance
        FROM chunks c
        WHERE c.embedding IS NOT NULL
          AND c.tenant = $2
          AND c.classification <= $3::classification_level
          AND c.is_quarantined = false
          AND c.status = 'active'
          AND EXISTS (SELECT 1 FROM documents d
                      WHERE d.rid = c.doc_rid AND d.status = 'active')
        ORDER BY distance ASC
        LIMIT $4
        """,
        vec_str, tenant, clearance, top_k,
    )

    return [(r["rid"], i + 1) for i, r in enumerate(rows)]


class UnknownRoute(ValueError):
    """호출자가 존재하지 않는 route 를 골랐다. 우리 잘못이 아니므로 400 이다.

    맨 ValueError 를 400 으로 바꾸면 내부 버그의 ValueError 까지 "당신 잘못" 이 된다.
    """


#: route → (BM25 다리를 도는가, 벡터 다리를 도는가). 그래프 보강은 아래에서 따로 판정한다.
#: SPEC-nexus-search-recall §4.2 — 이 표가 API·MCP·CLI 가 광고하는 계약의 정본이다.
ROUTES: dict[str, tuple[bool, bool]] = {
    "keyword_only": (True, False),
    "vector_only": (False, True),
    "hybrid_only": (True, True),
    "hybrid_then_graph": (True, True),
    "graph_then_hybrid": (True, True),
}


def _rrf_fusion(
    bm25_results: list[tuple[str, int]],
    vector_results: list[tuple[str, int]],
    k: int = 60,
) -> list[dict]:
    """RRF (Reciprocal Rank Fusion) 스코어 병합. 전체 병합 리스트를 RRF 순서로 반환(컷 없음).

    top_k 컷은 문서 다양성(_diversify) 이후로 미룬다 — 한 문서가 top-k 를 도배하지 않도록.
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

    return sorted(scores.values(), key=lambda x: x["score"], reverse=True)


def _diversify(hits: list, top_k: int, per_doc_cap: int) -> list:
    """문서별 상한(per_doc_cap)으로 top-k 를 재정렬 — 한 문서가 도배하지 못하게.

    RRF 순서를 돌며 상한 이내인 hit 을 담고, 문서가 부족해 top_k 를 못 채우면 넘긴 hit 으로
    채운다. 항상 min(top_k, len(hits)) 개를 돌려준다(recall 안전, 빈 결과 만들지 않음). 문서
    내부 순서는 RRF 순서를 유지한다. 반환 순서 = 다양화된 랭킹(순수 score 정렬 아님, SPEC §4.2).
    """
    selected: list = []
    skipped: list = []
    counts: dict[str, int] = {}
    for h in hits:
        if len(selected) < top_k and counts.get(h.doc_rid, 0) < per_doc_cap:
            selected.append(h)
            counts[h.doc_rid] = counts.get(h.doc_rid, 0) + 1
        else:
            skipped.append(h)
    for h in skipped:                      # 문서 부족 시 채워서 count 복구
        if len(selected) >= top_k:
            break
        selected.append(h)
    return selected


def _merge_subgraphs(subgraphs: list[SubGraph]) -> SubGraph | None:
    """여러 엔티티 중심 서브그래프를 하나로 병합.

    쿼리에서 엔티티가 여럿 감지되면 각각에서 이웃을 펼친 뒤 합친다.
    - center는 첫 서브그래프 기준 (표시 연속성 + 하위 호환: result.graph는 단일 SubGraph)
    - edge/observed_edge는 rid로 dedup. edge가 여러 탐색에서 중복되면 hop이
      작은 쪽(더 가까운 관계)을 유지한다.

    Args:
        subgraphs: 엔티티별 get_neighbors 결과 (None은 무시)

    Returns:
        병합된 단일 SubGraph. 입력이 비면 None.
    """
    merged = [sg for sg in subgraphs if sg is not None]
    if not merged:
        return None

    primary = merged[0]
    edges_by_rid: dict[str, EdgeResult] = {}
    observed_by_rid: dict[str, ObservedEdgeResult] = {}

    for sg in merged:
        for e in sg.edges:
            existing = edges_by_rid.get(e.rid)
            if existing is None or e.hop < existing.hop:
                edges_by_rid[e.rid] = e
        for o in sg.observed_edges:
            observed_by_rid[o.rid] = o

    return SubGraph(
        center_rid=primary.center_rid,
        center_name=primary.center_name,
        edges=list(edges_by_rid.values()),
        observed_edges=list(observed_by_rid.values()),
    )


# 진짜 문장 종결: 종결부호(+뒤따르는 닫는 인용/괄호) 뒤에 공백/끝. 숫자 사이 마침표(3.14)는 제외.
_SENT_RE = re.compile(r'[.!?。]["\')\]」』]*(?=\s|$)')


def _truncate_snippet(text: str, max_chars: int) -> str:
    """근거 스니펫을 경계에서 자른다 — 단어/문장 중간 안 자름(SPEC-nexus-snippet-boundary-truncation).

    이 스니펫은 dual-mode: LLM 프롬프트 + 사람 표면(웹/Slack/API) 양쪽이 본다.
    """
    if len(text) <= max_chars:
        return text
    window = text[:max_chars]
    # 1) 후반부(>=0.7*max)의 마지막 진짜 문장 종결 — 내용 손실 최소.
    best = -1
    for m in _SENT_RE.finditer(window):
        best = m.end()
    if best >= max_chars * 0.7:
        return text[:best].rstrip() + " …"
    # 2) 단어 경계(마지막 공백) — 내용 최대 보존, 단어 안 자름.
    sp = window.rfind(" ")
    if sp > 0:
        return text[:sp].rstrip() + " …"
    # 3) 최후: 하드컷(공백 없는 긴 토큰) — 오늘과 동일, 드묾.
    return window.rstrip() + " …"


async def _enrich_hits(
    fused: list[dict], tenant: str, max_snippet_chars: int = 300,
) -> list[SearchHit]:
    """RRF 결과에 청크 메타데이터를 보강."""
    if not fused:
        return []

    rids = [f["rid"] for f in fused]
    placeholders = ", ".join(f"${i+1}" for i in range(len(rids)))

    rows = await db.fetch_all(
        f"""
        SELECT c.rid, c.doc_rid, c.section_path, c.chunk_text, c.source_uri,
               c.classification, c.source_version,
               d.title as doc_title, d.approved_hash as approved_hash,
               d.doc_type as doc_type, d.updated_at as updated_at
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
        snippet = _truncate_snippet(r["chunk_text"], max_snippet_chars)
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
            approved_hash=r["approved_hash"] or "",
            doc_type=r["doc_type"] or "",
            updated_at=r["updated_at"],
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

    if route not in ROUTES:
        # 조용히 hybrid 로 처리하지 않는다. "당신의 route 는 무시됐다" 는 말이 아무 말보다 낫다.
        raise UnknownRoute(f"unknown_route: {route!r}. 가능한 값: {', '.join(sorted(ROUTES))}")

    result = SearchResult(route_used=route)

    # route 가 고르는 것은 그래프 보강만이 아니다 — 어느 **다리**를 돌릴지도 고른다.
    # 예전엔 둘 다 무조건 돌면서 route_used 로 "반영됐다" 고 보고했다.
    use_bm25, use_vector = ROUTES[route]

    bm25_results: list[tuple[str, int]] = []
    vector_results: list[tuple[str, int]] = []

    tasks = {}
    if use_bm25:
        tasks["bm25"] = asyncio.create_task(_bm25_search(query, tenant, clearance, bm25_top_k))
    # embedding_svc 가 없으면 벡터 다리는 못 돈다. 그렇다고 BM25 로 슬그머니 바꿔치기하고
    # route_used='vector_only' 라 보고하지는 않는다 — 빈 결과가 정직하다.
    if use_vector and embedding_svc:
        tasks["vector"] = asyncio.create_task(
            _vector_search(query, embedding_svc, tenant, clearance, vector_top_k))

    if tasks:
        done = dict(zip(tasks, await asyncio.gather(*tasks.values())))
        bm25_results = done.get("bm25", [])
        vector_results = done.get("vector", [])

    bm25_ms = int((time.time() - start) * 1000)

    # RRF Fusion (전체 병합, 컷은 다양성 이후)
    fused = _rrf_fusion(bm25_results, vector_results, k=rrf_k)

    # 메타데이터 보강 (fused 순서 보존)
    enriched = await _enrich_hits(
        fused, tenant, max_snippet_chars=search_cfg.get("snippet_max_chars", 300))

    # 문서 다양성 + top_k 컷 — 한 문서가 결과를 도배하지 않게.
    per_doc_cap = search_cfg.get("diversity_per_doc_cap", 3)
    result.hits = _diversify(enriched, top_k, per_doc_cap)

    # Graph 보강 (route에 따라)
    if graph_repo and entity_rids and route in ("hybrid_then_graph", "graph_then_hybrid"):
        graph_hops = search_cfg.get("graph_hops", 2)
        max_entities = search_cfg.get("graph_max_entities", 5)
        targets = entity_rids[:max_entities]  # 비용 상한
        try:
            # 감지된 모든 엔티티에서 병렬로 이웃 조회 후 병합
            subgraphs = await asyncio.gather(
                *[graph_repo.get_neighbors(rid, hops=graph_hops, tenant=tenant, clearance=clearance)
                  for rid in targets],
                return_exceptions=True,
            )
            ok: list[SubGraph] = []
            for rid, sg in zip(targets, subgraphs):
                if isinstance(sg, SubGraph):
                    ok.append(sg)
                else:
                    logger.warning("graph_search_partial_failed",
                                   entity_rid=rid, error=str(sg))
            result.graph = _merge_subgraphs(ok)
        except Exception as e:
            logger.warning("graph_search_failed", error=str(e))

    total_ms = int((time.time() - start) * 1000)
    result.timing_ms = {"total_ms": total_ms, "bm25_ms": bm25_ms}

    logger.info("hybrid_search_complete",
                hits=len(result.hits),
                route=route,
                total_ms=total_ms)

    return result
