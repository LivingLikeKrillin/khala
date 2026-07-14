"""Typer CLI.

커맨드라인에서 Nexus의 기능을 사용할 수 있게 한다.
Agent/개발자가 직접 호출하는 인터페이스.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import typer
import yaml

# Windows 콘솔에서 한글(UTF-8) 출력 보장 (codepage 무관)
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

app = typer.Typer(
    name="nexus",
    help="Nexus — Enterprise RAG + GraphRAG CLI",
    no_args_is_help=True,
)

# ── auth: bearer token utilities (identity layer) ──
auth_app = typer.Typer(help="인증 토큰 유틸리티 (identity layer)", no_args_is_help=True)
app.add_typer(auth_app, name="auth")


@auth_app.command("gen-token")
def auth_gen_token() -> None:
    """새 고엔트로피 bearer 토큰을 출력한다 (secrets.token_urlsafe(32))."""
    from nexus.auth import gen_token
    typer.echo(gen_token())


@auth_app.command("hash-token")
def auth_hash_token() -> None:
    """stdin으로 받은 토큰의 sha256 해시를 출력 (config의 token_sha256에 붙여넣기).

    토큰을 argv가 아닌 stdin으로 받는다 (argv는 셸 히스토리/ps에 노출되므로).
    예: nexus auth gen-token | nexus auth hash-token
    """
    from nexus.auth import hash_token
    token = sys.stdin.readline().strip()
    if not token:
        typer.echo("토큰을 stdin으로 입력하세요.", err=True)
        raise typer.Exit(code=1)
    typer.echo(hash_token(token))


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
        from nexus.ingest.pipeline import run_ingest
        from nexus import db

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


@app.command("claim-seed")
def claim_seed(
    path: str = typer.Argument("claims.yaml", help="claims.yaml 경로"),
    config_path: str = typer.Option("config.yaml", "--config", "-c"),
) -> None:
    """도메인 claim(불변식·값)을 적재. value_source의 현재 코드 hash를 스냅샷."""

    async def _seed() -> None:
        from nexus import db
        from nexus.claims.repository import ClaimRepository
        from nexus.claims.seed import seed_claims
        from nexus.index.code_source import CodeValueResolver

        cfg = _load_config(config_path)
        repo_path = cfg.get("code_source", {}).get("repo_path", "")
        pool = await db.get_pool()
        n = await seed_claims(path, ClaimRepository(pool), CodeValueResolver(repo_path))
        typer.echo(f"{n}건 적재")
        await db.close_pool()

    _run(_seed())


@app.command("claim-value")
def claim_value(
    concept: str = typer.Argument(..., help="개념(예: Basic)"),
    config_path: str = typer.Option("config.yaml", "--config", "-c"),
    tenant: str = typer.Option("default", "--tenant", "-t"),
) -> None:
    """개념의 도메인 값을 코드에서 읽어 신뢰등급·신선도와 함께 답한다."""

    async def _q() -> None:
        from nexus import db
        from nexus.claims.answer import format_value_answer
        from nexus.claims.repository import ClaimRepository
        from nexus.claims.value_query import ValueQueryService
        from nexus.index.code_source import CodeValueResolver

        cfg = _load_config(config_path)
        repo_path = cfg.get("code_source", {}).get("repo_path", "")
        svc = ValueQueryService(ClaimRepository(await db.get_pool()), CodeValueResolver(repo_path))
        answers = await svc.query_value(concept, tenant, "INTERNAL")
        typer.echo(format_value_answer(concept, answers))
        await db.close_pool()

    _run(_q())


@app.command("grade-authority")
def grade_authority_cmd(
    enum_name: str = typer.Option("GradeType", "--enum", help="등급 enum 이름"),
    subpath: str = typer.Option("", "--subpath", help="코드 하위경로로 범위 제한"),
    config_path: str = typer.Option("config.yaml", "--config", "-c"),
) -> None:
    """등급 계층의 권한을 코드 게이트에서 도출 (무료 tree-sitter AST, CodeQL 불필요)."""
    from nexus.claims.grade_authority import grade_authority as derive
    from nexus.index.gate_source import extract_gates, extract_grade_levels

    cfg = _load_config(config_path)
    repo = cfg.get("code_source", {}).get("repo_path", "")
    if not repo:
        typer.echo("config.code_source.repo_path 가 비어있습니다.")
        return
    levels = extract_grade_levels(repo, enum_name)
    gates = extract_gates(repo, subpath)
    cap = derive(gates, levels)

    typer.echo(f"등급 레벨: {levels}")
    fixed = [g for g in gates if g.kind == "fixed"]
    rel = [g for g in gates if g.kind == "relative"]
    typer.echo(f"\n고정 게이트 {len(fixed)}개 (액션 → 요구등급):")
    for g in fixed:
        typer.echo(f"  {g.class_name}.{g.method}()  [{g.check}(GradeType.{g.grade})]")
    typer.echo(f"\n상대/계층 게이트 {len(rel)}개 (동적 등급 비교)")
    typer.echo("\n등급별 차단 액션 (도출 — 확실: 고정 게이트 여집합):")
    for grade, info in cap.items():
        typer.echo(f"  {grade}({info['level']}): {info['blocked']}")
    typer.echo("\n주의: 추출은 고재현 후보. '액션가드 vs 필터' 의미확정은 확인 필요(medium).")


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
        import time
        from nexus import db
        from nexus.index.graph_extractor import (
            _build_entity_patterns, _load_gazetteer, find_entities_in_text,
        )
        from nexus.llm.answer import generate_answer
        from nexus.providers.embedding import EmbeddingService
        from nexus.providers.llm import LLMService
        from nexus.repositories.graph import PostgresGraphRepository
        from nexus.rid import entity_rid
        from nexus.search.evidence_packet import assemble_packet
        from nexus.search.hybrid import hybrid_search
        from nexus.search.router import determine_route

        _t0 = time.time()
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
        answer_result = None
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

        from nexus.search.signals import extract_signals, record_search
        sig = extract_signals(
            result, answer_result, path="cli",
            tenant=tenant, clearance="INTERNAL", query=q,
            n_entities=len(entity_rids),
            latency_ms=int((time.time() - _t0) * 1000),
        )
        await record_search(sig, await_persist=True)   # close_pool 이전에 적재 완료
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
        from nexus import db
        from nexus.repositories.graph import PostgresGraphRepository
        from nexus.rid import canonicalize_entity_name, entity_rid

        pool = await db.get_pool()
        graph_repo = PostgresGraphRepository(pool)

        # rid로 직접 전달되었는지 확인
        if entity.startswith("ent_"):
            rid = entity
        else:
            # 이름으로 rid 생성 (Service 타입 기본)
            canonical = canonicalize_entity_name(entity, "Service")
            rid = entity_rid(tenant, "Service", canonical)

        # CLI 는 clearance 개념이 없다(SPEC §4.4) — 로컬 운영자 상한 INTERNAL 고정.
        subgraph = await graph_repo.get_neighbors(
            rid, hops=hops, tenant=tenant, clearance="INTERNAL")

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
        from nexus.otel.aggregator import run_otel_aggregation
        from nexus import db

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
        from nexus.otel.diff_engine import run_diff
        from nexus import db

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
        from nexus import db

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

            # 임베딩 세대 건전성(SPEC-nexus-embed-generation-drift) — 부분 재임베딩 경고.
            from nexus.index.embed_health import embed_generation_report, fetch_embed_generations
            eg = embed_generation_report(await fetch_embed_generations())
            if eg["generations"]:
                dist = "  ".join(f"{g['model']}={g['count']}" for g in eg["generations"])
                typer.echo(f"임베딩 세대: {dist}")
                if eg["mixed"]:
                    models = ", ".join(g["model"] for g in eg["generations"])
                    typer.echo(f"⚠ 혼합 임베딩 세대 {eg['distinct']}종({models}) — 부분 재임베딩일 수 있음")

        try:
            row = await db.fetch_one(
                """
                SELECT count(*) AS n,
                       avg((no_answer)::int) AS no_ans,
                       avg((graph_requested AND n_graph_edges = 0)::int) AS graph_empty,
                       percentile_disc(0.95) WITHIN GROUP (ORDER BY latency_ms) AS p95
                FROM search_log WHERE ts > now() - interval '7 days'
                """
            )
            if row and row["n"]:
                typer.echo(
                    f"검색 신호 (7d): {row['n']:,}건 · "
                    f"no-answer {float(row['no_ans'] or 0) * 100:.1f}% · "
                    f"graph-empty {float(row['graph_empty'] or 0) * 100:.1f}% · "
                    f"p95 {int(row['p95'] or 0)}ms"
                )
            else:
                typer.echo("검색 신호: 없음")
        except Exception:
            typer.echo("검색 신호: 없음")   # 구버전 DB(테이블 부재) 우아한 격하

        await db.close_pool()

    _run(_status())


@app.command()
def supersede(
    old_ref: str = typer.Argument(..., help="대체될(옛) 문서 — rid 또는 경로/URI"),
    by: str = typer.Option(..., "--by", help="대체할(새) 문서 — rid 또는 경로/URI"),
    tenant: str = typer.Option("default", "--tenant", "-t"),
) -> None:
    """옛 문서를 새 문서로 supersede(검색에서 배제). 명시적·멱등. ref = rid | 경로 | URI."""

    async def _do() -> None:
        from nexus import db
        from nexus.supersede import resolve_active_doc, supersede as _supersede

        try:
            old_rid = await resolve_active_doc(old_ref, tenant)
            new_rid = await resolve_active_doc(by, tenant)
            result = await _supersede(old_rid, new_rid, tenant)
            typer.echo(f"{old_ref} → {by}: {result}")
        except ValueError as e:
            typer.echo(f"거부: {e}", err=True)
            raise typer.Exit(1) from None
        finally:
            await db.close_pool()

    _run(_do())


# ── 문서 생애주기 — SPEC-nexus-document-lifecycle §4.6 ──

doc_app = typer.Typer(help="문서 생애주기 — 검색에서 내리고, 되돌린다.")
app.add_typer(doc_app, name="doc")

_HIDE_NOTE = "검색에서 사라집니다. 문서와 청크는 지워지지 않으며 언제든 되돌릴 수 있습니다."


def _doc_command(ref: str, tenant: str, action):
    """ref 해석 → action(rid, tenant) 실행 → 거부는 exit 1. 풀은 반드시 닫는다."""

    async def _do() -> None:
        from nexus import db
        from nexus.documents.resolve import resolve_doc

        try:
            rid = await resolve_doc(ref, tenant)
            await action(rid, tenant)
        except ValueError as e:
            typer.echo(f"거부: {e}", err=True)
            raise typer.Exit(1) from None
        finally:
            await db.close_pool()

    _run(_do())


@doc_app.command("hide")
def doc_hide(
    ref: str = typer.Argument(..., help="문서 — rid 또는 경로/URI"),
    tenant: str = typer.Option("default", "--tenant", "-t"),
) -> None:
    """문서를 검색에서 내린다. 지우지 않는다 — 언제든 restore 로 되돌린다."""

    async def _act(rid: str, tn: str) -> None:
        from nexus.documents.lifecycle_ops import AlreadySuperseded, hide_document

        try:
            result = await hide_document(rid, tn)
        except AlreadySuperseded:
            raise ValueError(
                f"{ref} 는 이미 다른 문서로 대체되었습니다(superseded). "
                f"되살리려면: nexus unsupersede {ref} --reason \"...\"") from None
        if result == "noop":
            typer.echo(f"{ref}: 이미 숨겨져 있습니다.")
            return
        typer.echo(f"{ref}: 숨겼습니다. {_HIDE_NOTE}")
        typer.echo(f"되돌리려면: nexus doc restore {ref}")

    _doc_command(ref, tenant, _act)


@doc_app.command("restore")
def doc_restore(
    ref: str = typer.Argument(..., help="문서 — rid 또는 경로/URI"),
    tenant: str = typer.Option("default", "--tenant", "-t"),
) -> None:
    """숨겼거나 Notion 에서 사라져 내려간 문서를 다시 검색에 올린다."""

    async def _act(rid: str, tn: str) -> None:
        from nexus.documents.lifecycle_ops import UseUnsupersede, restore_document

        try:
            result = await restore_document(rid, tn)
        except UseUnsupersede:
            raise ValueError(
                f"{ref} 는 다른 문서로 대체된 상태입니다(superseded). "
                f"되살리려면: nexus unsupersede {ref} --reason \"...\"") from None
        if result == "noop":
            typer.echo(f"{ref}: 이미 검색에 나타납니다.")
            return
        typer.echo(f"{ref}: 되돌렸습니다. 이 문서가 다시 검색에 나타납니다.")

    _doc_command(ref, tenant, _act)


@app.command()
def unsupersede(
    ref: str = typer.Argument(..., help="되살릴 문서 — rid 또는 경로/URI"),
    reason: str = typer.Option(..., "--reason", help="왜 되돌리는가 — 원장에 남는다"),
    tenant: str = typer.Option("default", "--tenant", "-t"),
) -> None:
    """supersession 을 취소해 옛 문서를 다시 검색에 올린다. 체인은 역순으로만 풀린다."""

    async def _act(rid: str, tn: str) -> None:
        from nexus.lifecycle import ChainBroken, unsupersede as _unsupersede

        try:
            result = await _unsupersede(rid, tn, reason=reason)
        except ChainBroken as e:
            raise ValueError(str(e)) from None
        if result == "noop":
            typer.echo(f"{ref}: superseded 상태가 아닙니다.")
            return
        typer.echo(f"{ref}: supersession 을 취소했습니다. 이 문서가 다시 검색에 나타납니다.")

    _doc_command(ref, tenant, _act)


# ── 소스 진단 — SPEC-nexus-notion-connection-health §4.5 ──

sources_app = typer.Typer(help="Notion 소스 — 연결 진단.")
app.add_typer(sources_app, name="sources")

# 테스트가 갈아끼울 수 있도록 모듈 전역으로 붙든다(전송을 주입해 모든 분기를 밟는다).
from nexus.sources.notion_health import probe_connection  # noqa: E402

_TOKEN_PROSE = {
    "ok": "정상",
    "invalid": "거부됨(401) — 폐기되었거나 잘못된 토큰입니다",
    "not_configured": "설정되지 않음 (.env 의 NOTION_TOKEN)",
    "unknown": "확인하지 못함 — Notion 에 연결할 수 없습니다",
}
_ROOT_PROSE = {
    "reachable": "도달 가능",
    "unreachable": "볼 수 없음",
    "invalid_id": "id 형식 오류",
    "unknown": "확인하지 못함",
}


@sources_app.command("health")
def sources_health(tenant: str = typer.Option("default", "--tenant", "-t")) -> None:
    """토큰이 유효한가, 등록된 root 에 정말 닿는가. 문제가 있으면 exit 1.

    동기화를 시작하기 전에 물어보라. 토큰이 죽었거나 root 가 공유되지 않았다면 걷는 일이 낭비다.
    """

    async def _do() -> bool:
        import os

        from nexus import db
        from nexus.sources import roots_store

        try:
            roots = [r["root_id"] for r in await roots_store.list_roots(tenant)]
            health = await probe_connection(os.getenv("NOTION_TOKEN", ""), roots)
        finally:
            await db.close_pool()

        t = health.token
        typer.echo(f"토큰: {_TOKEN_PROSE.get(t.state.value, t.state.value)}")
        if t.state.value == "ok":
            typer.echo(f"  integration: {t.integration} · 워크스페이스: {t.workspace}")

        if not health.roots:
            typer.echo("등록된 root 가 없습니다.")
        for r in health.roots:
            typer.echo(f"- {r.title or r.root_id}  [{_ROOT_PROSE.get(r.state.value, r.state.value)}]")
            if r.remedy:
                typer.echo(f"    {r.root_id}: {r.remedy}")

        # 초록은 '토큰 정상 + 모든 root 도달 가능' 뿐이다. 모른다는 것은 초록이 아니다.
        return t.state.value == "ok" and all(r.state.value == "reachable" for r in health.roots)

    if not _run(_do()):
        raise typer.Exit(1)


@app.command("entropy-signals")
def entropy_signals() -> None:
    """공존 잔차 신호(재수집 덮어쓰기·정확중복·제목충돌·supersession)를 표시.

    migration 001의 v_entropy_signals 뷰를 읽어 4개 신호를 출력. 전역 스냅샷
    (뷰에 tenant 컬럼 없음 — Slice 2에서 tenant/최근-윈도우 그룹핑 추가).
    """

    async def _do() -> None:
        from nexus import db

        row = await db.fetch_one("SELECT * FROM v_entropy_signals")
        for k, v in dict(row).items():
            typer.echo(f"{k}: {v}")
        await db.close_pool()

    _run(_do())


@app.command("ingest-notion")
def ingest_notion(
    tenant: str = "default",
    roots: str = typer.Option("", help="쉼표구분 Notion page id 목록"),
    token_env: str = "NOTION_TOKEN",
    since: str = typer.Option("", help="ISO8601 watermark — 이후 변경분만(증분)"),
    reconcile: bool = typer.Option(
        False, "--reconcile",
        help="Notion 에서 사라진 페이지를 soft_delete 하고 되살아난 페이지를 revive 한다",
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="--reconcile 의 계획만 출력하고 DB 는 건드리지 않는다",
    ),
    force: bool = typer.Option(
        False, "--force", help="prune 비율이 임계치를 넘어도 강행한다 (--roots 를 먼저 확인하세요)",
    ),
    threshold: float = typer.Option(
        0.5, help="prune 비율이 이 값을 넘으면 거부한다 (0.5 = 50%)",
    ),
) -> None:
    """Notion 페이지를 CSF로 변환해 S3 타입-인지 intake로 적재(Path B).

    --reconcile 을 주면 적재 뒤 재조정한다: 걸어온 root 하위에서 사라진 문서는 검색에서 내리고
    (soft_delete), 되살아난 문서는 되살린다(revive). 출처 root 가 이번 실행에 전부 포함된 문서만
    판정 대상이다 — SPEC-nexus-notion-reconciliation.
    """
    from nexus.a2a.server import _default_external_ingest_fn
    from nexus.ingest.sources.notion import NotionSource
    from nexus.ingest.sources.notion_importer import import_notion
    from nexus.ingest.sources.notion_reconcile import make_reconcile_fn

    root_list = [r.strip() for r in roots.split(",") if r.strip()]
    if not root_list:
        # --roots 미지정 → DB 에 등록된 소스를 쓴다 (SPEC-nexus-notion-source-console §4.1).
        # cron 명령에서 페이지 id 를 지우고, 오타로 코퍼스를 날릴 여지를 없앤다.
        from nexus.sources.roots_store import list_roots

        root_list = [r["root_id"] for r in asyncio.run(list_roots(tenant))]
    if not root_list:
        typer.echo(
            "등록된 Notion 소스가 없습니다. 웹 UI 의 '소스' 탭에서 추가하거나 "
            "--roots 'pageid1,pageid2' 를 주세요."
        )
        raise typer.Exit(code=1)
    if (dry_run or force) and not reconcile:
        typer.echo("--dry-run / --force 는 --reconcile 과 함께 써야 의미가 있습니다")
        raise typer.Exit(code=1)
    try:
        source = NotionSource(token_env=token_env, roots=root_list, tenant=tenant)
    except KeyError:
        typer.echo(f"환경변수 {token_env} 없음 — Notion 통합 토큰 필요")
        raise typer.Exit(code=1) from None
    except ImportError:
        typer.echo("notion-client 미설치 — `pip install nexus[notion]`")
        raise typer.Exit(code=1) from None

    reconcile_fn = (
        make_reconcile_fn(threshold=threshold, force=force, dry_run=dry_run)
        if reconcile else None
    )
    report = asyncio.run(
        # force 는 재조정 planner 뿐 아니라 **적재**까지 닿아야 한다. 안 그러면 본문이 안 바뀐
        # 페이지는 --force 를 줘도 영원히 idempotent 다 (제목 같은 파생 메타데이터가 안 고쳐진다).
        import_notion(source, tenant, _default_external_ingest_fn,
                      since=since or None, reconcile_fn=reconcile_fn, force=force)
    )
    typer.echo(
        f"ingested={report.ingested} idempotent={report.idempotent} "
        f"empty={report.empty} skipped={report.skipped} watermark={report.watermark or ''}"
    )
    if reconcile:
        typer.echo(f"pruned={report.pruned} revived={report.revived}")
        if report.refused:
            typer.echo(f"재조정 거부됨: {report.reason}")
            raise typer.Exit(code=2)
        if dry_run:
            typer.echo("dry-run — DB 는 변경되지 않았습니다")


if __name__ == "__main__":
    app()
