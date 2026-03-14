"""FastAPI 엔드포인트.

API_CONTRACT.md에 정의된 엔드포인트를 구현한다.
모든 응답은 KhalaResponse로 감싸고, 검색에는 base_filter를 적용한다.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

import yaml
from fastapi import FastAPI, HTTPException, UploadFile, File, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from khala import db
from khala.index.bm25 import tokenize_korean
from khala.index.graph_extractor import find_entities_in_text, _build_entity_patterns, _load_gazetteer
from khala.ingest.pipeline import run_ingest
from khala.llm.answer import generate_answer
from khala.llm.prompts import SYSTEM_PROMPT, build_user_prompt
from khala.otel.aggregator import run_otel_aggregation
from khala.otel.diff_engine import run_diff
from khala.providers.embedding import EmbeddingService
from khala.providers.llm import LLMService
from khala.repositories.graph import PostgresGraphRepository
from khala.rid import canonicalize_entity_name, entity_rid
from khala.search.evidence_packet import assemble_packet, format_for_llm
from khala.search.hybrid import hybrid_search
from khala.search.router import determine_route


# ── Lifespan ──
async def _bootstrap_gazetteer() -> None:
    """entities.yaml의 엔티티를 DB에 초기 등록."""
    from khala.index.graph_extractor import ensure_entity_exists, _load_gazetteer
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
    await db.get_pool()
    await _bootstrap_gazetteer()
    yield
    await db.close_pool()


app = FastAPI(title="Khala", version="0.1.0", lifespan=lifespan)

# CORS: 2.0 Web UI에서 접근 허용
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 운영 시 허용 도메인으로 제한
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Config ──
def _load_config() -> dict:
    from pathlib import Path
    p = Path("config.yaml")
    if not p.exists():
        return {}
    with open(p, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


# ── Response wrapper ──
class KhalaResponse(BaseModel):
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


# ── Endpoints ──

@app.post("/search", response_model=KhalaResponse)
async def search(req: SearchRequest) -> KhalaResponse:
    """Hybrid 검색."""
    if not req.query.strip():
        raise HTTPException(status_code=400, detail="쿼리가 비어있습니다.")

    try:
        config = _load_config()
        embedding_svc = EmbeddingService()
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

        return KhalaResponse(
            data={
                "results": [
                    {
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
                    }
                    for h in result.hits
                ],
                "graph_findings": graph_findings,
                "route_used": result.route_used,
                "timing_ms": result.timing_ms,
            },
        )
    except Exception as e:
        if "connect" in str(e).lower():
            raise HTTPException(status_code=503, detail="데이터베이스 연결 실패")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/search/answer", response_model=KhalaResponse)
async def search_answer(req: AnswerRequest) -> KhalaResponse:
    """검색 + LLM 답변 생성."""
    if not req.query.strip():
        raise HTTPException(status_code=400, detail="쿼리가 비어있습니다.")

    try:
        config = _load_config()
        embedding_svc = EmbeddingService()
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

        return KhalaResponse(
            data={
                "answer": answer_result.answer,
                "evidence_snippets": answer_result.evidence_snippets,
                "graph_findings": answer_result.graph_findings,
                "provenance": answer_result.provenance,
                "route_used": answer_result.route_used,
                "timing_ms": answer_result.timing_ms,
            },
        )
    except Exception as e:
        if "connect" in str(e).lower():
            raise HTTPException(status_code=503, detail="데이터베이스 연결 실패")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/ingest", response_model=KhalaResponse)
async def ingest(req: IngestRequest) -> KhalaResponse:
    """문서 인덱싱 (통합 파이프라인: Collect → Classify → Chunk → BM25 → Vector → Graph)."""
    try:
        result = await run_ingest(
            docs_path=req.path,
            force=req.force,
            tenant=req.tenant,
        )
        return KhalaResponse(
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


@app.post("/upload", response_model=KhalaResponse)
async def upload(
    file: UploadFile = File(...),
    path: str = Query(default="uploads", description="저장 경로"),
    tenant: str = Query(default="default"),
) -> KhalaResponse:
    """비개발자용 Markdown 파일 업로드 + 자동 인덱싱."""
    from pathlib import Path
    import aiofiles

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

        from khala.rid import doc_rid as make_doc_rid
        canonical_uri = f"{tenant}:{file.filename}"
        d_rid = make_doc_rid(canonical_uri)

        return KhalaResponse(
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


@app.get("/graph/{entity_rid_param}", response_model=KhalaResponse)
async def get_graph(
    entity_rid_param: str,
    hops: int = Query(default=1, ge=1, le=2),
    tenant: str = Query(default="default"),
    classification_max: str = Query(default="INTERNAL"),
    include_evidence: bool = Query(default=True),
) -> KhalaResponse:
    """엔티티 관계 그래프 조회.

    entity_rid_param은 rid (ent_로 시작) 또는 엔티티 이름을 받는다.
    이름으로 전달 시 내부에서 rid를 변환한다.
    """
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

        subgraph = await graph_repo.get_neighbors(rid, hops=hops)

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
                evi_rows = await db.fetch_all(
                    """
                    SELECT ev.note, c.chunk_text, c.section_path, d.title as doc_title
                    FROM evidence ev
                    LEFT JOIN chunks c ON ev.evidence_rid = c.rid
                    LEFT JOIN documents d ON c.doc_rid = d.rid
                    WHERE ev.subject_rid = $1 AND ev.status = 'active'
                    """,
                    e.rid,
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

        return KhalaResponse(
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


@app.get("/diff", response_model=KhalaResponse)
async def get_diff(
    tenant: str = Query(default="default"),
    flag_filter: str | None = Query(default=None),
    entity_filter: str | None = Query(default=None, description="특정 엔티티 관련 diff만 조회"),
) -> KhalaResponse:
    """설계-관측 diff 보고서 (evidence 포함)."""
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

        return KhalaResponse(
            data={
                "total_designed_edges": report.total_designed,
                "total_observed_edges": report.total_observed,
                "diffs": diffs_with_evidence,
                "generated_at": report.generated_at,
            },
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/otel/aggregate", response_model=KhalaResponse)
async def otel_aggregate(req: OtelAggregateRequest) -> KhalaResponse:
    """OTel 집계 실행."""
    try:
        result = await run_otel_aggregation(
            window_minutes=req.window_minutes,
            lookback_minutes=req.lookback_minutes,
            tenant=req.tenant,
        )
        return KhalaResponse(
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
async def search_answer_stream(req: AnswerRequest) -> StreamingResponse:
    """검색 + LLM 스트리밍 답변 (SSE). 2.0 UI용."""
    if not req.query.strip():
        raise HTTPException(status_code=400, detail="쿼리가 비어있습니다.")

    async def event_stream():
        import json
        import time

        try:
            config = _load_config()
            embedding_svc = EmbeddingService()
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

            # 1) evidence 이벤트 전송
            evidence_data = {
                "evidence_snippets": [
                    {
                        "chunk_rid": s.chunk_rid,
                        "doc_title": s.doc_title,
                        "section_path": s.section_path,
                        "source_uri": s.source_uri,
                        "text": s.text,
                        "score": s.score,
                    }
                    for s in packet.snippets
                ],
                "provenance": [
                    {"doc_rid": p.doc_rid, "source_uri": p.source_uri, "source_version": p.source_version}
                    for p in packet.provenance
                ],
                "route_used": route,
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

            # 3) LLM 스트리밍 답변
            if not packet.snippets:
                yield f"event: answer_delta\ndata: {json.dumps({'text': '제공된 문서에서 해당 정보를 찾을 수 없습니다.'}, ensure_ascii=False)}\n\n"
            else:
                evidence_text = format_for_llm(packet)
                user_prompt = build_user_prompt(req.query, evidence_text)

                try:
                    async for chunk in llm_svc.stream(SYSTEM_PROMPT, user_prompt):
                        yield f"event: answer_delta\ndata: {json.dumps({'text': chunk}, ensure_ascii=False)}\n\n"
                except Exception:
                    yield f"event: answer_delta\ndata: {json.dumps({'text': '답변을 생성할 수 없습니다. 위 근거를 직접 확인해주세요.'}, ensure_ascii=False)}\n\n"

            # 4) 완료 이벤트
            yield f"event: done\ndata: {json.dumps({'timing_ms': search_result.timing_ms})}\n\n"

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


@app.get("/entities/suggest", response_model=KhalaResponse)
async def suggest_entities(
    q: str = Query(..., min_length=1, description="엔티티 검색어"),
    tenant: str = Query(default="default"),
    limit: int = Query(default=10, ge=1, le=50),
) -> KhalaResponse:
    """엔티티 자동완성. UI 검색창에서 사용."""
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
        return KhalaResponse(
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


@app.get("/documents", response_model=KhalaResponse)
async def list_documents(
    tenant: str = Query(default="default"),
    classification_max: str = Query(default="INTERNAL"),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
) -> KhalaResponse:
    """인덱싱된 문서 목록 조회. UI 문서 브라우저용."""
    try:
        rows = await db.fetch_all(
            """
            SELECT d.rid, d.title, d.source_uri, d.source_version,
                   d.classification, d.doc_type, d.language,
                   d.is_quarantined, d.updated_at,
                   (SELECT COUNT(*) FROM chunks c WHERE c.doc_rid = d.rid AND c.status = 'active') as chunk_count
            FROM documents d
            WHERE d.tenant = $1
              AND d.classification <= $2::classification_level
              AND d.is_quarantined = false
              AND d.status = 'active'
            ORDER BY d.updated_at DESC
            OFFSET $3 LIMIT $4
            """,
            tenant, classification_max, offset, limit,
        )

        total = await db.fetch_val(
            """
            SELECT COUNT(*) FROM documents
            WHERE tenant = $1 AND classification <= $2::classification_level
              AND is_quarantined = false AND status = 'active'
            """,
            tenant, classification_max,
        )

        return KhalaResponse(
            data=[
                {
                    "rid": r["rid"],
                    "title": r["title"],
                    "source_uri": r["source_uri"],
                    "source_version": r["source_version"] or "",
                    "classification": r["classification"],
                    "doc_type": r["doc_type"],
                    "language": r["language"],
                    "chunk_count": r["chunk_count"],
                    "updated_at": r["updated_at"].isoformat() if r["updated_at"] else None,
                }
                for r in rows
            ],
            meta={"total": total or 0, "offset": offset, "limit": limit},
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/status", response_model=KhalaResponse)
async def status() -> KhalaResponse:
    """시스템 상태 확인."""
    import httpx
    import os

    data: dict[str, Any] = {}

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

    return KhalaResponse(data=data)
