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
from nexus.index.bm25 import active_tokenizer, tokens_to_tsquery
from nexus.index.vector_index import (
    UnknownVectorColumn,
    configured_column,
    resolve_column,
)
from nexus.providers.embedding import EmbeddingService, WrongVectorDimensions
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
    #: 사람이 보는 미리보기 — 경계에서 자른 짧은 조각. 웹·Slack·API 가 그대로 쓴다.
    snippet: str = ""
    #: **LLM 근거용 청크 전문.** 사람 미리보기와 갈라 둔다: 300자는 화면엔 알맞지만 프롬프트엔
    #: 답을 잘라먹는 값이다. 2026-08-08 에 846자짜리 권한 표가 앞 300자만 넘어가, 모델이
    #: "표가 중간에 잘려 있다" 고 정확히 말하고 답을 못 했다. 검색은 그 청크를 1위로 뽑았고
    #: 문서 단위 Recall@10 은 1.000 이었다 — 검색만 재는 자에는 안 보이던 구간이다.
    chunk_text: str = ""
    #: 이 청크가 속한 문서가 담은 이미지 수. 신호원이지 랭킹 입력이 아니다 — 그림에 갇힌
    #: 내용 때문에 답을 못 내는 비율을 재려면 근거가 어디서 왔는지 알아야 한다 (migration 011).
    doc_n_images: int = 0
    #: 이 텍스트가 어떻게 존재하게 됐는가 (ADR-0010). 'authored' | 'machine_read'.
    #: **여섯 hop 전부를 통과해야 한다** — 어느 한 곳에서 벗겨지면 읽는 사람이 둘을 구별할 수
    #: 없고, 그건 ADR-0010 §4 가 "추출 안 하느니만 못하다" 고 한 상태다: 알려진 공백이
    #: 표시 없는 주장으로 바뀐다.
    provenance_tier: str = "authored"
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
    #: 실패해서 결과에 기여하지 못한 다리들 (`LEGS` 의 부분집합).
    #: **"아무것도 못 찾았다" 와 "죽었다" 는 다른 사실**이고, 그 둘이 구별되지 않는 것이
    #: 이 코드베이스가 반복해서 찾아낸 결함이다. 호출자에게도 그대로 나간다.
    degraded: list[str] = field(default_factory=list)


async def _bm25_search(
    query: str,
    tenant: str,
    clearance: str,
    top_k: int = 20,
) -> list[tuple[str, int]]:
    """BM25 검색. (chunk_rid, rank) 반환."""
    tokens = active_tokenizer().tokenize(query)
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
        -- `c.rid` 는 장식이 아니라 **전순서**를 만드는 키다. ts_rank_cd 동점이 빽빽해서
        -- (상위 25행에 13~16종 점수) 동점 안 순서가 물리적 행 순서를 따라가고, 그게 LIMIT
        -- 경계를 흔들어 같은 질의가 적재본마다 다른 답을 냈다 (SPEC-nexus-deterministic-retrieval-order §1).
        ORDER BY rank_score DESC, c.rid ASC
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
    column: str | None = None,
) -> list[tuple[str, int]]:
    """Vector 검색. (chunk_rid, rank) 반환.

    `column` 은 어느 임베딩 세대를 읽을지다 (SPEC-nexus-kure-embedding-swap §4.2). 컷오버와
    롤백이 이 값 하나로 이뤄지므로, **화이트리스트를 통과한 이름만** SQL 에 닿는다.
    """
    col = resolve_column(column)
    query_embedding = await embedding_svc.embed_query(query)

    vec_str = "[" + ",".join(str(v) for v in query_embedding) + "]"

    rows = await db.fetch_all(
        f"""
        SELECT c.rid, c.{col} <=> $1::vector as distance
        FROM chunks c
        WHERE c.{col} IS NOT NULL
          AND c.tenant = $2
          AND c.classification <= $3::classification_level
          AND c.is_quarantined = false
          AND c.status = 'active'
          AND EXISTS (SELECT 1 FROM documents d
                      WHERE d.rid = c.doc_rid AND d.status = 'active')
        -- 키워드 다리와 같은 이유의 전순서 키. 다만 이 다리는 ivfflat(ANN)이라 **후보 집합
        -- 자체**가 흔들릴 수 있고, 정렬 키는 그걸 고치지 못한다 (같은 SPEC §4.3 — 측정해서 기록한다).
        ORDER BY distance ASC, c.rid ASC
        LIMIT $4
        """,
        vec_str, tenant, clearance, top_k,
    )

    return [(r["rid"], i + 1) for i, r in enumerate(rows)]


#: 검색이 가진 다리들. `SearchResult.degraded` 에 들어갈 수 있는 값은 여기가 정본이다.
LEGS = ("bm25", "vector", "graph")


def degrades_the_leg(exc: BaseException) -> bool:
    """이 실패는 **이 다리만** 죽이는가, 아니면 배포가 아픈가 (SPEC-nexus-embedding-cutover-seam §4.4).

    `nexus/CLAUDE.md` 가 금지하는 것은 **죽은 DB 를 우회해 답하는 것**이지 한 다리의 degrade 가
    아니다. 그 둘의 차이는 무엇이 없어졌느냐다: **DB 는 두 다리가 함께 서 있는 기반**이고,
    임베딩 백엔드는 한 다리의 서버다. 기반이 없으면 어떤 답도 신뢰할 수 없으니 크게 실패해야 하고,
    한 다리의 서버가 없으면 다른 다리의 답은 여전히 근거 위에 있다 — 더 나쁘지만, 나쁘다고 표시된다.

    그래서 분류는 **좁게** 하고, 애매하면 503 으로 보낸다: 잘못된 503 은 보이는 장애지만 잘못된
    degrade 는 조용히 나빠진 답이고, 이 코드베이스는 후자를 이미 두 번 치렀다(재적재마다 흔들리던
    검색 순서, 상수 벡터를 읽은 ANN 측정).

    degrade: `DataError` — 차원 불일치(SQLSTATE 22000)가 이 부류다. **이 질의의 벡터**의 성질이라
    재시도로 낫지 않는다. 이 부류가 그 결함 하나보다 넓다는 것은 알고 있고(벡터 다리의 질의 조립
    버그도 여기로 온다), 그래서 error 레벨로 SQLSTATE 와 함께 남긴다 — 조립 버그는 테스트와 로그가
    잡고, 살아 있는 500 은 사용자가 잡는다.
    """
    import asyncpg

    return isinstance(exc, asyncpg.exceptions.DataError)


async def _vector_leg(
    query: str,
    embedding_svc: EmbeddingService,
    tenant: str,
    clearance: str,
    top_k: int,
    column: str | None,
) -> tuple[list[tuple[str, int]], bool]:
    """(결과, degraded). **빈 결과와 죽은 다리를 구분해서 돌려준다.**

    예전엔 임베딩 실패를 조용히 삼켜 빈 리스트를 냈고 SQL 실패는 500 으로 나갔다 — 둘 다 틀렸다.
    """
    try:
        return await _vector_search(query, embedding_svc, tenant, clearance, top_k, column), False
    except Exception as e:                      # noqa: BLE001 — 분류가 이 함수의 일이다
        if isinstance(e, (UnknownVectorColumn,)):
            raise                               # 설정 오타는 우리 잘못이고, 조용히 degrade 할 수 없다
        if _is_embedding_failure(e) or degrades_the_leg(e):
            logger.error("vector_leg_degraded", column=resolve_column(column),
                         error_type=type(e).__name__,
                         sqlstate=getattr(e, "sqlstate", None), error=str(e)[:200])
            return [], True
        raise


def _is_embedding_failure(exc: BaseException) -> bool:
    """임베딩 백엔드 쪽 실패인가 — 사이드카가 안 떠 있거나(503), 준비 중이거나, 못 붙거나."""
    import httpx

    return isinstance(exc, (httpx.HTTPError, RuntimeError, WrongVectorDimensions))


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

    **채널이 하나인 경우다.** 멀티턴은 질의 변형(재작성/원문)을 채널로 얹는데, 그 융합은
    `fuse_channels` 가 한다 — 이 함수는 거기에 가중치 1.0 짜리 채널 하나를 넘기는 얇은 겉면이다.
    구현이 둘이면 갈라지고, 갈라진 융합은 비교가 아니다.
    """
    return fuse_channels([ChannelResults(bm25=bm25_results, vector=vector_results, weight=1.0)], k)


@dataclass
class ChannelResults:
    """한 **채널**(= 질의 변형)이 두 **다리**에서 얻은 순위. 축이 둘이라는 것이 요점이다.

    채널 = 무엇을 물었나(재작성 질의 / 사용자가 실제로 친 문장).
    다리  = 어떻게 찾았나(BM25 / vector).

    가중은 **채널당 한 번** 걸린다. 다리마다 걸면 1.3 이 2.6 이 된다 (SPEC §3.3).
    """
    bm25: list[tuple[str, int]] = field(default_factory=list)
    vector: list[tuple[str, int]] = field(default_factory=list)
    weight: float = 1.0
    #: 진단용 이름(`rewritten` / `original`). 점수에 영향을 주지 않는다.
    name: str = ""


def fuse_channels(channels: list[ChannelResults], k: int = 60) -> list[dict]:
    """가중 RRF: `score = Σ_channel w_channel · Σ_leg 1/(k + rank + 1)`.

    **채널이 하나이고 가중이 1.0 이면 결과는 예전과 글자 그대로 같다** — 그것이 U2·U3 를 나눠
    넣은 이유이자 §4 I1 이 요구하는 바다.

    중복 제거의 실제 효과를 오해하지 마라: 두 채널의 질의 문자열이 같으면 두 채널은 같은 순위
    목록을 내고, 가중 합산은 **모든 문서에 같은 배수**를 곱할 뿐 순서를 바꾸지 않는다. 절대
    점수만 팽창한다(§3.3, §4 I6).
    """
    scores: dict[str, dict] = {}

    def _slot(rid: str) -> dict:
        if rid not in scores:
            scores[rid] = {"rid": rid, "score": 0.0, "bm25_rank": None, "vector_rank": None,
                           "channel_ranks": {}}
        return scores[rid]

    for ch in channels:
        for leg, results in (("bm25", ch.bm25), ("vector", ch.vector)):
            for rid, rank in results:
                slot = _slot(rid)
                slot["score"] += ch.weight * (1.0 / (k + rank + 1))
                # 다리별 순위는 **채널을 통틀어 가장 좋은 것**을 남긴다. 칸이 둘뿐인데 채널이
                # 늘었으므로, 어느 하나를 고르지 않으면 나중 채널이 앞 채널을 덮는다.
                key = f"{leg}_rank"
                if slot[key] is None or rank < slot[key]:
                    slot[key] = rank
                # 채널별 순위는 진단으로 따로 남긴다 — 두 칸으로는 네 순위를 표현할 수 없고,
                # "재작성이 mecab tsvector 텀을 흔드는가"(SPEC §8)는 이 값으로만 답할 수 있다.
                if ch.name:
                    slot["channel_ranks"].setdefault(ch.name, {})[leg] = rank

    # 동점 키를 **명시**한다. 안정 정렬에 기대면 융합 순서가 이 함수의 입력 구성 순서에
    # 좌우되고, 나중에 heapq.nlargest 나 병렬 병합으로 바꾸는 순간 비결정성이 조용히 돌아온다.
    # RRF 점수는 순위에서 나오므로 동점이 특히 빽빽하다.
    return sorted(scores.values(), key=lambda x: (-x["score"], x["rid"]))


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
               d.doc_type as doc_type, d.updated_at as updated_at,
               coalesce(d.n_images, 0) as n_images,
               c.provenance_tier as provenance_tier
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
            chunk_text=r["chunk_text"],
            doc_n_images=r["n_images"] or 0,
            provenance_tier=r["provenance_tier"] or "authored",
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
    channels: list[tuple[str, float]] | None = None,
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

    # **채널 = 질의 변형.** 기본은 하나(= 오늘) — 그러면 아래 융합이 예전과 글자 그대로 같다.
    # 멀티턴은 (재작성, 1.3) + (원문, 0.5) 두 채널로 온다 (SPEC §3.3).
    #
    # **후보 풀은 채널마다 그대로다.** 다리가 둘에서 넷으로 늘어도 bm25_top_k/vector_top_k 는
    # 건드리지 않는다. 컷(_diversify/per_doc_cap/top_k)은 융합 **뒤 한 번만** 걸린다 — 채널마다
    # 걸면 다양성 규칙이 두 번 먹는다.
    active = channels or [(query, 1.0)]
    #: 채널 이름은 진단용이다. 점수에 영향을 주지 않는다.
    names = ["rewritten", "original"] if len(active) > 1 else [""]

    tasks: dict[tuple[int, str], asyncio.Task] = {}
    for i, (text, _w) in enumerate(active):
        if use_bm25:
            tasks[(i, "bm25")] = asyncio.create_task(
                _bm25_search(text, tenant, clearance, bm25_top_k))
        # embedding_svc 가 없으면 벡터 다리는 못 돈다. 그렇다고 BM25 로 슬그머니 바꿔치기하고
        # route_used='vector_only' 라 보고하지는 않는다 — 빈 결과가 정직하다.
        if use_vector and embedding_svc:
            tasks[(i, "vector")] = asyncio.create_task(
                _vector_leg(text, embedding_svc, tenant, clearance, vector_top_k,
                            column=configured_column(cfg)))

    done = dict(zip(tasks, await asyncio.gather(*tasks.values()))) if tasks else {}

    ch_results: list[ChannelResults] = []
    for i, (_text, weight) in enumerate(active):
        vector_results, vector_degraded = done.get((i, "vector"), ([], False))
        if vector_degraded and "vector" not in result.degraded:
            result.degraded.append("vector")
        ch_results.append(ChannelResults(
            bm25=done.get((i, "bm25"), []), vector=vector_results, weight=weight,
            name=names[i] if i < len(names) else f"ch{i}"))

    bm25_ms = int((time.time() - start) * 1000)

    # RRF Fusion (전체 병합, 컷은 다양성 이후)
    fused = fuse_channels(ch_results, k=rrf_k)

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


async def visibility_counts(tenant: str, clearance: str) -> tuple[int, int]:
    """(이 테넌트의 활성 문서 수, 그중 이 등급으로 **보이는** 수).

    0건의 원인 셋은 서로 다른 사실이고 고칠 사람도 다르다: 코퍼스가 빈 것(적재 담당), 질의가 안
    맞은 것(사용자), 그리고 등급/테넌트 설정이 코퍼스 전체를 가린 것(운영자). 셋째가 둘째로
    위장하던 동안 슬랙 봇은 "인덱싱된 문서에서 답을 찾지 못했습니다" 라고 답했다 — 뒤진 문서가
    하나도 없었으므로 거짓이었다 (2026-08-13, 봇 principal PUBLIC vs 문서 116건 전부 INTERNAL).

    **이 함수는 검색 경로에서 부르지 않는다.** 첫 판은 `hybrid_search` 안에 두었고 그것이 CI 를
    40분 매달았다: `hybrid_search` 는 DB 없이 도는 단위 테스트 수백 개가 부르는 함수인데, 거기에
    DB 왕복 하나를 얹으면 **죽은 이벤트 루프에 묶인 전역 asyncpg 풀**을 집는다
    (`tests/test_search_route_api.py` 픽스처가 이 함정을 이미 적어 두었다). 커넥션이 열린
    트랜잭션째 반납되지 않아 `documents` 에 AccessShareLock 이 남고, 뒤따르는 모든
    `TRUNCATE documents` 가 그 뒤에 줄을 섰다. 두 번째 판은 API 응답 조립으로 옮기고 타임아웃을
    걸었는데 **그래도 매달렸다** — 질의는 끝나 있었고 붙들고 있던 것은 커넥션이었기 때문이다.

    그래서 진단은 **자기 엔드포인트**(`GET /visibility`)에만 산다. 답을 못 받은 클라이언트가
    이유를 물으러 오는 자리이지, 모든 검색이 지나는 자리가 아니다.
    """
    row = await db.fetch_one(
        "SELECT count(*) AS total, "
        "       count(*) FILTER (WHERE classification <= $2::classification_level) AS visible "
        "FROM documents "
        "WHERE tenant = $1 AND status = 'active' AND is_quarantined = false",
        tenant, clearance)
    if not row:
        return 0, 0
    return int(row["total"] or 0), int(row["visible"] or 0)
