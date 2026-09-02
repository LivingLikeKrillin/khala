"""BM25 + Vector 병렬 검색 + RRF Fusion.

⛔ **그래프는 융합에 들어가지 않는다.** 이 줄이 오래 `"BM25 + Vector + Graph 3-way"` 였고
`nexus/CLAUDE.md` 는 이미 정정했는데 이 파일만 그대로였다(외부 평가 P4). 그래프는 라우터가
고른 경로에서 **따로** 조회되어 근거에 붙고, RRF 는 두 다리만 융합한다.

모든 검색은 base_filter(tenant, classification, quarantine, status)를 적용한다.
"""

from __future__ import annotations
from collections.abc import Sequence

from nexus.search.scope_sql import tenant_predicate

import asyncio
import re
from dataclasses import dataclass, field
from datetime import datetime

import structlog

from nexus import db
from nexus.index.bm25 import active_tokenizer, tokens_to_tsquery
from nexus.search.confidence import Confidence
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
    #: 문서 단위 Recall@10 은 1.000 이었다 — 검색만 측정하는 자에는 안 보이던 구간이다.
    chunk_text: str = ""
    #: 이 청크가 속한 문서가 담은 이미지 수. 신호원이지 랭킹 입력이 아니다 — 그림에 갇힌
    #: 내용 때문에 답을 못 내는 비율을 측정하려면 근거가 어디서 왔는지 알아야 한다 (migration 011).
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
    #: 이 청크가 **어느 코퍼스에서 왔는가** (SPEC-nexus-design-corpus-cutover §5.3).
    #:
    #: 읽기 범위가 목록이 된 뒤로 한 답변의 근거는 여러 테넌트에서 온다. `search_log.tenant` 는
    #: 귀속용 단일 값이고 `read_scope` 는 **읽을 수 있었던** 범위라, 둘 다 *"이 답이 실제로 어느
    #: 코퍼스에 기댔는가"* 를 말하지 못한다 — 범위를 넓혀 놓고 근거가 한쪽에서만 오는 상태와
    #: 고르게 오는 상태가 기록에서 같아 보인다. 그 차이가 여기 있다.
    tenant: str = ""


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
    #: 상한을 꽉 채운 문서의 **남은 절**(`search/section_fill.py`). 근거로만 가고 **순위에는
    #: 안 들어간다** — 사람이 보는 목록·Recall·Top-1 은 이 필드가 있든 없든 같다.
    fill: list[SearchHit] = field(default_factory=list)
    #: 이번 검색이 얼마나 **잘 맞았는가**(`search/confidence.py`). 융합이 지우는 신호라 다리에서
    #: 직접 들고 온다. **랭킹에 쓰지 않는다** — 서술 계약에만 쓴다.
    confidence: Confidence = field(default_factory=Confidence)


#: `ts_rank_cd` 의 **길이 정규화 비트마스크**. `1` = 점수를 `1 + log(문서 길이)` 로 나눈다.
#:
#: 오래 `0`(정규화 없음)이었고, 커버 밀도는 매치 수에 비례하므로 **긴 청크가 이겼다.**
#: 2026-08-26 실측: 질의 하나에 매칭 140건인데 1위가 1,228자짜리(점수 4.700)이고 정답인
#: 19자짜리 행은 **48위**(0.400)였다 — 못 찾은 게 아니라 `bm25_top_k`(20) 밖으로 밀렸고,
#: 그래서 RRF 에 한쪽 다리 점수만 들고 들어가 융합에서 탈락했다.
#:
#: 다섯 후보를 **제품 경로**(hybrid Recall@10)로 측정했다 —
#: `tests/eval/bm25-normalization/README.md`. 사전등록한 바는 "파편이 오르고 대조군이 안
#: 떨어질 것" 이었고, `1` 과 `16` 이 통과, `2`(길이로 나눔)는 파편에 제일 좋았지만 **대조군
#: Recall 을 1.000 → 0.917 로 떨어뜨려 기각**됐다. `1` 과 `16` 은 그 표본에서 구별되지 않았다.
#:
#: ⚠ **유의성은 주장하지 않는다**: 5승 0패 28무로 방향은 안 뒤집혔지만 불일치쌍이 문턱(6)에
#: 하나 모자란다. 그리고 코퍼스 하나에서 측정했다. 되돌리려면 이 값을 `0` 으로 두면 된다.
#:
#: `SPEC-nexus-ranking-precision` §4.1 은 정규화 없는 `ts_rank_cd` 를 골랐다. 이 값은 그
#: 결정의 개정이고, 근거는 `SPEC-nexus-bm25-length-normalization` 에 있다.
BM25_LENGTH_NORMALIZATION = 1


async def _bm25_search(
    query: str,
    tenant: str | Sequence[str],
    clearance: str,
    top_k: int = 20,
) -> tuple[list[tuple[str, int]], float | None]:
    """BM25 검색. `((chunk_rid, rank) 목록, 1위 원점수)`.

    **원점수를 같이 돌려주는 이유**: 융합(RRF)은 순위만 쓰므로 "얼마나 잘 맞았는가" 가
    사라진다. 그 크기는 여기서 이미 계산해 정렬에까지 썼는데 버려지고 있었다
    (`search/confidence.py` 머리말의 실측). 융합에 들어가는 첫 값은 예전과 같다.

    **`None` 과 `0.0` 은 다른 사실이다.** `None` 은 *다리가 안 돌았다* — 토크나이저가 텀을
    하나도 못 만들어 질의 자체가 없었다. `0.0` 은 *돌았는데 아무것도 못 잡았다* 이고, 그것은
    "코퍼스 밖" 의 가장 강한 증거다. 둘을 같은 `None` 으로 뭉개던 동안 그 강한 증거가
    `Confidence.weak` 에서 **못 측정한 것**으로 읽혀 신호가 안 켜졌다 — 2026-08-24 라이브에서
    *"오늘 서울 날씨 알려줘"* 가 거리 0.608(멀다)인데도 약함 판정을 못 받았다.
    """
    tokens = active_tokenizer().tokenize(query)
    tsquery = tokens_to_tsquery(tokens)

    if not tsquery:
        return [], None

    tenant_pred, tenant_val = tenant_predicate("c.tenant", 2, tenant)
    rows = await db.fetch_all(
        f"""
        SELECT c.rid,
               ts_rank_cd(c.tsvector_ko, to_tsquery('simple', $1),
                          $5) as rank_score
        FROM chunks c
        WHERE c.tsvector_ko @@ to_tsquery('simple', $1)
          AND {tenant_pred}
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
        tsquery, tenant_val, clearance, top_k, BM25_LENGTH_NORMALIZATION,
    )

    # 매칭 0건은 **측정해서 0점**이다(위 참조). 안 측정한 것이 아니다.
    return ([(r["rid"], i + 1) for i, r in enumerate(rows)],
            float(rows[0]["rank_score"]) if rows else 0.0)


async def _vector_search(
    query: str,
    embedding_svc: EmbeddingService,
    tenant: str | Sequence[str],
    clearance: str,
    top_k: int = 20,
    column: str | None = None,
) -> tuple[list[tuple[str, int]], float | None]:
    """Vector 검색. `((chunk_rid, rank) 목록, 1위 코사인 거리)`.

    `column` 은 어느 임베딩 세대를 읽을지다 (SPEC-nexus-kure-embedding-swap §4.2). 컷오버와
    롤백이 이 값 하나로 이뤄지므로, **화이트리스트를 통과한 이름만** SQL 에 닿는다.
    """
    col = resolve_column(column)
    query_embedding = await embedding_svc.embed_query(query)

    vec_str = "[" + ",".join(str(v) for v in query_embedding) + "]"
    tenant_pred, tenant_val = tenant_predicate("c.tenant", 2, tenant)

    rows = await db.fetch_all(
        f"""
        SELECT c.rid, c.{col} <=> $1::vector as distance
        FROM chunks c
        WHERE c.{col} IS NOT NULL
          AND {tenant_pred}
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
        vec_str, tenant_val, clearance, top_k,
    )

    return ([(r["rid"], i + 1) for i, r in enumerate(rows)],
            float(rows[0]["distance"]) if rows else None)


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
) -> tuple[list[tuple[str, int]], bool, float | None]:
    """(결과, degraded, 1위 거리). **빈 결과와 죽은 다리를 구분해서 돌려준다.**

    예전엔 임베딩 실패를 조용히 삼켜 빈 리스트를 냈고 SQL 실패는 500 으로 나갔다 — 둘 다 틀렸다.

    죽은 다리의 거리는 `None` 이다. **0.0 으로 채우지 않는다** — 그러면 "완벽하게 맞았다" 로
    읽히고, 못 측정한 것과 측정해서 좋은 것이 같은 값이 된다.
    """
    try:
        hits, dist = await _vector_search(query, embedding_svc, tenant, clearance, top_k, column)
        return hits, False, dist
    except Exception as e:                      # noqa: BLE001 — 분류가 이 함수의 일이다
        if isinstance(e, (UnknownVectorColumn,)):
            raise                               # 설정 오타는 우리 잘못이고, 조용히 degrade 할 수 없다
        if _is_embedding_failure(e) or degrades_the_leg(e):
            logger.error("vector_leg_degraded", column=resolve_column(column),
                         error_type=type(e).__name__,
                         sqlstate=getattr(e, "sqlstate", None), error=str(e)[:200])
            return [], True, None
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
               c.classification, c.source_version, c.tenant,
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
            tenant=r["tenant"] or "",
        ))

    return hits


async def _fill_sections(
    hits: list[SearchHit], tenant: str, clearance: str, per_doc_cap: int,
) -> list[SearchHit]:
    """상한을 채운 문서의 남은 절 → `SearchHit`. 실패는 삼키되 **조용하지 않게**.

    채움은 보강이다. 이게 죽었다고 검색 결과까지 버리면, 있던 답도 못 준다.
    """
    from nexus.search.section_fill import (
        fill_for_docs,
        fill_for_sections,
        hit_sections,
        saturated_docs,
    )

    docs = saturated_docs(hits, per_doc_cap)
    exclude = {h.rid for h in hits}
    try:
        rows = await fill_for_docs(tenant, clearance, docs, exclude) if docs else []

        # **상한을 넘는 문서는 트리거가 다르다.** `fill_for_docs` 가 그 문서를 통째로 빼므로,
        # 포화를 기다리면 그 부류는 **영영 아무 맥락도 못 받는다**. 그리고 포화는 오히려 덜
        # 걸린다 — A13 컷오버로 파편이 패킷 자리를 나눠 가지면서 큰 정책 문서의 몫이 상한 아래로
        # 내려갔다(2026-08-26 실측: 3/5). 그래서 큰 문서에서는 **히트가 앉은 절**을 포화와
        # 무관하게 완성한다. 절을 고르는 것이 아니라 검색이 이미 고른 절이다.
        #
        # 그날 이것이 없어서 생긴 일: 어떤 표가 낡았다고 알리는 문단이 그 표와 같은 절에
        # 있었는데(chunk 2·6) 문서가 32청크라 빠졌고, 답변이 낡은 숫자를 정본으로 읽었다.
        sections = hit_sections(hits)
        if sections:
            rows += await fill_for_sections(
                tenant, clearance, sections, exclude | {r["rid"] for r in rows})
    except Exception as e:  # noqa: BLE001 — 보강 실패가 검색을 죽이면 안 된다
        logger.warning("section_fill_failed", error=str(e), docs=len(docs))
        return []
    if not rows:
        return []

    return [SearchHit(
        rid=r["rid"],
        doc_rid=r["doc_rid"],
        doc_title=r["doc_title"] or "",
        section_path=r["section_path"],
        source_uri=r["source_uri"],
        source_version=r["source_version"] or "",
        # 미리보기는 검색 결과와 같은 규칙으로 자른다. 이 절들은 사람 목록에 안 나가지만,
        # 스니펫이 비어 있으면 옛 호출부가 `text` 로 떨어질 때 근거가 통째로 빈다.
        snippet=_truncate_snippet(r["chunk_text"], 300),
        chunk_text=r["chunk_text"],
        doc_n_images=r["n_images"] or 0,
        provenance_tier=r["provenance_tier"] or "authored",
        # **점수는 0 이다.** 이 절들은 순위 경쟁을 하지 않았고, 점수를 지어내면 다음 사람이
        # 그걸 랭킹 신호로 읽는다.
        score=0.0,
        classification=r["classification"],
        approved_hash=r["approved_hash"] or "",
        doc_type=r["doc_type"] or "",
        updated_at=r["updated_at"],
        tenant=r["tenant"] or "",
    ) for r in rows]


async def hybrid_search(
    query: str,
    tenant: str | Sequence[str] = "default",
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
    #: 적합도는 **첫 채널**(= 사용자가 물은 것)로 측정한다. 재작성 채널까지 섞으면 "무엇에 대한
    #: 적합도인가" 가 흐려진다 — 재작성이 잘 맞은 것과 질문이 잘 맞은 것은 다른 사실이다.
    top_distance = top_bm25 = None
    for i, (_text, weight) in enumerate(active):
        vector_results, vector_degraded, vector_top = done.get((i, "vector"), ([], False, None))
        if vector_degraded and "vector" not in result.degraded:
            result.degraded.append("vector")
        bm25_results, bm25_top = done.get((i, "bm25"), ([], None))
        if i == 0:
            top_distance, top_bm25 = vector_top, bm25_top
        ch_results.append(ChannelResults(
            bm25=bm25_results, vector=vector_results, weight=weight,
            name=names[i] if i < len(names) else f"ch{i}"))
    result.confidence = Confidence(top_distance=top_distance, top_bm25=top_bm25)

    bm25_ms = int((time.time() - start) * 1000)

    # RRF Fusion (전체 병합, 컷은 다양성 이후)
    fused = fuse_channels(ch_results, k=rrf_k)

    # 메타데이터 보강 (fused 순서 보존)
    enriched = await _enrich_hits(
        fused, tenant, max_snippet_chars=search_cfg.get("snippet_max_chars", 300))

    # 문서 다양성 + top_k 컷 — 한 문서가 결과를 도배하지 않게.
    per_doc_cap = search_cfg.get("diversity_per_doc_cap", 3)
    result.hits = _diversify(enriched, top_k, per_doc_cap)

    # 상한을 꽉 채운 문서 = 검색이 몰표를 준 문서. 그 안의 **남은 절**을 근거에 채운다.
    # 순위에는 넣지 않는다 (SPEC 근거는 `search/section_fill.py` 머리말).
    #
    # **기본값이 꺼짐인 이유는 취향이 아니다.** 이 규칙은 쿼리를 **하나 더** 쏘고, 그러면 설정을
    # 안 준 호출부(단위 시험 다수)가 전에는 없던 DB 접촉을 하게 된다. `db.get_pool()` 은 풀이
    # 없으면 기본 `DATABASE_URL`(=개발 DB)로 새로 열기 때문에, 그 접촉은 조용히 엉뚱한 DB 를
    # 향하고 다른 테스트의 이벤트 루프까지 망가뜨린다 — 2026-08-18 CI 에서 실제로 그렇게 됐다.
    # 배포는 config.yaml 로 켠다.
    if search_cfg.get("section_fill", False):
        result.fill = await _fill_sections(result.hits, tenant, clearance, per_doc_cap)

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
