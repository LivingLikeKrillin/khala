"""Typer CLI.

커맨드라인에서 Khala의 기능을 사용할 수 있게 한다.
Agent/개발자가 직접 호출하는 인터페이스.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import typer
import yaml

app = typer.Typer(
    name="khala",
    help="Khala — Enterprise RAG + GraphRAG CLI",
    no_args_is_help=True,
)


def _run(coro):
    """Async 함수를 sync에서 실행."""
    return asyncio.run(coro)


def _load_config(config_path: str = "config.yaml") -> dict:
    p = Path(config_path)
    if not p.exists():
        return {}
    with open(p, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


@app.command()
def ingest(
    path: str = typer.Argument(..., help="인덱싱할 문서 폴더 경로"),
    force: bool = typer.Option(False, "--force", "-f", help="해시 무시, 전체 재인덱싱"),
    tenant: str = typer.Option("default", "--tenant", "-t", help="테넌트 ID"),
    config_path: str = typer.Option("config.yaml", "--config", "-c"),
    index: bool = typer.Option(True, "--index/--no-index", help="BM25/Vector 인덱싱 수행"),
    extract_graph: bool = typer.Option(True, "--graph/--no-graph", help="Graph 추출 수행"),
) -> None:
    """문서 인덱싱 (통합 파이프라인: Collect → Classify → Chunk → BM25 → Vector → Graph)."""

    async def _ingest() -> None:
        from khala.ingest.pipeline import run_ingest
        from khala import db

        result = await run_ingest(
            docs_path=path,
            force=force,
            tenant=tenant,
            config_path=config_path,
            skip_index=not index,
            skip_graph=not extract_graph,
        )

        typer.echo(f"총 파일: {result.total_files}")
        typer.echo(f"인덱싱: {result.indexed}")
        typer.echo(f"스킵: {result.skipped}")
        typer.echo(f"격리: {result.quarantined}")
        typer.echo(f"실패: {result.failed}")

        if result.bm25_indexed or result.vector_indexed:
            typer.echo(f"\nBM25: {result.bm25_indexed}  Vector: {result.vector_indexed}")
        if result.edges_created:
            typer.echo(f"Graph edges: {result.edges_created}")

        if result.errors:
            typer.echo("\n실패 목록:")
            for err in result.errors:
                typer.echo(f"  - [{err['stage']}] {err['file_path']}: {err['error']}")

        await db.close_pool()

    _run(_ingest())


@app.command()
def query(
    q: str = typer.Argument(..., help="검색 쿼리"),
    top_k: int = typer.Option(10, "--top-k", "-k"),
    route: str = typer.Option("auto", "--route", "-r"),
    tenant: str = typer.Option("default", "--tenant", "-t"),
    answer: bool = typer.Option(True, "--answer/--no-answer", help="LLM 답변 생성"),
) -> None:
    """검색 + 답변 생성."""

    async def _query() -> None:
        from khala import db
        from khala.index.graph_extractor import (
            _build_entity_patterns, _load_gazetteer, find_entities_in_text,
        )
        from khala.llm.answer import generate_answer
        from khala.providers.embedding import EmbeddingService
        from khala.providers.llm import LLMService
        from khala.repositories.graph import PostgresGraphRepository
        from khala.rid import entity_rid
        from khala.search.evidence_packet import assemble_packet
        from khala.search.hybrid import hybrid_search
        from khala.search.router import determine_route

        config = _load_config()
        embedding_svc = EmbeddingService()
        pool = await db.get_pool()
        graph_repo = PostgresGraphRepository(pool)

        # 엔티티 감지
        gazetteer = _load_gazetteer()
        patterns = _build_entity_patterns(gazetteer)
        detected = find_entities_in_text(q, patterns)
        entity_rids = [
            entity_rid(tenant, e.entity_type, e.name)
            for e in detected
        ]

        route_used = determine_route(q, route, [e.name for e in detected])

        # 검색
        result = await hybrid_search(
            query=q, tenant=tenant, clearance="INTERNAL",
            top_k=top_k, embedding_svc=embedding_svc,
            graph_repo=graph_repo, route=route_used,
            entity_rids=entity_rids, config=config,
        )

        typer.echo(f"\n검색 경로: {result.route_used}")
        typer.echo(f"결과: {len(result.hits)}건 ({result.timing_ms.get('total_ms', 0)}ms)\n")

        for i, hit in enumerate(result.hits, 1):
            typer.echo(f"[{i}] {hit.doc_title} > {hit.section_path} (score: {hit.score:.4f})")
            typer.echo(f"    {hit.snippet[:100]}...")
            typer.echo()

        # LLM 답변
        if answer and result.hits:
            typer.echo("─" * 60)
            typer.echo("답변 생성 중...\n")
            packet = assemble_packet(result.hits, result.graph)
            llm_svc = LLMService()
            answer_result = await generate_answer(
                query=q, packet=packet, llm_svc=llm_svc,
                route_used=route_used, timing_ms=result.timing_ms,
            )
            typer.echo(answer_result.answer)
            typer.echo(f"\n({answer_result.timing_ms.get('llm_ms', '?')}ms)")

        await db.close_pool()

    _run(_query())


@app.command()
def graph(
    entity: str = typer.Argument(..., help="엔티티 이름 또는 rid"),
    hops: int = typer.Option(1, "--hops", "-h", min=1, max=2),
    tenant: str = typer.Option("default", "--tenant", "-t"),
) -> None:
    """엔티티 관계 그래프 조회."""

    async def _graph() -> None:
        from khala import db
        from khala.repositories.graph import PostgresGraphRepository
        from khala.rid import canonicalize_entity_name, entity_rid

        pool = await db.get_pool()
        graph_repo = PostgresGraphRepository(pool)

        # rid로 직접 전달되었는지 확인
        if entity.startswith("ent_"):
            rid = entity
        else:
            # 이름으로 rid 생성 (Service 타입 기본)
            canonical = canonicalize_entity_name(entity, "Service")
            rid = entity_rid(tenant, "Service", canonical)

        subgraph = await graph_repo.get_neighbors(rid, hops=hops)

        typer.echo(f"\n엔티티: {subgraph.center_name} ({subgraph.center_rid})")
        typer.echo(f"  Hops: {hops}\n")

        if subgraph.edges:
            typer.echo("설계 관계 (Designed):")
            for e in subgraph.edges:
                typer.echo(f"  [{e.edge_type}] {e.from_name} → {e.to_name} (confidence: {e.confidence:.2f}, hop: {e.hop})")
        else:
            typer.echo("설계 관계: 없음")

        typer.echo()

        if subgraph.observed_edges:
            typer.echo("관측 관계 (Observed):")
            for o in subgraph.observed_edges:
                typer.echo(
                    f"  [{o.edge_type}] {o.from_name} → {o.to_name} "
                    f"(calls: {o.call_count}, error: {o.error_rate:.2%}, p95: {o.latency_p95}ms)"
                )
        else:
            typer.echo("관측 관계: 없음")

        await db.close_pool()

    _run(_graph())


@app.command("otel-aggregate")
def otel_aggregate(
    window: int = typer.Option(5, "--window", "-w", help="집계 윈도우 (분)"),
    lookback: int = typer.Option(60, "--lookback", "-l", help="조회 기간 (분)"),
    tenant: str = typer.Option("default", "--tenant", "-t"),
) -> None:
    """OTel trace 집계."""

    async def _aggregate() -> None:
        from khala.otel.aggregator import run_otel_aggregation
        from khala import db

        result = await run_otel_aggregation(
            window_minutes=window,
            lookback_minutes=lookback,
            tenant=tenant,
        )

        typer.echo(f"생성/갱신된 edge: {result.edges_created}")
        if result.unresolved_services:
            typer.echo(f"미해석 서비스: {', '.join(result.unresolved_services)}")
        typer.echo(f"소요 시간: {result.timing_ms}ms")

        await db.close_pool()

    _run(_aggregate())


@app.command()
def diff(
    tenant: str = typer.Option("default", "--tenant", "-t"),
    type_filter: str = typer.Option(None, "--type", help="doc_only | observed_only | conflict"),
) -> None:
    """설계-관측 diff 보고서."""

    async def _diff() -> None:
        from khala.otel.diff_engine import run_diff
        from khala import db

        report = await run_diff(tenant=tenant, flag_filter=type_filter)

        typer.echo(f"\n설계 edge: {report.total_designed}")
        typer.echo(f"관측 edge: {report.total_observed}")
        typer.echo(f"불일치: {len(report.diffs)}건\n")

        for d in report.diffs:
            icon = {"doc_only": "📄", "observed_only": "👁", "conflict": "⚠️"}.get(d.flag, "?")
            typer.echo(f"  {icon} [{d.flag}] {d.from_name} → {d.to_name} ({d.edge_type})")
            typer.echo(f"     {d.detail}")

        await db.close_pool()

    _run(_diff())


@app.command()
def status() -> None:
    """시스템 상태 확인."""

    async def _status() -> None:
        import os
        import httpx
        from khala import db

        # DB
        db_ok = await db.check_connection()
        typer.echo(f"DB:     {'✓' if db_ok else '✗'}")

        # Ollama
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(
                    f"{os.getenv('OLLAMA_URL', 'http://localhost:11434')}/api/tags"
                )
                typer.echo(f"Ollama: {'✓' if resp.status_code == 200 else '✗'}")
        except Exception:
            typer.echo("Ollama: ✗")

        # Tempo
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(
                    f"{os.getenv('TEMPO_URL', 'http://localhost:3200')}/ready"
                )
                typer.echo(f"Tempo:  {'✓' if resp.status_code == 200 else '✗'}")
        except Exception:
            typer.echo("Tempo:  ✗")

        # 통계
        if db_ok:
            docs = await db.fetch_val("SELECT COUNT(*) FROM documents WHERE status = 'active'") or 0
            chunks = await db.fetch_val("SELECT COUNT(*) FROM chunks WHERE status = 'active'") or 0
            entities = await db.fetch_val("SELECT COUNT(*) FROM entities WHERE status = 'active'") or 0
            edges = await db.fetch_val("SELECT COUNT(*) FROM edges WHERE status = 'active'") or 0
            obs = await db.fetch_val("SELECT COUNT(*) FROM observed_edges WHERE status = 'active'") or 0
            quarantined = await db.fetch_val("SELECT COUNT(*) FROM documents WHERE is_quarantined = true") or 0

            typer.echo(f"\n문서: {docs}  청크: {chunks}  엔티티: {entities}")
            typer.echo(f"설계 edge: {edges}  관측 edge: {obs}  격리: {quarantined}")

        await db.close_pool()

    _run(_status())


if __name__ == "__main__":
    app()
