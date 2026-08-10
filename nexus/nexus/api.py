"""FastAPI 엔드포인트.

API_CONTRACT.md에 정의된 엔드포인트를 구현한다.
모든 응답은 NexusResponse로 감싸고, 검색에는 base_filter를 적용한다.
"""

from __future__ import annotations

import os
import time
from contextlib import asynccontextmanager
from typing import Any

import yaml
from fastapi import FastAPI, HTTPException, UploadFile, File, Query, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from nexus import db
from nexus.auth import AuthConfig, Principal, effective_scope
from nexus.auth.deps import make_get_principal
from nexus.index.graph_extractor import find_entities_in_text, _build_entity_patterns, _load_gazetteer
from nexus.ingest.pipeline import run_ingest
from nexus.llm.answer import _load_staleness_ttl, generate_answer
from nexus.documents.staleness import annotate_staleness
from nexus.llm.citations import validate_citations
from nexus.llm.numbers import validate_numbers
from nexus.llm.prompts import SYSTEM_PROMPT, build_user_prompt
from nexus.otel.aggregator import run_otel_aggregation
from nexus.otel.diff_engine import run_diff
from nexus.index.vector_index import configured_column
from nexus.providers.embedding import embedding_service_from_config
from nexus.providers.llm import LLMService
from nexus.repositories.graph import PostgresGraphRepository
from nexus.rid import canonicalize_entity_name, entity_rid
from nexus.search.evidence_packet import assemble_packet, format_for_llm
from nexus.search.hybrid import hybrid_search
from nexus.search.hybrid import ROUTES as hybrid_routes
from nexus.search.hybrid import UnknownRoute
from nexus.search.router import determine_route
from nexus.search.signals import JudgeInput, extract_signals, record_search


# 로컬 dev 온램프: ANTHROPIC_API_KEY 미설정 시, 일시적 API 오류와 구분되는 *행동지침* 안내.
# (LLM 호출 자체가 실패하는 것과 달리, 미설정은 호출 전 결정적으로 알 수 있다 → LLMService.configured)
LLM_NOT_CONFIGURED_NOTICE = (
    "로컬 LLM 키가 설정되지 않아 답변 생성을 건너뛰었습니다. "
    "nexus/.env 에 ANTHROPIC_API_KEY 를 넣고 재기동(task up)하면 답변이 생성됩니다. "
    "그동안에도 근거는 위에 그대로 제공됩니다 — 출처를 직접 확인하세요."
)


# ── Lifespan ──
async def _bootstrap_gazetteer() -> None:
    """entities.yaml의 엔티티를 DB에 초기 등록."""
    from nexus.index.graph_extractor import ensure_entity_exists, _load_gazetteer
    try:
        entities = _load_gazetteer()
        for ent in entities:
            await ensure_entity_exists(
                "default",
                ent["name"],
                ent["type"],
                description=ent.get("description", ""),
                aliases=ent.get("aliases", []),
            )
        if entities:
            import structlog
            structlog.get_logger(__name__).info("gazetteer_bootstrapped", count=len(entities))
    except Exception:
        pass  # DB 미준비 시 무시


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Fail fast: refuse to boot enforced with placeholder credentials.
    AuthConfig.from_dict(_load_config()).validate_startup()
    # 같은 이유로 임베딩 세대도 여기서 한 번 세운다: 모델·컬럼·백엔드가 어긋난 배포는 **요청마다**
    # 실패하는 대신 아예 뜨지 않아야 한다 (SPEC-nexus-embedding-cutover-seam §4.2).
    embedding_service_from_config(_load_config())
    await db.get_pool()
    await _log_embedding_coverage()
    await _bootstrap_gazetteer()
    await db.ensure_search_log()   # ← 추가: 멱등, 기존 DB도 적재 시작
    await _sweep_orphaned_syncs()
    yield
    await db.close_pool()


async def _log_embedding_coverage() -> None:
    """설정된 세대의 커버리지를 기동 로그에 남긴다 — 빈 컬럼은 error, 부분은 warning.

    거부하지 않는 이유는 `embed_health.log_embedding_coverage` 에 적혀 있다: NULL 벡터는 평범한
    과도상태이고, 그걸 부팅 거부로 만들면 적재 사고가 배포 장애가 된다.
    """
    try:
        from nexus.index.embed_health import log_embedding_coverage

        await log_embedding_coverage(configured_column(_load_config()))
    except Exception:  # noqa: BLE001 — 마이그레이션 전 DB 등. 부팅을 막지 않는다
        pass


async def _sweep_orphaned_syncs() -> None:
    """죽은 프로세스가 남긴 running sync 행을 정리한다 (SPEC-nexus-notion-source-console §4.2).

    advisory lock 을 잡을 수 있는 행만 — 다른 커넥션에서 도는 잡은 건드리지 않는다.
    소스 콘솔 테이블이 아직 없는 DB(마이그레이션 전)면 조용히 넘어간다.
    """
    try:
        import structlog

        from nexus.sources.runs_store import sweep_orphaned_runs
        swept = await sweep_orphaned_runs()
        if swept:
            structlog.get_logger(__name__).warning("notion_sync_runs_swept", run_ids=swept)
    except Exception:  # noqa: BLE001 — 부팅을 막지 않는다
        pass


app = FastAPI(title="Nexus", version="0.1.0", lifespan=lifespan)


# ── Config ──
def _load_config() -> dict:
    from pathlib import Path
    p = Path("config.yaml")
    if not p.exists():
        return {}
    with open(p, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


# ── Auth (identity layer) ──
def _auth_config() -> AuthConfig:
    return AuthConfig.from_dict(_load_config())


# FastAPI dependency: resolves Authorization: Bearer -> Principal (401 in enforced mode).
get_principal = make_get_principal(_auth_config)


def _mount_sources(app) -> None:
    """소스 콘솔·문서 라우터를 붙이고 principal 해석기를 꽂는다.

    라우터는 `nexus.api` 를 임포트할 수 없다(순환). 그래서 플레이스홀더 의존성 `dep` 를
    두고 여기서 override 한다 — 꽂히지 않으면 라우터는 500 으로 죽지, 무인증으로 열리지 않는다.
    """
    from nexus.documents.api import dep as documents_dep
    from nexus.documents.api import router as documents_router
    from nexus.sources.api import dep as sources_dep
    from nexus.sources.api import router as sources_router

    app.include_router(sources_router)
    app.include_router(documents_router)
    app.dependency_overrides[sources_dep] = get_principal
    app.dependency_overrides[documents_dep] = get_principal


def _dev_token() -> str | None:
    """로컬 dev 편의 토큰(NEXUS_DEV_TOKEN). 미설정/빈값이면 None — prod 에선 노출 안 됨."""
    return os.getenv("NEXUS_DEV_TOKEN") or None

# CORS: an Authorization header requires a real origin allowlist, not "*".
# When the A2A surface is enabled, external A2A caller origins are unioned in (Phase 2).
def _cors_origins() -> list[str]:
    from nexus.a2a.config import A2AConfig, resolve_a2a_cors_origins

    return resolve_a2a_cors_origins(
        _auth_config().allowed_origins, A2AConfig.from_dict(_load_config())
    )


app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── A2A (Agent2Agent) Phase 0 — additive, flag-gated, off by default ──
# Unset/false NEXUS_A2A_ENABLED ⇒ no routes, no SDK import, zero overhead (SPEC §6.4).
def _mount_a2a_if_enabled() -> None:
    from nexus.a2a.config import A2AConfig

    cfg = A2AConfig.from_dict(_load_config())
    if not cfg.enabled:
        return
    from nexus.a2a.server import mount_a2a  # import the A2A SDK only when enabled

    mount_a2a(app, cfg)


_mount_a2a_if_enabled()
_mount_sources(app)


# ── Response wrapper ──
class NexusResponse(BaseModel):
    success: bool = True
    data: Any = None
    error: str | None = None
    meta: dict = Field(default_factory=dict)


# ── Request/Response models ──
class SearchRequest(BaseModel):
    query: str
    top_k: int = 10
    route: str = "auto"
    classification_max: str = "INTERNAL"
    tenant: str = "default"
    include_graph: bool = True
    include_evidence: bool = True


class AnswerRequest(BaseModel):
    query: str
    top_k: int = 10
    route: str = "auto"
    classification_max: str = "INTERNAL"
    tenant: str = "default"


class IngestRequest(BaseModel):
    path: str
    force: bool = False
    tenant: str = "default"


class UploadRequest(BaseModel):
    path: str = "uploads"
    tenant: str = "default"


class OtelAggregateRequest(BaseModel):
    window_minutes: int = 5
    lookback_minutes: int = 60
    tenant: str = "default"


class SupersedeRequest(BaseModel):
    old_ref: str
    new_ref: str
    tenant: str = "default"


# ── Endpoints ──

@app.get("/auth/dev-token", response_model=NexusResponse)
async def dev_token() -> NexusResponse:
    """로컬 dev 온램프: NEXUS_DEV_TOKEN 설정 시 그 토큰을 노출(웹이 Bearer 로 자동 사용).

    의도적으로 비-게이트(토큰을 받기 전 단계). prod(env 미설정)에선 token=null 이라 노출 없음.
    이 토큰은 override 가 주입하는 로컬 편의 자격이며 [[local-dev principal]] 과 짝이다.
    """
    return NexusResponse(data={"token": _dev_token()})


def _search_hit_to_dict(h) -> dict:
    """SearchHit → /search 응답 dict. doc_type(축-A 타입, S3) 포함 — 웹 클라이언트 타입 배지용."""
    return {
        "rid": h.rid,
        "doc_rid": h.doc_rid,
        "doc_title": h.doc_title,
        "section_path": h.section_path,
        "source_uri": h.source_uri,
        "snippet": h.snippet,
        "score": h.score,
        "bm25_rank": h.bm25_rank,
        "vector_rank": h.vector_rank,
        "classification": h.classification,
        "doc_type": h.doc_type,
    }


def _validate_route(route: str) -> None:
    """DB 를 만지기 전에 route 를 검증한다.

    검증이 검색 안쪽에 있으면, DB 가 없는 환경에서 '없는 route' 가 503(데이터베이스 연결 실패)로
    보고된다 — 호출자는 자기 오타를 우리 장애로 읽는다. 스트림은 헤더가 나간 뒤라 400 조차 줄 수 없다.
    """
    if route != "auto" and route not in hybrid_routes:
        raise HTTPException(
            status_code=400,
            detail=f"unknown_route: {route!r}. 가능한 값: auto, {', '.join(sorted(hybrid_routes))}")


@app.post("/search", response_model=NexusResponse)
async def search(req: SearchRequest, principal: Principal = Depends(get_principal)) -> NexusResponse:
    """Hybrid 검색."""
    req.tenant, req.classification_max = effective_scope(principal, req.tenant, req.classification_max)
    if not req.query.strip():
        raise HTTPException(status_code=400, detail="쿼리가 비어있습니다.")
    _validate_route(req.route)

    try:
        _t0 = time.time()
        config = _load_config()
        embedding_svc = embedding_service_from_config(config)
        pool = await db.get_pool()
        graph_repo = PostgresGraphRepository(pool)

        # 엔티티 감지
        gazetteer = _load_gazetteer()
        patterns = _build_entity_patterns(gazetteer)
        detected = find_entities_in_text(req.query, patterns)
        entity_rids = [
            entity_rid(req.tenant, e.entity_type, e.name)
            for e in detected
        ]

        # 경로 결정
        route = determine_route(req.query, req.route, [e.name for e in detected])

        result = await hybrid_search(
            query=req.query,
            tenant=req.tenant,
            clearance=req.classification_max,
            top_k=req.top_k,
            embedding_svc=embedding_svc,
            graph_repo=graph_repo if req.include_graph else None,
            route=route,
            entity_rids=entity_rids,
            config=config,
        )

        # Graph findings + diff_flags 조립
        graph_findings = None
        if result.graph:
            diff_items = []
            try:
                diff_items = await graph_repo.get_diff(req.tenant)
            except Exception:
                pass
            graph_findings = {
                "designed_edges": [
                    {"rid": e.rid, "edge_type": e.edge_type,
                     "from_name": e.from_name, "to_name": e.to_name,
                     "confidence": e.confidence}
                    for e in result.graph.edges
                ],
                "observed_edges": [
                    {"rid": o.rid, "edge_type": o.edge_type,
                     "from_name": o.from_name, "to_name": o.to_name,
                     "call_count": o.call_count, "error_rate": o.error_rate,
                     "latency_p95": o.latency_p95}
                    for o in result.graph.observed_edges
                ],
                "diff_flags": [
                    {"flag": d.flag, "from_name": d.from_name,
                     "to_name": d.to_name, "edge_type": d.edge_type}
                    for d in diff_items
                ],
            }

        sig = extract_signals(
            result, None, path="search",
            tenant=req.tenant, clearance=req.classification_max, query=req.query,
            n_entities=len(entity_rids),
            latency_ms=int((time.time() - _t0) * 1000),
        )
        await record_search(sig)   # fire-and-forget; 답변 경로가 아니다 → not_applicable
        return NexusResponse(
            data={
                "results": [_search_hit_to_dict(h) for h in result.hits],
                "graph_findings": graph_findings,
                "route_used": result.route_used,
                "timing_ms": result.timing_ms,
                # 죽은 다리는 호출자에게도 보여야 한다 — 로그에만 있으면 "건강해 보이는" 상태가
                # 그대로다 (SPEC-nexus-embedding-cutover-seam §4.5).
                "degraded": result.degraded,
            },
        )
    except UnknownRoute as e:
        # 호출자가 없는 route 를 골랐다. 500 은 "우리 잘못" 이라는 뜻이므로 여기선 틀렸다.
        # 맨 ValueError 를 잡으면 내부 버그까지 400 이 되어 조용히 넘어간다.
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        if "connect" in str(e).lower():
            raise HTTPException(status_code=503, detail="데이터베이스 연결 실패")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/search/answer", response_model=NexusResponse)
async def search_answer(req: AnswerRequest, principal: Principal = Depends(get_principal)) -> NexusResponse:
    """검색 + LLM 답변 생성."""
    req.tenant, req.classification_max = effective_scope(principal, req.tenant, req.classification_max)
    if not req.query.strip():
        raise HTTPException(status_code=400, detail="쿼리가 비어있습니다.")
    _validate_route(req.route)

    try:
        _t0 = time.time()
        config = _load_config()
        embedding_svc = embedding_service_from_config(config)
        llm_svc = LLMService()
        pool = await db.get_pool()
        graph_repo = PostgresGraphRepository(pool)

        # 엔티티 감지
        gazetteer = _load_gazetteer()
        patterns = _build_entity_patterns(gazetteer)
        detected = find_entities_in_text(req.query, patterns)
        entity_rids = [
            entity_rid(req.tenant, e.entity_type, e.name)
            for e in detected
        ]

        route = determine_route(req.query, req.route, [e.name for e in detected])

        # 검색
        search_result = await hybrid_search(
            query=req.query,
            tenant=req.tenant,
            clearance=req.classification_max,
            top_k=req.top_k,
            embedding_svc=embedding_svc,
            graph_repo=graph_repo,
            route=route,
            entity_rids=entity_rids,
            config=config,
        )

        # Evidence packet 조립
        packet = assemble_packet(search_result.hits, search_result.graph)

        # LLM 답변 생성
        answer_result = await generate_answer(
            query=req.query,
            packet=packet,
            llm_svc=llm_svc,
            route_used=route,
            timing_ms=search_result.timing_ms,
        )

        sig = extract_signals(
            search_result, answer_result, path="search_answer",
            tenant=req.tenant, clearance=req.classification_max, query=req.query,
            n_entities=len(entity_rids),
            latency_ms=int((time.time() - _t0) * 1000),
        )
        await record_search(sig, judge_input=JudgeInput(   # 답변이 받은 것과 같은 근거
            query=req.query, evidence=format_for_llm(packet),
            config=_load_config(), llm_svc=llm_svc))
        return NexusResponse(
            data={
                "answer": answer_result.answer,
                "evidence_snippets": answer_result.evidence_snippets,
                "graph_findings": answer_result.graph_findings,
                "provenance": answer_result.provenance,
                "route_used": answer_result.route_used,
                "timing_ms": answer_result.timing_ms,
                "citations": answer_result.citations,
                "unverified_citations": answer_result.unverified_citations,
                "unverified_numbers": answer_result.unverified_numbers,
                "usage": answer_result.usage,
                "n_stale": answer_result.n_stale,
                # 기권은 코드가 내린 판단이다. 답변 문장을 문자열 대조해서 알아내지 않는다.
                "abstained": answer_result.abstained,
                "abstain_reason": answer_result.abstain_reason,
                "degraded": search_result.degraded,
            },
        )
    except UnknownRoute as e:
        # 호출자가 없는 route 를 골랐다. 500 은 "우리 잘못" 이라는 뜻이므로 여기선 틀렸다.
        # 맨 ValueError 를 잡으면 내부 버그까지 400 이 되어 조용히 넘어간다.
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        if "connect" in str(e).lower():
            raise HTTPException(status_code=503, detail="데이터베이스 연결 실패")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/ingest", response_model=NexusResponse)
async def ingest(req: IngestRequest, principal: Principal = Depends(get_principal)) -> NexusResponse:
    """문서 인덱싱 (통합 파이프라인: Collect → Classify → Chunk → BM25 → Vector → Graph)."""
    req.tenant, _ = effective_scope(principal, req.tenant, None)  # writes are tenant-bound
    try:
        result = await run_ingest(
            docs_path=req.path,
            force=req.force,
            tenant=req.tenant,
        )
        return NexusResponse(
            data={
                "total_files": result.total_files,
                "indexed": result.indexed,
                "skipped": result.skipped,
                "quarantined": result.quarantined,
                "failed": result.failed,
                "bm25_indexed": result.bm25_indexed,
                "vector_indexed": result.vector_indexed,
                "edges_created": result.edges_created,
                "errors": result.errors,
            },
        )
    except FileNotFoundError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/upload", response_model=NexusResponse)
async def upload(
    file: UploadFile = File(...),
    path: str = Query(default="uploads", description="저장 경로"),
    tenant: str = Query(default="default"),
    principal: Principal = Depends(get_principal),
) -> NexusResponse:
    """비개발자용 Markdown 파일 업로드 + 자동 인덱싱."""
    tenant, _ = effective_scope(principal, tenant, None)  # writes are tenant-bound
    from pathlib import Path

    # Markdown만 허용
    if not file.filename or not file.filename.endswith(".md"):
        raise HTTPException(status_code=400, detail="Markdown (.md) 파일만 업로드 가능합니다.")

    save_dir = Path(path)
    save_dir.mkdir(parents=True, exist_ok=True)
    save_path = save_dir / file.filename

    # 중복 확인
    if save_path.exists():
        raise HTTPException(status_code=409, detail=f"파일이 이미 존재합니다: {file.filename}")

    # 파일 저장
    content = await file.read()
    try:
        content_str = content.decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="UTF-8 인코딩이 아닙니다.")

    save_path.write_text(content_str, encoding="utf-8")

    # 인덱싱 실행
    try:
        result = await run_ingest(
            docs_path=str(save_dir),
            force=True,
            tenant=tenant,
        )

        from nexus.rid import doc_rid as make_doc_rid
        canonical_uri = f"{tenant}:{file.filename}"
        d_rid = make_doc_rid(canonical_uri)

        return NexusResponse(
            data={
                "doc_rid": d_rid,
                "source_uri": canonical_uri,
                "indexed": result.indexed > 0,
                "quarantined": result.quarantined > 0,
                "message": f"파일 업로드 및 인덱싱 완료: {file.filename}",
            },
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/graph/{entity_rid_param}", response_model=NexusResponse)
async def get_graph(
    entity_rid_param: str,
    hops: int = Query(default=1, ge=1, le=2),
    tenant: str = Query(default="default"),
    classification_max: str = Query(default="INTERNAL"),
    include_evidence: bool = Query(default=True),
    principal: Principal = Depends(get_principal),
) -> NexusResponse:
    """엔티티 관계 그래프 조회.

    entity_rid_param은 rid (ent_로 시작) 또는 엔티티 이름을 받는다.
    이름으로 전달 시 내부에서 rid를 변환한다.
    """
    tenant, classification_max = effective_scope(principal, tenant, classification_max)
    try:
        pool = await db.get_pool()
        graph_repo = PostgresGraphRepository(pool)

        # 이름 기반 조회 지원: rid가 아니면 이름→rid 변환
        rid = entity_rid_param
        if not entity_rid_param.startswith("ent_"):
            # 이름으로 entity 검색
            row = await db.fetch_one(
                "SELECT rid FROM entities WHERE name = $1 AND tenant = $2 AND status = 'active'",
                entity_rid_param, tenant,
            )
            if not row:
                # canonicalize 후 재시도
                canonical = canonicalize_entity_name(entity_rid_param, "Service")
                rid = entity_rid(tenant, "Service", canonical)
            else:
                rid = row["rid"]

        subgraph = await graph_repo.get_neighbors(
            rid, hops=hops, tenant=tenant, clearance=classification_max)

        if not subgraph.edges and not subgraph.observed_edges:
            raise HTTPException(status_code=404, detail="엔티티를 찾을 수 없습니다.")

        # 엔티티 상세 정보 조회
        entity_row = await db.fetch_one(
            "SELECT rid, name, entity_type, aliases, description FROM entities WHERE rid = $1",
            rid,
        )
        center_entity = {
            "rid": subgraph.center_rid,
            "name": subgraph.center_name,
        }
        if entity_row:
            center_entity.update({
                "type": entity_row["entity_type"],
                "aliases": list(entity_row["aliases"] or []),
                "description": entity_row["description"] or "",
            })

        # Edge별 evidence 조회
        edge_data = []
        for e in subgraph.edges:
            evidence_snippets = []
            if include_evidence:
                # base_filter 를 증거 청크에도 강제(SPEC-nexus-graph-scope-filter §4.3):
                # 스코프 밖 청크의 chunk_text 가 그래프 증거로 새지 않게 한다. INNER JOIN + 필터라
                # 스코프 밖(또는 backing chunk 없는) 증거는 배제된다.
                evi_rows = await db.fetch_all(
                    """
                    SELECT ev.note, c.chunk_text, c.section_path, d.title as doc_title
                    FROM evidence ev
                    JOIN chunks c ON ev.evidence_rid = c.rid
                    JOIN documents d ON c.doc_rid = d.rid
                    WHERE ev.subject_rid = $1 AND ev.status = 'active'
                      AND c.tenant = $2 AND c.classification <= $3::classification_level
                      AND c.is_quarantined = false AND c.status = 'active'
                      AND d.status = 'active'
                    """,
                    e.rid, tenant, classification_max,
                )
                for er in evi_rows:
                    snippet_text = er["chunk_text"][:200] if er["chunk_text"] else ""
                    evidence_snippets.append({
                        "doc_title": er["doc_title"] or "",
                        "section_path": er["section_path"] or "",
                        "text": snippet_text,
                        "note": er["note"] or "",
                    })
            edge_data.append({
                "rid": e.rid, "edge_type": e.edge_type,
                "from_rid": e.from_rid, "from_name": e.from_name,
                "to_rid": e.to_rid, "to_name": e.to_name,
                "confidence": e.confidence, "hop": e.hop,
                "evidence": evidence_snippets,
            })

        return NexusResponse(
            data={
                "center_entity": center_entity,
                "edges": edge_data,
                "observed_edges": [
                    {
                        "rid": o.rid, "edge_type": o.edge_type,
                        "from_name": o.from_name, "to_name": o.to_name,
                        "call_count": o.call_count, "error_rate": o.error_rate,
                        "latency_p95": o.latency_p95,
                        "sample_trace_ids": o.sample_trace_ids,
                        "trace_query_ref": o.trace_query_ref,
                    }
                    for o in subgraph.observed_edges
                ],
            },
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/diff", response_model=NexusResponse)
async def get_diff(
    tenant: str = Query(default="default"),
    flag_filter: str | None = Query(default=None),
    entity_filter: str | None = Query(default=None, description="특정 엔티티 관련 diff만 조회"),
    principal: Principal = Depends(get_principal),
) -> NexusResponse:
    """설계-관측 diff 보고서 (evidence 포함)."""
    tenant, _ = effective_scope(principal, tenant, None)
    try:
        report = await run_diff(tenant=tenant, flag_filter=flag_filter)

        diffs_with_evidence = []
        for d in report.diffs:
            # entity_filter 적용: 특정 엔티티 관련 diff만 반환
            if entity_filter and entity_filter not in (d.from_name, d.to_name):
                continue
            item: dict = {
                "flag": d.flag,
                "edge_rid": d.edge_rid,
                "observed_edge_rid": d.observed_edge_rid,
                "from_name": d.from_name,
                "to_name": d.to_name,
                "edge_type": d.edge_type,
                "detail": d.detail,
                "designed_evidence": [],
                "observed_evidence": [],
            }

            # 설계 edge의 evidence (chunk snippet)
            if d.edge_rid:
                evi_rows = await db.fetch_all(
                    """
                    SELECT c.chunk_text, c.section_path, d.title as doc_title
                    FROM evidence ev
                    LEFT JOIN chunks c ON ev.evidence_rid = c.rid
                    LEFT JOIN documents d ON c.doc_rid = d.rid
                    WHERE ev.subject_rid = $1 AND ev.status = 'active'
                    """,
                    d.edge_rid,
                )
                for er in evi_rows:
                    item["designed_evidence"].append({
                        "doc_title": er["doc_title"] or "",
                        "section_path": er["section_path"] or "",
                        "text": (er["chunk_text"] or "")[:200],
                    })

            # 관측 edge의 evidence (trace ref)
            if d.observed_edge_rid:
                obs_row = await db.fetch_one(
                    "SELECT sample_trace_ids, trace_query_ref FROM observed_edges WHERE rid = $1",
                    d.observed_edge_rid,
                )
                if obs_row:
                    item["observed_evidence"] = {
                        "sample_trace_ids": list(obs_row["sample_trace_ids"] or []),
                        "trace_query_ref": obs_row["trace_query_ref"] or "",
                    }

            diffs_with_evidence.append(item)

        return NexusResponse(
            data={
                "total_designed_edges": report.total_designed,
                "total_observed_edges": report.total_observed,
                "diffs": diffs_with_evidence,
                "generated_at": report.generated_at,
            },
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# /supersede 와 /documents 는 nexus.documents.api 라우터로 이전했다.
# 여기 남겨두면 FastAPI 가 먼저 등록된 이 라우트를 쓰고, capability 게이트와
# 새 필터/출처 필드가 조용히 무시된다 (SPEC-nexus-document-lifecycle §4.4).

@app.post("/otel/aggregate", response_model=NexusResponse)
async def otel_aggregate(req: OtelAggregateRequest, principal: Principal = Depends(get_principal)) -> NexusResponse:
    """OTel 집계 실행."""
    req.tenant, _ = effective_scope(principal, req.tenant, None)  # writes are tenant-bound
    try:
        result = await run_otel_aggregation(
            window_minutes=req.window_minutes,
            lookback_minutes=req.lookback_minutes,
            tenant=req.tenant,
        )
        return NexusResponse(
            data={
                "edges_created": result.edges_created,
                "edges_updated": result.edges_updated,
                "unresolved_services": result.unresolved_services,
                "timing_ms": result.timing_ms,
            },
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/search/answer/stream")
async def search_answer_stream(req: AnswerRequest, principal: Principal = Depends(get_principal)) -> StreamingResponse:
    """검색 + LLM 스트리밍 답변 (SSE). 2.0 UI용."""
    req.tenant, req.classification_max = effective_scope(principal, req.tenant, req.classification_max)
    if not req.query.strip():
        raise HTTPException(status_code=400, detail="쿼리가 비어있습니다.")

    # 스트림을 열면 헤더가 나가고 400 을 줄 수 없다. 그래서 그 전에 검증한다.
    _validate_route(req.route)

    async def event_stream():
        import json
        import time
        t0 = time.time()                      # 신호 latency 시작점(핸들러 진입~done 신호 조립)

        try:
            config = _load_config()
            embedding_svc = embedding_service_from_config(config)
            llm_svc = LLMService()
            pool = await db.get_pool()
            graph_repo = PostgresGraphRepository(pool)

            # 엔티티 감지
            gazetteer = _load_gazetteer()
            patterns = _build_entity_patterns(gazetteer)
            detected = find_entities_in_text(req.query, patterns)
            entity_rids = [
                entity_rid(req.tenant, e.entity_type, e.name)
                for e in detected
            ]

            route = determine_route(req.query, req.route, [e.name for e in detected])

            # 검색 (검색 완료 시 evidence 먼저 전송)
            search_result = await hybrid_search(
                query=req.query,
                tenant=req.tenant,
                clearance=req.classification_max,
                top_k=req.top_k,
                embedding_svc=embedding_svc,
                graph_repo=graph_repo,
                route=route,
                entity_rids=entity_rids,
                config=config,
            )

            packet = assemble_packet(search_result.hits, search_result.graph)

            # 1) evidence 이벤트 전송 — 신선도(staleness) 판정 포함
            from datetime import datetime, timezone
            _snips = [
                {
                    "chunk_rid": s.chunk_rid,
                    "doc_title": s.doc_title,
                    "section_path": s.section_path,
                    "source_uri": s.source_uri,
                    "text": s.text,
                    "score": s.score,
                    "doc_type": s.doc_type,
                    "updated_at": s.updated_at,
                }
                for s in packet.snippets
            ]
            _snips, n_stale = annotate_staleness(_snips, datetime.now(timezone.utc), _load_staleness_ttl())
            for _sn in _snips:
                _ua = _sn.get("updated_at")
                _sn["updated_at"] = _ua.isoformat() if _ua else None
            evidence_data = {
                "evidence_snippets": _snips,
                "provenance": [
                    {"doc_rid": p.doc_rid, "source_uri": p.source_uri,
                     "source_version": p.source_version, "doc_title": p.doc_title}
                    for p in packet.provenance
                ],
                "route_used": route,
                # 근거와 같은 이벤트에 실린다 — 근거가 왜 이것뿐인지를 설명하는 사실이라
                # 답변보다 먼저 도착해야 한다.
                "degraded": search_result.degraded,
            }
            yield f"event: evidence\ndata: {json.dumps(evidence_data, ensure_ascii=False)}\n\n"

            # 2) graph 이벤트 전송
            if search_result.graph:
                graph_data = {
                    "center": search_result.graph.center_name,
                    "designed_edges": [
                        {"type": e.edge_type, "from": e.from_name, "to": e.to_name, "confidence": e.confidence}
                        for e in search_result.graph.edges
                    ],
                    "observed_edges": [
                        {"type": o.edge_type, "from": o.from_name, "to": o.to_name,
                         "call_count": o.call_count, "error_rate": o.error_rate}
                        for o in search_result.graph.observed_edges
                    ],
                }
                yield f"event: graph\ndata: {json.dumps(graph_data, ensure_ascii=False)}\n\n"

            # 3) LLM 스트리밍 답변 — 청크를 누적해 완료 후 인용을 검증한다.
            answer_parts: list[str] = []
            llm_failed = False
            usage_out: list = []
            if not packet.snippets:
                _payload = json.dumps({'text': '제공된 문서에서 해당 정보를 찾을 수 없습니다.'}, ensure_ascii=False)
                yield f"event: answer_delta\ndata: {_payload}\n\n"
            elif not llm_svc.configured:
                # 미설정(키 없음): 일시적 오류가 아니라 행동지침을 준다. 근거는 이미 위에서 전송됨.
                _payload = json.dumps({'text': LLM_NOT_CONFIGURED_NOTICE}, ensure_ascii=False)
                yield f"event: answer_delta\ndata: {_payload}\n\n"
            else:
                evidence_text = format_for_llm(packet)
                user_prompt = build_user_prompt(req.query, evidence_text)

                try:
                    async for chunk in llm_svc.stream(SYSTEM_PROMPT, user_prompt, usage_out=usage_out):
                        answer_parts.append(chunk)
                        yield f"event: answer_delta\ndata: {json.dumps({'text': chunk}, ensure_ascii=False)}\n\n"
                except Exception:
                    llm_failed = True
                    _payload = json.dumps(
                        {'text': '답변을 생성할 수 없습니다. 위 근거를 직접 확인해주세요.'}, ensure_ascii=False)
                    yield f"event: answer_delta\ndata: {_payload}\n\n"

            # 4) 완료 이벤트 — 누적 답변의 인용·숫자를 근거와 대조해 함께 실어 보낸다.
            full_answer = "".join(answer_parts)
            report = validate_citations(full_answer, packet)
            # evidence_text 는 위 else 분기에서만 잡히므로 여기서 안전하게 재구성(멱등·저비용).
            nreport = validate_numbers(full_answer, format_for_llm(packet), req.query)

            # 신호 기록은 done yield **전**에 — 클라이언트가 끊기면 제너레이터가 마지막 yield 뒤로
            # 재개 안 될 수 있어 '뒤에서' 기록하면 조용히 누락된다(fire-and-forget 이라 지연 없음).
            has_answer = bool(packet.snippets) and llm_svc.configured
            _u = usage_out[0] if usage_out else None   # 성공 완료 시 Usage(토큰 None 가능), 실패 시 없음
            sig = extract_signals(
                search_result, None, path="search_answer_stream",
                tenant=req.tenant, clearance=req.classification_max, query=req.query,
                n_entities=len(entity_rids), latency_ms=int((time.time() - t0) * 1000),
                n_citations=len(report.citations) if has_answer else None,
                unverified_citations=report.unverified_count if has_answer else None,
                llm_failed=llm_failed,
                prompt_tokens=_u.input_tokens if _u else None,
                completion_tokens=_u.output_tokens if _u else None,
                cost_usd=_u.cost_usd if _u else None,
            )
            await record_search(sig, judge_input=JudgeInput(
                query=req.query, evidence=evidence_text,
                config=_load_config(), llm_svc=llm_svc) if has_answer else None)

            done_data = {
                "timing_ms": search_result.timing_ms,
                "citations": [
                    {"title": c.title, "section": c.section, "verified": c.verified}
                    for c in report.citations
                ],
                "unverified_citations": report.unverified_count,
                "unverified_numbers": nreport.unverified_count,
                "usage": (lambda u: {"input_tokens": u.input_tokens, "output_tokens": u.output_tokens,
                                     "cost_usd": u.cost_usd, "model": u.model})(usage_out[0])
                         if usage_out else None,
                "n_stale": n_stale,
            }
            yield f"event: done\ndata: {json.dumps(done_data, ensure_ascii=False)}\n\n"

        except Exception as e:
            yield f"event: error\ndata: {json.dumps({'error': str(e)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/entities/suggest", response_model=NexusResponse)
async def suggest_entities(
    q: str = Query(..., min_length=1, description="엔티티 검색어"),
    tenant: str = Query(default="default"),
    limit: int = Query(default=10, ge=1, le=50),
    principal: Principal = Depends(get_principal),
) -> NexusResponse:
    """엔티티 자동완성. UI 검색창에서 사용."""
    tenant, _ = effective_scope(principal, tenant, None)
    try:
        rows = await db.fetch_all(
            """
            SELECT rid, name, entity_type, aliases, description
            FROM entities
            WHERE status = 'active' AND tenant = $1
              AND (
                name ILIKE $2
                OR $3 = ANY(aliases)
                OR name % $4
              )
            ORDER BY similarity(name, $4) DESC
            LIMIT $5
            """,
            tenant, f"%{q}%", q, q, limit,
        )
        return NexusResponse(
            data=[
                {
                    "rid": r["rid"],
                    "name": r["name"],
                    "type": r["entity_type"],
                    "aliases": list(r["aliases"] or []),
                    "description": r["description"] or "",
                }
                for r in rows
            ],
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/claims/value", response_model=NexusResponse)
async def claim_value(
    concept: str = Query(..., min_length=1, description="개념 (예: Basic)"),
    tenant: str = Query(default="default"),
    classification_max: str = Query(default="INTERNAL"),
    principal: Principal = Depends(get_principal),
) -> NexusResponse:
    """Archon — 개념의 도메인 값(불변식) 현재값을 코드 상수에서 읽어 신뢰등급·신선도와 함께 반환."""
    tenant, classification_max = effective_scope(principal, tenant, classification_max)
    from nexus.claims.repository import ClaimRepository
    from nexus.claims.value_query import ValueQueryService
    from nexus.index.code_source import CodeValueResolver

    config = _load_config()
    repo_path = config.get("code_source", {}).get("repo_path", "")
    svc = ValueQueryService(ClaimRepository(await db.get_pool()), CodeValueResolver(repo_path))
    answers = await svc.query_value(concept, tenant, classification_max)
    return NexusResponse(
        data=[
            {
                "claim_id": a.claim_id, "statement": a.statement, "value": a.value,
                "source": a.source, "confidence": a.confidence, "fresh": a.fresh,
                "drifted": a.drifted, "note": a.note,
            }
            for a in answers
        ]
    )


@app.get("/claims/grade-authority", response_model=NexusResponse)
async def grade_authority_endpoint(
    enum_name: str = Query(default="GradeType"),
    subpath: str = Query(default=""),
    principal: Principal = Depends(get_principal),
) -> NexusResponse:
    """Archon — 등급 계층 권한을 코드 게이트에서 라이브 도출 (tree-sitter 무료, CodeQL 불필요).

    값 조회와 동일하게 조회 시점에 코드를 읽어 도출(드리프트 0). 영속화 안 함.
    """
    from nexus.claims.grade_authority import grade_authority as derive
    from nexus.index.gate_source import extract_gates, extract_grade_levels

    config = _load_config()
    repo = config.get("code_source", {}).get("repo_path", "")
    levels = extract_grade_levels(repo, enum_name)
    gates = extract_gates(repo, subpath)
    cap = derive(gates, levels)
    return NexusResponse(
        data={
            "levels": levels,
            "fixed_gates": [
                {"action": f"{g.class_name}.{g.method}", "check": g.check,
                 "grade": g.grade, "guard": g.guard}
                for g in gates
                if g.kind == "fixed"
            ],
            "relative_gate_count": sum(1 for g in gates if g.kind == "relative"),
            "capabilities": cap,
        }
    )


async def _embed_backend_health(svc) -> tuple[bool, str | None]:
    """(붙는가, 리비전). **2초에 끊는다** — `/status` 는 사이드카가 뜨는 중일 때 읽는 화면이고,
    그때 멈추면 진단 도구가 장애의 일부가 된다 (SPEC-nexus-embedding-cutover-seam §4.5).

    리비전은 사이드카에만 있다. Ollama 경로에서는 `null` 이고, 그게 그 필드의 계약이다 —
    은퇴하는 세대의 provenance 를 여기서 만들지 않는다.
    """
    import httpx

    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            if svc.backend == "sidecar":
                resp = await client.get(f"{svc.base_url}/health")
                if resp.status_code != 200:
                    return False, None
                body = resp.json()
                return bool(body.get("ready")), body.get("revision")
            resp = await client.get(f"{svc.base_url}/api/tags")
            return resp.status_code == 200, None
    except Exception:       # noqa: BLE001 — 못 붙는 것도 상태다
        return False, None


@app.get("/status", response_model=NexusResponse)
async def status() -> NexusResponse:
    """시스템 상태 확인."""
    import httpx
    import os

    config = _load_config()
    data: dict[str, Any] = {}

    # Auth posture — only the mode + anonymous flag (never origins/principals/hashes).
    # Lets the UI surface a "PUBLIC-only (anonymous)" banner when permissive.
    _auth = _auth_config()
    data["auth_mode"] = _auth.mode
    data["anonymous"] = _auth.permissive

    # DB
    data["db_connected"] = await db.check_connection()

    # Ollama
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(
                f"{os.getenv('OLLAMA_URL', 'http://localhost:11434')}/api/tags"
            )
            data["ollama_connected"] = resp.status_code == 200
    except Exception:
        data["ollama_connected"] = False

    # 임베딩 세대 — 지금 이 프로세스가 무엇으로·어디에 붙어 돌고 있는가
    # (SPEC-nexus-embedding-cutover-seam §4.5). `ollama_connected` 는 뜻이 바뀌지 않는다:
    # Ollama 의 접속 가능성이고, 그게 임베딩 백엔드인지와 무관하게 보고된다. **지금 쓰는 백엔드**가
    # 살아 있는지는 아래 필드가 답한다 — 컷오버 뒤에도 옛 의존성만 보고하던 것이 §1.8 의 결함이다.
    try:
        _svc = embedding_service_from_config(config)
        data["embedding_model"] = _svc.model
        data["embedding_backend"] = _svc.backend
        data["embedding_column"] = configured_column(config)
        data["embedding_backend_connected"], data["embedding_revision"] = (
            await _embed_backend_health(_svc))
    except Exception as e:      # noqa: BLE001 — 상태 조회가 세대 불일치로 죽으면 진단이 안 된다
        data["embedding_generation_error"] = str(e)

    # Tempo
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(
                f"{os.getenv('TEMPO_URL', 'http://localhost:3200')}/ready"
            )
            data["tempo_connected"] = resp.status_code == 200
    except Exception:
        data["tempo_connected"] = False

    # 통계
    if data["db_connected"]:
        try:
            # 세대 커버리지 — 집계 하나 + waiver 하나, 그 이상은 늘리지 않는다 (§2 의 경계).
            from nexus.index.embed_health import fetch_coverage_by_tenant, fetch_waived_count

            data["embedding_coverage"] = await fetch_coverage_by_tenant()
            data["embedding_waived"] = await fetch_waived_count()
        except Exception:  # noqa: BLE001 — 마이그레이션 전 DB 면 이 필드만 빠진다
            pass
        try:
            data["documents_count"] = await db.fetch_val(
                "SELECT COUNT(*) FROM documents WHERE status = 'active'"
            ) or 0
            data["chunks_count"] = await db.fetch_val(
                "SELECT COUNT(*) FROM chunks WHERE status = 'active'"
            ) or 0
            data["entities_count"] = await db.fetch_val(
                "SELECT COUNT(*) FROM entities WHERE status = 'active'"
            ) or 0
            data["edges_count"] = await db.fetch_val(
                "SELECT COUNT(*) FROM edges WHERE status = 'active'"
            ) or 0
            data["observed_edges_count"] = await db.fetch_val(
                "SELECT COUNT(*) FROM observed_edges WHERE status = 'active'"
            ) or 0
            data["quarantined_count"] = await db.fetch_val(
                "SELECT COUNT(*) FROM documents WHERE is_quarantined = true"
            ) or 0

            # 임베딩 세대 건전성 — 부분 재임베딩(mixed) 감지(SPEC-nexus-embed-generation-drift).
            from nexus.index.embed_health import embed_generation_report, fetch_embed_generations
            data["embed_generations"] = embed_generation_report(await fetch_embed_generations())

            # last_ingest_at / last_otel_aggregate_at
            data["last_ingest_at"] = await db.fetch_val(
                "SELECT MAX(updated_at) FROM documents WHERE status = 'active'"
            )
            if data["last_ingest_at"]:
                data["last_ingest_at"] = data["last_ingest_at"].isoformat()
            data["last_otel_aggregate_at"] = await db.fetch_val(
                "SELECT MAX(updated_at) FROM observed_edges WHERE status = 'active'"
            )
            if data["last_otel_aggregate_at"]:
                data["last_otel_aggregate_at"] = data["last_otel_aggregate_at"].isoformat()

            # diff_summary
            diff_rows = await db.fetch_all("SELECT diff_type, COUNT(*) as cnt FROM v_edge_diff GROUP BY diff_type")
            diff_summary = {"doc_only_count": 0, "observed_only_count": 0, "conflict_count": 0}
            for row in diff_rows:
                key = f"{row['diff_type']}_count"
                if key in diff_summary:
                    diff_summary[key] = row["cnt"]
            data["diff_summary"] = diff_summary
        except Exception:
            pass

    return NexusResponse(data=data)


# ── Web UI 서빙 ──

@app.get("/")
async def serve_ui():
    """Web UI SPA 진입점."""
    from pathlib import Path
    ui_path = Path(__file__).parent / "web" / "index.html"
    if not ui_path.exists():
        raise HTTPException(status_code=404, detail="Web UI가 설치되지 않았습니다.")
    return FileResponse(str(ui_path))


# Static 파일 마운트 (모든 API 라우트 이후에 위치해야 함)
# noqa 사유: catch-all "/static" 마운트는 반드시 모든 라우트 정의 이후여야 하므로
# 이 import는 의도적으로 파일 하단에 위치한다.
from pathlib import Path as _Path  # noqa: E402
_web_dir = _Path(__file__).parent / "web"
if _web_dir.exists():
    app.mount("/static", StaticFiles(directory=str(_web_dir)), name="static")
