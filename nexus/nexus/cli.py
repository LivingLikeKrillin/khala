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


@app.command("ops-map")
def ops_map(
    repo: str = typer.Argument(..., help="대상 코드 리포 체크아웃 경로"),
    out: str = typer.Option(..., "--out", "-o", help="생성한 마크다운을 쓸 폴더"),
) -> None:
    """설정 파일에서 **운영 지도** 문서를 만든다 (로그 필드 스키마 · 배포 토폴로지).

    적재는 하지 않는다 — 만든 폴더를 `nexus ingest` 에 넘겨라. 쓰기 경로를 하나로 두는 것이
    세대 게이트가 한 곳이면 되는 이유이고, 사람이 **넣기 전에 읽어 볼 기회**이기도 하다.

    실시간 수치는 담지 않는다(적재 순간 낡는다). 담는 것은 *이름*이다.
    """
    from pathlib import Path

    from nexus.ingest.sources.ops_map import generate

    docs = generate(Path(repo))
    if not docs:
        typer.echo("아는 운영 설정을 못 찾았다 (logback / docker-compose). 만든 문서 없음.")
        raise typer.Exit(0)

    out_dir = Path(out)
    out_dir.mkdir(parents=True, exist_ok=True)
    for d in docs:
        (out_dir / d.name).write_text(d.body, encoding="utf-8")
        typer.echo(f"  {d.name}  ({len(d.body):,}자)  {d.title}")
    typer.echo(f"\n{len(docs)}건 생성 → {out_dir}")
    typer.echo(f"적재: nexus ingest {out_dir} --tenant <tenant>")


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

        # 세대 불일치는 **거부**이지 크래시가 아니다 (SPEC-nexus-generation-of-record §3.2).
        # 트레이스백으로 던지면 읽는 사람이 고치는 법 대신 스택을 본다.
        from nexus.index.generation import GenerationMismatch
        try:
            result = await run_ingest(
                docs_path=path,
                force=force,
                tenant=tenant,
                config_path=config_path,
                skip_index=not index,
                skip_graph=not extract_graph,
            )
        except GenerationMismatch as e:
            typer.echo(f"\n거부: {e}", err=True)
            await db.close_pool()
            raise typer.Exit(2) from None

        typer.echo(f"총 파일: {result.total_files}")
        typer.echo(f"인덱싱: {result.indexed}")
        typer.echo(f"스킵: {result.skipped}")
        typer.echo(f"격리: {result.quarantined}")
        typer.echo(f"실패: {result.failed}")

        if result.bm25_indexed or result.vector_indexed:
            typer.echo(f"\nBM25: {result.bm25_indexed}  Vector: {result.vector_indexed}")
        if result.edges_created:
            typer.echo(f"Graph edges: {result.edges_created}")

        # 이 적재가 남긴 것 (SPEC-nexus-index-completeness §3.4). 종료코드는 바꾸지 않는다 —
        # 그 판단은 §2.4 에서 이미 내려져 있다. 프로세스가 죽으면 이 줄도 없으므로, 보장은
        # `nexus status` 쪽이다.
        if result.coverage:
            from nexus.index.vector_index import configured_column
            col = configured_column(_load_config(config_path))
            gap = result.coverage["active"] - result.coverage[col]
            if gap:
                typer.echo(f"\n⚠ 벡터 다리가 못 보는 청크 {gap}건 "
                           f"(활성 {result.coverage['active']} 중 {result.coverage[col]} 인덱싱)")
                # **이유를 여기서 말한다.** 아래 복구 명령은 이유를 모르면 같은 자리에서 같은
                # 실패를 다시 부른다 — 그 이유는 `embed_refusals` 에 이미 적혀 있었고, 읽는
                # 곳이 없었을 뿐이다.
                ref = result.refusals or {}
                for reason, n in ref.get("reasons", []):
                    typer.echo(f"  거부 {n}건: {reason}")
                hidden = ref.get("distinct", 0) - len(ref.get("reasons", []))
                if hidden > 0:
                    typer.echo(f"  … 그 밖의 이유 {hidden}종")
                if ref.get("total", 0) < gap:
                    # 거부 기록조차 없는 구멍이다. 적재 큐에 안 들어갔거나 프로세스가 중간에
                    # 죽은 모양이고, 처방이 다르다.
                    typer.echo(f"  이유가 기록되지 않은 것 {gap - ref.get('total', 0)}건 "
                               f"— 임베딩 단계에 도달조차 못 했을 수 있다")
                typer.echo(f"  복구: nexus reembed run --tenant {tenant}")

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
        from nexus.providers.embedding import embedding_service_from_config
        from nexus.providers.llm import LLMService
        from nexus.repositories.graph import PostgresGraphRepository
        from nexus.rid import entity_rid
        from nexus.search.evidence_packet import assemble_packet
        from nexus.search.hybrid import hybrid_search
        from nexus.search.router import determine_route

        _t0 = time.time()
        config = _load_config()
        embedding_svc = embedding_service_from_config(config)
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
            packet = await assemble_packet(result.hits, result.graph, tenant,
                                           fill=result.fill)
            llm_svc = LLMService()
            answer_result = await generate_answer(
                query=q, packet=packet, llm_svc=llm_svc,
                route_used=route_used, timing_ms=result.timing_ms,
                confidence=result.confidence,
            )
            typer.echo(answer_result.answer)
            typer.echo(f"\n({answer_result.timing_ms.get('llm_ms', '?')}ms)")

        from nexus.search.signals import JudgeInput, extract_signals, record_search
        sig = extract_signals(
            result, answer_result, path="cli",
            tenant=tenant, clearance="INTERNAL", query=q,
            n_entities=len(entity_rids),
            latency_ms=int((time.time() - _t0) * 1000),
        )
        # await_persist=True: close_pool 이전에 적재 완료 — CLI 는 판정도 기다린다(설계).
        # 답변을 만들지 않았으면 판정할 근거도 없다(packet/llm_svc 는 그 블록 안에서만 산다).
        _ji = None
        if answer_result is not None:
            from nexus.search.evidence_packet import format_for_llm
            _ji = JudgeInput(query=q, evidence=format_for_llm(packet),
                             config=config, llm_svc=llm_svc)
        # CLI 는 principal 이 없다 — 허용목록에 오를 수 없으므로 보존되지 않는다.
        # 도구 트래픽이 '실사용 질문' 집합을 오염시키면 이 기능의 목적이 무너진다.
        await record_search(sig, await_persist=True, judge_input=_ji, query_text=q)
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
                typer.echo(f"  [{e.edge_type}] {e.from_name} → {e.to_name} "
                           f"(confidence: {e.confidence:.2f}, hop: {e.hop})")
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
def feedback(
    days: int = typer.Option(30, "--days", help="이 기간의 👎 를 본다 (포인터는 90일에 지워진다)"),
    tenant: str = typer.Option("default", "--tenant"),
) -> None:
    """👎 목록 — 답변 품질 개선 자료 (SPEC-nexus-answer-feedback §3.7).

    **푸시는 없다.** 자료는 쌓이고 이 명령이 주기적으로 뽑는다. 월 1회 권장 — 슬랙 포인터가
    90일에 지워지므로 그보다 길게 두면 사유 코드만 남고 스레드를 못 연다.
    """

    async def _run() -> None:
        from nexus import db
        from nexus.feedback import store

        counts = await store.tally(tenant=tenant)
        typer.echo(f"제안 {counts['offered']}건 · 표받은 답변 {counts['answers_with_votes']}건"
                   f" · 제안없이 온 투표 {counts['synthesized']}건\n")
        rows = await store.recent_downvotes(tenant=tenant, days=days)
        if not rows:
            typer.echo(f"최근 {days}일 👎 없음.")
        for r in rows:
            when = r["voted_at"].strftime("%Y-%m-%d")
            why = r["reason"] or "(사유 미상)"
            where = (f"{r['channel_id']}/{r['message_ts']}" if r["channel_id"]
                     else "(포인터 만료 — 스레드를 열 수 없다)")
            typer.echo(f"  {when}  {why:16s}  {where}")
        await db.close_pool()

    asyncio.run(_run())


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

            # 임베딩 세대 건전성 — **출처 표**를 읽는다. 행 라벨(`chunks.embed_model`)은
            # 컬럼 둘을 한 칸으로 설명해서 균일한 컬럼을 혼합이라 불렀다
            # (SPEC-nexus-embedding-provenance-grain §1.3).
            from nexus.index.provenance import fetch_distribution, fetch_mismatch, summarize
            from nexus.index.vector_index import configured_column
            _col = configured_column(_load_config())
            eg = summarize(await fetch_distribution(_col))
            if eg["generations"] or eg["unknown"]:
                dist = "  ".join(f"{g['model']}={g['count']}" for g in eg["generations"])
                typer.echo(f"임베딩 세대({_col}): {dist or '(아는 것 없음)'}")
                if eg["unknown"]:
                    # 숨기면 "모른다" 와 "괜찮다" 가 같아 보인다. 이 수가 크면 아래 혼합·불일치
                    # 감지의 감도가 그만큼 낮다는 뜻이다 (SPEC §3.3·§7).
                    typer.echo(f"  출처 미상 {eg['unknown']}개 — 재임베딩해야 알게 된다")
                if eg["mixed"]:
                    models = ", ".join(g["model"] for g in eg["generations"])
                    typer.echo(f"⚠ 혼합 임베딩 세대 {eg['distinct']}종({models}) — 부분 재임베딩일 수 있음")
                try:
                    _mm = await fetch_mismatch(_col, tenant=_load_config().get("default_tenant", "default"))
                    if _mm:
                        typer.echo(f"⚠ 선언과 다른 세대의 벡터 {_mm}개 — 검색이 선언되지 않은 "
                                   f"공간에서 돈다")
                except Exception:  # noqa: BLE001 — 선언 표가 없는 배포
                    pass

            # 임베딩을 포기한 청크 — 벡터 검색에서 빠진 내용의 양이다
            # (SPEC-nexus-kure-embedding-swap §4.5). 0 이 아니면 조용히 넘어가지 않는다.
            from nexus.index.embed_health import fetch_waived_count
            try:
                waived = await fetch_waived_count()
            except Exception:      # noqa: BLE001 — 마이그레이션 전이면 테이블이 없다
                waived = 0
            if waived:
                typer.echo(f"⚠ 임베딩 포기(waived) 청크 {waived}건 — 벡터 검색에서 빠져 있음")

            # 질의 텍스트 보존 (SPEC-nexus-query-text-retention §3.3). 여기 한 줄이 없으면
            # **안 도는 purge 는 증상이 없다** — 보관 중이라는 사실도, 만료를 넘겼다는 사실도
            # 아무 화면에 안 뜬다. 켜지지 않은 배포에서는 아무것도 출력하지 않는다.
            from nexus.search.query_retention import status as retention_status
            try:
                ret = await retention_status()
            except Exception:      # noqa: BLE001 — 마이그레이션 전이면 테이블이 없다
                ret = []
            for r in ret:
                oldest = r["oldest"].date().isoformat() if r["oldest"] else "-"
                typer.echo(f"질의 보존 [{r['tenant']}] {r['stored']}건 · 최고령 {oldest}")
                if r["overdue"]:
                    typer.echo(f"  ⚠ 만료 초과 {r['overdue']}건 — `nexus query-text purge` 가 안 돌고 있다")
                if not r["has_notice"]:
                    typer.echo("  ⚠ 고지(notice_shown) 없음 — 쓰기가 거부되고 있다")
                if r.get("orphan"):
                    typer.echo("  ⚠ 옵트인 행 없이 남은 텍스트 — 철회가 절반만 됐다")

            # 인덱스 커버리지 (SPEC-nexus-index-completeness §3.2). 이 값은 이미 재고 있었지만
            # **API 기동 로그에만** 있었다 — 사람이 치는 건 이 명령이다. 51개 청크가 벡터 다리에서
            # 빠진 채 하루를 지나간 이유가 그 간극이었다.
            from nexus.index.embed_health import exempt_tenants, fetch_coverage_by_tenant
            from nexus.index.vector_index import configured_column
            try:
                config = _load_config()
                col = configured_column(config)
                exempt = exempt_tenants(config)
                coverage = await fetch_coverage_by_tenant()
            except Exception:      # noqa: BLE001 — 마이그레이션 전이면 컬럼이 없다
                coverage = []
            for row_ in [c for c in coverage if c["active"]]:
                gap = row_["active"] - row_[col]
                mark = "⚠ " if gap and row_["tenant"] not in exempt else "  "
                note = " (면제 — 일부러 비워 둔 코퍼스)" if row_["tenant"] in exempt else ""
                # 두 벡터 컬럼을 **함께** 찍는다: 옛 컬럼의 구멍이 곧 롤백이 잃을 것이다
                # (ADR-0009 의 "post-flip NULL gap" 미결 항목, §3.2).
                typer.echo(
                    f"{mark}커버리지 {row_['tenant']:<16} 활성 {row_['active']:>5}  "
                    f"{col} {row_[col]:>5}  embedding {row_['embedding']:>5}  "
                    f"bm25 {row_['bm25']:>5}{note}")
                if gap and row_["tenant"] not in exempt:
                    typer.echo(
                        f"   └ 벡터 다리가 못 보는 청크 {gap}건 — "
                        f"nexus reembed run --tenant {row_['tenant']}")
                    # 그 구멍의 **이유**. `embed_refusals` 는 백엔드 메시지를 그대로 갖고 있는데
                    # 읽는 곳이 코퍼스 뷰 하나뿐이었다 — 그래서 안내받은 재시도가 같은 이유로
                    # 다시 실패했다 (OPEN.md A7).
                    from nexus.index.embed_health import fetch_refusals
                    try:
                        ref = await fetch_refusals(col, tenant=row_["tenant"])
                    except Exception:  # noqa: BLE001 — 마이그레이션 전이면 표가 없다
                        ref = {"total": 0, "distinct": 0, "reasons": []}
                    for reason, n in ref["reasons"]:
                        typer.echo(f"      · {n}건: {reason}")
                    if ref["distinct"] > len(ref["reasons"]):
                        typer.echo(f"      · … 그 밖의 이유 {ref['distinct'] - len(ref['reasons'])}종")
                    if ref["total"] < gap:
                        typer.echo(f"      · 이유가 기록되지 않은 것 {gap - ref['total']}건 "
                                   f"— 임베딩 단계에 도달조차 못 했을 수 있다")

            # 코드 인덱스의 신원 — 문서↔코드 판정이 **어느 커밋 기준인지**. 이 줄이 없는 동안
            # 심볼 10,659개·앵커 2,674개가 라이브에 앉아 있었고, 그 판정이 언제의 코드에
            # 대한 것인지 볼 방법이 없었다. 스캔이 없는 테넌트에는 한 줄도 안 찍는다.
            from nexus.index.anchor_store import code_index_health
            try:
                code_rows = await code_index_health()
            except Exception:      # noqa: BLE001 — 마이그레이션 전이면 컬럼이 없다
                code_rows = []
            for c in code_rows:
                when = c["scanned_at"].date().isoformat() if c["scanned_at"] else "-"
                typer.echo(
                    f"  코드 인덱스 {c['tenant']:<16} {c['repo']} @{(c['scan_commit'] or '')[:12]} "
                    f"· 심볼 {c['symbol_count']:>5} · 앵커 {c['anchors']:>5} "
                    f"· 지워진 이름 {c['deleted_names']:>4} · 스캔 {when}")
                # ⚠ 는 **읽지 못한 파일에만** 건다. 선언 0 파일은 정상이라 경보를 걸면 영원히
                # 울린다 — 두 사실을 한 칸에 뭉쳐 세던 것이 migration 033 이 가른 것이다.
                if c["unreadable_files"]:
                    typer.echo(
                        f"   └ ⚠ 읽지 못한 파일 {c['unreadable_files']}건 — 그 파일의 심볼은 "
                        f"통째로 없다. 문서가 그 이름을 부르면 **없는 이름**으로 판정된다")
                elif c["unreadable_files"] is None:
                    typer.echo("   └ 이 스캔은 가르기 전이다 — 다시 스캔하면 채워진다")

            # 어떤 다리도 읽을 수 없는 문서 (SPEC-nexus-index-completeness §3.1 의 사각지대).
            # 위 커버리지는 **청크**를 세므로 청크가 0건인 문서는 모집단 밖이다 — 그래서
            # 유령 문서는 커버리지 100% 로 보인다. 그래서 `coverage` 가 아니라 이 함수의 행을
            # 직접 돈다: 문서가 전부 유령인 테넌트는 커버리지에 줄 자체가 없다.
            from nexus.index.embed_health import fetch_unreachable_documents
            try:
                ghosts = await fetch_unreachable_documents()
            except Exception:      # noqa: BLE001 — 마이그레이션 전이면 표가 없다
                ghosts = []
            for g in ghosts:
                typer.echo(
                    f"⚠ 읽을 수 없는 문서 {g['tenant']:<16} {g['unreachable']}건 — active 인데 "
                    f"살아 있는 청크가 0건이다. 목록·개수에는 보이고 검색에는 영영 안 나온다")
                for uri in g["examples"]:
                    typer.echo(f"   · {uri}")
                typer.echo(f"   └ nexus ingest --force --tenant {g['tenant']} 로 다시 청킹하라")

            # 선언되지 않은 테넌트 (SPEC-nexus-generation-of-record §3.5). 선언이 없으면 §3.2 의
            # 가드가 통과시키므로, 고쳐 놓고도 노출된 상태다 — 그 상태를 여기서 지목한다.
            # 그림 판독기의 재현율 (SPEC-nexus-vision-reproducibility §2.3). 컬럼을 만들어 두고
            # 아무도 안 읽으면 신호가 아니다 — 이 리포가 그 실패를 이미 한 번 기록했다.
            # `machine_read` 청크가 없는 테넌트에는 **한 줄도 찍지 않는다**: 새 상시 경보를
            # 만드는 것이 오늘 고친 문제의 모양이다.
            from nexus.ingest.vision_health import MAX_VARIATION, fetch_reader_health
            try:
                for row_ in [c for c in coverage if c["active"]]:
                    vh = await fetch_reader_health(row_["tenant"])
                    if not vh["machine_read_chunks"]:
                        continue
                    typer.echo(
                        f"  그림 판독 {row_['tenant']:<16} machine_read 청크 "
                        f"{vh['machine_read_chunks']:>4}  추출 {vh['extractions']:>4}")
                    if vh["unmeasured"]:
                        typer.echo(
                            f"   └ ⚠ 재현율 미측정 추출 {vh['unmeasured']}건 — 이 판독기가 같은 "
                            f"그림을 두 번 읽어 같은 값을 내는지 아무도 안 쟀다")
                    if vh["above_threshold"]:
                        typer.echo(
                            f"   └ ⚠ 재현율이 문턱({MAX_VARIATION:.0%})을 넘는 추출 "
                            f"{vh['above_threshold']}건 — 같은 바이트가 다른 텍스트를 낸다")
            except Exception:      # noqa: BLE001 — 마이그레이션 전이면 컬럼이 없다
                pass

            # 원본으로 돌아갈 수 없는 추출 (SPEC-nexus-vision-source-ref §5.9).
            # **추출 행 기준**으로 센다 — 청크와 추출은 조인되지 않는 별개 모집단이고, 청크 쪽
            # 술어로 억제하면 청크 없는 추출(빈 판독)의 미해석 상태가 0 으로 보고된다.
            from nexus.ingest.vision_source import unresolvable_count
            try:
                for row_ in [c for c in coverage if c["active"]]:
                    vs = await unresolvable_count(row_["tenant"])
                    if not vs["rows"]:
                        continue
                    if vs["unresolvable"]:
                        typer.echo(
                            f"   └ ⚠ 원본 참조 없는 추출 {vs['unresolvable']}건 "
                            f"/ {vs['current_rows']} ({row_['tenant']}) — 인용을 든 독자가 "
                            f"그림으로 돌아갈 수 없다. ADR-0010 §2 가 이 등급을 받아들인 "
                            f"근거가 그것이다")
                    if vs["retired_unresolvable"]:
                        # ⚠ 가 아니다. 은퇴한 신원의 행은 어떤 걷기도 다시 닿지 않고(§5 가
                        # 저장을 신원으로 키잉한다), 활성 인용은 전부 현 신원의 마커를 이고
                        # 있으므로 그것을 가리키는 인용이 없다. 안 꺼지는 경보로 만들지 않는다.
                        typer.echo(
                            f"     은퇴한 판독기의 추출 {vs['retired_unresolvable']}건은 참조가 "
                            f"없다 — 기록으로만 남는다(가리키는 활성 인용 없음)")
            except Exception:      # noqa: BLE001 — 마이그레이션 016 전이면 컬럼이 없다
                pass

            # 면제 테넌트는 **묻지 않는다**: 벡터를 일부러 안 만드는 코퍼스에게 "어느 세대냐" 는
            # 물음은 성립하지 않는다. 여기를 빼먹었더니 ⚠ 가 3줄이 됐고, 그중 2줄이 영원히 안
            # 꺼지는 것이었다 — 이 작업이 통째로 그 실패에 관한 것이다.
            from nexus.index.generation import current as _current_generation
            for row_ in [c for c in coverage if c["active"] and c["tenant"] not in exempt]:
                if await _current_generation(row_["tenant"]) is None:
                    typer.echo(
                        f"⚠ 세대 미선언 {row_['tenant']} — 이 코퍼스가 어느 세대인지 DB 에 없다. "
                        f"다른 세대로 적재해도 아무도 못 막는다\n"
                        f"   └ nexus generation declare --tenant {row_['tenant']} "
                        f"--column {col} --model <model> --by <who>")

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
def entropy_signals(
    tenant: str = typer.Option("", "--tenant", "-t", help="이 테넌트만. 비우면 전부"),
    total_only: bool = typer.Option(False, "--total", help="합계 한 줄만"),
) -> None:
    """공존 잔차 신호를 **테넌트별로** 표시.

    신호 다섯: 재수집 덮어쓰기 · 정확중복쌍 · 제목충돌 · supersession · 신원없는청크
    (마이그레이션 001 + 034).

    **왜 테넌트별인가.** 이 수는 ADR-0006 이 지정한 demand-pull 방아쇠이고, 여러 SPEC 처분이
    여기에 걸려 보류돼 있다. 그런데 전역 집계는 버릴 평가 테넌트(`ko_eval_*`·`merge_probe`)를
    같이 세고 **테넌트를 가로지르는 쌍까지** 셌다 — 2026-08-25 실측에서 전역 정확중복 61,425 대
    라이브 `default` 0. 무엇을 만들지 정하는 숫자가 그렇게 오염돼 있었다.
    """

    async def _do() -> None:
        from nexus import db

        # `…_docs` 는 `…_events` 의 **분모**다. 나란히 있어야 53 이 혼자 읽히지 않는다
        # (2026-08-26 라이브: 이벤트 53 · 문서 18 — 같은 열여덟을 다시 적재한 수였다).
        keys = ("reingest_overwrite_events", "reingest_overwrite_docs", "exact_dup_pairs",
                "title_stem_collisions", "supersessions", "identityless_chunks")
        try:
            if not total_only:
                rows = await db.fetch_all(
                    "SELECT * FROM v_entropy_signals_by_tenant "
                    "WHERE ($1 = '' OR tenant = $1) ORDER BY tenant", tenant)
                if not rows:
                    typer.echo(f"테넌트 없음: {tenant}" if tenant else "테넌트 없음")
                for r in rows:
                    d = dict(r)
                    typer.echo(f"[{d['tenant']}] " + "  ".join(f"{k}: {d[k]}" for k in keys))
            if total_only or not tenant:
                # 합계는 **테넌트별 뷰의 합**이다(034). 가로지르는 쌍은 여기에도 안 들어온다.
                total = dict(await db.fetch_one("SELECT * FROM v_entropy_signals"))
                typer.echo("[합계] " + "  ".join(f"{k}: {total[k]}" for k in keys))
        finally:
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
        False, "--dry-run", help="계획만 출력하고 DB 를 건드리지 않는다 (적재도 하지 않는다)",
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

    from nexus.sources import roots_store

    # **루트는 토큰별로 갈라 걷는다** (migration 009). Notion 의 integration 은 워크스페이스에
    # 속하므로, 한 토큰으로 두 워크스페이스의 루트를 함께 걸으면 그 토큰이 못 보는 쪽이 통째로
    # `ObjectNotFound` 로 돌아온다 — 그리고 그 코드는 *공유 안 됨* 과 *삭제됨* 을 구분하지 않는다.
    # 009 가 예고한 "조용한 오독" 이 그것이고, `--reconcile` 과 만나면 남의 워크스페이스 문서를
    # 사라진 것으로 판정한다. HTTP 표면은 `group_by_token()` 으로 이미 갈라 걷고 있었고
    # (`sources/api.py`), CLI 만 `--token-env` 하나를 전부에 적용하고 있었다.
    # `--dry-run` 은 이제 **적재까지** 마른다. 그래서 `--reconcile` 없이도 의미가 있다:
    # "지금 돌리면 무엇이 들어오나" 를 쓰기 없이 보는 것. `--force` 는 여전히 재조정 전용이다.
    if force and not reconcile:
        typer.echo("--force 는 --reconcile 과 함께 써야 의미가 있습니다")
        raise typer.Exit(code=1)
    reconcile_fn = (
        make_reconcile_fn(threshold=threshold, force=force, dry_run=dry_run)
        if reconcile else None
    )

    totals = {"ingested": 0, "idempotent": 0, "empty": 0, "skipped": 0,
              "holes": 0, "would_ingest": 0}
    # 이 실행이 공급자로 보낸 그림 판독. **그룹마다 리포트가 하나씩 오므로 여기서 합친다.**
    from nexus.llm.dev_spend import Spend
    vision_spend = Spend()
    watermarks: list[str] = []
    report = None

    # **루프는 하나다.** `asyncio.run()` 을 두 번 부르면 첫 루프에서 만들어진 asyncpg 풀의
    # 연결이 두 번째에서 죽은 루프에 묶여 있고, 모든 페이지가 `Event loop is closed` 로
    # 실패한다 — 2026-08-11 라이브 실행에서 112 페이지가 통째로 그렇게 skip 됐다. 루트 조회를
    # 적재와 같은 루프 안으로 들여야 그 상태가 성립하지 않는다.
    async def _walk() -> None:
        nonlocal report

        # **루트는 토큰별로 갈라 걷는다** (migration 009). Notion 의 integration 은 워크스페이스에
        # 속하므로, 한 토큰으로 두 워크스페이스의 루트를 함께 걸으면 그 토큰이 못 보는 쪽이 통째로
        # `ObjectNotFound` 로 돌아온다 — 그리고 그 코드는 *공유 안 됨* 과 *삭제됨* 을 구분하지
        # 않는다. 009 가 예고한 "조용한 오독" 이 그것이고, `--reconcile` 과 만나면 남의
        # 워크스페이스 문서를 사라진 것으로 판정한다.
        explicit = [r.strip() for r in roots.split(",") if r.strip()]
        if explicit:
            # 명시된 루트도 **등록돼 있으면 그 루트의 토큰**을 쓴다. `--token-env` 는 미등록
            # 루트의 기본값일 뿐이다 — 등록 정보를 손 인자가 덮으면 009 의 컬럼이 무의미해진다.
            known = {r["root_id"]: r.get("token_env") or token_env
                     for r in await roots_store.list_roots(tenant)}
            groups: dict[str, list[str]] = {}
            for rid in explicit:
                groups.setdefault(known.get(rid, token_env), []).append(rid)
        else:
            # --roots 미지정 → DB 에 등록된 소스를 쓴다 (SPEC-nexus-notion-source-console §4.1).
            # cron 명령에서 페이지 id 를 지우고, 오타로 코퍼스를 날릴 여지를 없앤다.
            groups = roots_store.group_by_token(await roots_store.list_roots(tenant))

        if not [rid for ids in groups.values() for rid in ids]:
            typer.echo(
                "등록된 Notion 소스가 없습니다. 웹 UI 의 '소스' 탭에서 추가하거나 "
                "--roots 'pageid1,pageid2' 를 주세요."
            )
            raise typer.Exit(code=1)

        for env, ids in sorted(groups.items()):
            try:
                source = NotionSource(token_env=env, roots=ids, tenant=tenant)
            except KeyError:
                typer.echo(f"환경변수 {env} 없음 — 이 토큰이 읽는 루트 {len(ids)}개를 건너뜁니다")
                raise typer.Exit(code=1) from None
            except ImportError:
                typer.echo("notion-client 미설치 — `pip install nexus[notion]`")
                raise typer.Exit(code=1) from None

            if len(groups) > 1:
                typer.echo(f"[{env}] 루트 {len(ids)}개")
            # force 는 재조정 planner 뿐 아니라 **적재**까지 닿아야 한다. 안 그러면 본문이 안
            # 바뀐 페이지는 --force 를 줘도 영원히 idempotent 다 (제목 같은 파생 메타데이터가
            # 안 고쳐진다).
            report = await import_notion(
                source, tenant, _default_external_ingest_fn,
                since=since or None, reconcile_fn=reconcile_fn, force=force,
                dry_run=dry_run)
            for k in totals:
                totals[k] += getattr(report, k, 0) or 0
            vs = getattr(report, "vision_spend", None) or {}
            vision_spend.calls += vs.get("calls", 0)
            vision_spend.priced += vs.get("priced_calls", 0)
            vision_spend.usd += vs.get("usd", 0.0)
            for kind, n in (vs.get("by_kind") or {}).items():
                vision_spend.by_kind[kind] = vision_spend.by_kind.get(kind, 0) + n
            if report.watermark:
                watermarks.append(report.watermark)

    _asyncio_run(_walk)

    # **watermark 는 그룹들의 최소값이다.** 다음 증분 실행의 `--since` 로 쓰이므로, 최대값을
    # 내면 뒤처진 그룹의 변경분을 건너뛴다. 최소값은 이미 본 것을 다시 볼 뿐이고 그건 멱등이다.
    if dry_run:
        typer.echo(
            f"would_ingest={totals['would_ingest']} empty={totals['empty']} "
            f"skipped={totals['skipped']} holes={totals['holes']} "
            f"watermark={min(watermarks) if watermarks else ''}"
        )
    else:
        typer.echo(
            f"ingested={totals['ingested']} idempotent={totals['idempotent']} "
            f"empty={totals['empty']} skipped={totals['skipped']} "
            f"holes={totals['holes']} watermark={min(watermarks) if watermarks else ''}"
        )
    # **판독은 돈이 나가는 유일한 경로다** — 그런데 2026-08-25 재적재는 39건을 보내고도
    # 아무 데도 안 적어서 "지출 0" 으로 보고됐다. 0 건이면 조용하고, 1건이라도 있으면 말한다.
    if vision_spend.calls:
        typer.echo(f"그림 판독: {vision_spend.summary()}")
        if not vision_spend.priced:
            from nexus.ingest.vision import vision_model
            typer.echo(f"  ⚠ 값을 모릅니다 — `{vision_model()}` 가 config.yaml 의 llm.pricing 에"
                       " 없습니다. 호출 수는 실측이고, 단가를 넣으면 금액이 나옵니다"
                       " (단가를 지어내지 않으므로 그때까지 값은 비어 있습니다)")
    if totals["holes"]:
        # 부분 본문은 **성공한 적재**로 세어지므로, 여기서 말하지 않으면 아무도 모른다.
        typer.echo(f"⚠ 읽지 못한 하위 블록 {totals['holes']}개 — 그만큼의 문서가 부분 본문입니다"
                   " (본문의 '읽지 못한 블록' 표식을 보세요)")
    if reconcile:
        typer.echo(f"pruned={report.pruned} revived={report.revived}")
        if report.refused:
            typer.echo(f"재조정 거부됨: {report.reason}")
            raise typer.Exit(code=2)
    if dry_run:
        typer.echo("dry-run — DB 는 변경되지 않았습니다")


def _asyncio_run(coro_fn):
    """CLI 명령이 코루틴을 돌리는 공통 경로. Windows 는 Proactor 루프에서 asyncpg 가 안 돈다."""
    import asyncio
    import sys

    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    return asyncio.run(coro_fn())


reembed_app = typer.Typer(help="임베딩 세대 이전 (SPEC-nexus-kure-embedding-swap §4.4)")
app.add_typer(reembed_app, name="reembed")


@reembed_app.command("run")
def reembed_run(
    column: str = typer.Option("embedding_1024", "--column"),
    model: str = typer.Option("KURE-v1", "--model"),
    backend: str = typer.Option("sidecar", "--backend"),
    batch_size: int = typer.Option(16, "--batch-size"),
    tenant: str = typer.Option(None, "--tenant", help="비우면 전 테넌트 — 범위는 명시적 선택이다"),
    all_tenants: bool = typer.Option(False, "--all-tenants",
                                     help="청크를 가진 테넌트를 모두 돈다 (범위를 손으로 세지 않는다)"),
    change_generation: bool = typer.Option(
        False, "--change-generation",
        help="이 실행이 **컷오버**다 — 선언과 다른 세대를 채우고, 완료 시 새 선언을 남긴다"),
    by: str = typer.Option("", "--by", help="--change-generation 의 서명 (누가 세대를 바꿨나)"),
) -> None:
    """NULL 인 것을 채운다. 중단해도 이어서 돈다 — 큐가 NULL 컬럼이기 때문이다.

    **`--column` 은 설정을 따라가지 않는다.** 컷오버 시점의 설정은 아직 옛 컬럼을 가리키므로,
    설정을 따라가는 마이그레이션은 보존해야 할 컬럼을 겨눈다 (SPEC-nexus-embedding-cutover-seam §4.3).
    """
    from nexus.index.generation import GenerationMismatch, assert_writable, declare
    from nexus.index.reembed import counts, reembed, tenants_with_chunks
    from nexus.index.vector_index import dimensions_of
    from nexus.providers.embedding import MODEL_DIMENSIONS, EmbeddingService

    if all_tenants and tenant:
        typer.echo("--tenant 와 --all-tenants 는 함께 쓸 수 없다 — 범위는 하나여야 한다", err=True)
        raise typer.Exit(2)

    # 차원이 안 맞으면 **첫 행을 읽기 전에** 막는다. KURE 벡터를 768 컬럼에 겨누는 실행은
    # 절반쯤 돌다 실패하는 대신 시작하지 않아야 한다 (§4.3 불변식 2).
    if model in MODEL_DIMENSIONS and MODEL_DIMENSIONS[model] != dimensions_of(column):
        typer.echo(f"--model {model} ({MODEL_DIMENSIONS[model]}d) 와 --column {column} "
                   f"({dimensions_of(column)}d) 의 차원이 다르다", err=True)
        raise typer.Exit(2)

    async def _go():
        svc = EmbeddingService(model=model, backend=backend, dimensions=dimensions_of(column))
        scopes = await tenants_with_chunks() if all_tenants else [tenant]
        if all_tenants:
            typer.echo(f"대상 테넌트 {len(scopes)}개: {', '.join(scopes) or '(없음)'}")

        # 세대 가드 (SPEC-nexus-generation-of-record §3.3). 초안은 이 명령을 **면제**했고,
        # 비평이 그 구멍으로 사고가 그대로 재현된다고 지적했다: `--column embedding --model
        # nomic-embed-text` 는 차원이 맞으므로 옛 가드를 통과하고, 검색되지 않는 세대를 다시
        # 채운다. 그래서 여기서도 선언을 본다 — 다만 이 명령만이 선언을 **바꿀** 수 있다.
        if not change_generation:
            for scope in scopes:
                if scope:
                    await assert_writable(scope, column, model, what="reembed")
        elif not by.strip():
            typer.echo("--change-generation 은 --by 가 필요하다 — 세대 변경은 서명이 있는 결정이다",
                       err=True)
            raise typer.Exit(2)

        failed = 0
        for scope in scopes:
            label = f"[{scope}] " if all_tenants else ""
            before = await counts(column, scope)
            typer.echo(f"{label}대상 {before['pending']}건 (활성 {before['active']} · "
                       f"이미 {before['embedded']} · waived {before['waived']})")
            summary = await reembed(
                svc, column, batch_size=batch_size, tenant=scope,
                progress=lambda s: typer.echo(f"  … {s.embedded}건", err=True))
            typer.echo(label + summary.render())
            failed += 0 if summary.ok else 1

            # 컷오버가 **끝났을 때만** 선언을 남긴다 (§3.3). 사람에게 두 번째 명령을 기억시키는
            # 설계는 잊히고, 절반 돌다 죽은 실행이 선언을 남기면 그 선언이 거짓이 된다.
            if change_generation and summary.ok and scope:
                await declare(scope, column, model, by,
                              reason=f"reembed --change-generation ({summary.embedded}건)")
                typer.echo(f"{label}세대 선언: {column} / {model} (by {by})")
        return 1 if failed else 0

    try:
        raise typer.Exit(_run(_go()))
    except GenerationMismatch as e:
        typer.echo(f"\n{e}", err=True)
        raise typer.Exit(2) from None


generation_app = typer.Typer(help="이 코퍼스가 어느 임베딩 세대에 있는가 "
                                  "(SPEC-nexus-generation-of-record)")
app.add_typer(generation_app, name="generation")


@generation_app.command("declare")
def generation_declare(
    column: str = typer.Option(..., "--column", help="이 코퍼스를 서빙하는 벡터 컬럼"),
    model: str = typer.Option(..., "--model"),
    by: str = typer.Option(..., "--by", help="누가 선언하는가 (감사 필드 — 권한이 아니다)"),
    tenant: str = typer.Option("default", "--tenant", "-t"),
    reason: str = typer.Option("", "--reason"),
) -> None:
    """세대를 선언한다. append 이고, 이전 선언은 이력으로 남는다."""
    from nexus.index.generation import InvalidDeclaration, declare

    async def _go() -> int:
        try:
            g = await declare(tenant, column, model, by, reason)
        except InvalidDeclaration as e:
            typer.echo(f"거부: {e}", err=True)
            return 2
        typer.echo(f"선언됨 [{tenant}] {g.render()} (by {g.declared_by})")
        return 0

    raise typer.Exit(_run(_go()))


@generation_app.command("show")
def generation_show(
    tenant: str = typer.Option("", "--tenant", "-t", help="비우면 전체"),
    show_history: bool = typer.Option(False, "--history", help="이력 전체"),
) -> None:
    """현재 세대(또는 이력)를 출력한다."""
    from nexus.index.generation import current, history

    async def _go() -> int:
        if show_history:
            rows = await history(tenant or None)
            if not rows:
                typer.echo("선언 없음")
                return 0
            for g in rows:
                when = g.declared_at.isoformat(timespec="seconds") if g.declared_at else ""
                typer.echo(f"{g.tenant:16} {g.render():34} {g.declared_by:12} {when}  {g.reason}")
            return 0
        if tenant:
            g = await current(tenant)
            typer.echo(f"{tenant}: {g.render()} (by {g.declared_by})" if g
                       else f"{tenant}: 선언 없음")
            return 0
        rows = await history()
        seen: set[str] = set()
        for g in rows:                      # history 는 (tenant, id desc) 순 → 첫 등장이 최신
            if g.tenant not in seen:
                seen.add(g.tenant)
                typer.echo(f"{g.tenant:16} {g.render():34} (by {g.declared_by})")
        if not seen:
            typer.echo("선언 없음")
        return 0

    raise typer.Exit(_run(_go()))


@reembed_app.command("waive")
def reembed_waive(
    chunk_rid: str = typer.Argument(...),
    reason: str = typer.Option(..., "--reason"),
    by: str = typer.Option(..., "--by", help="서명 — 이 내용이 검색에서 빠지는 것을 인정하는 사람"),
    model: str = typer.Option("KURE-v1", "--model"),
) -> None:
    """영구 실패 청크를 **사람이 서명해** 뺀다. 재임베딩 경로는 이걸 자동으로 만들지 않는다."""
    from nexus.index.reembed import waive

    async def _go():
        await waive(chunk_rid, model, reason, by)
        typer.echo(f"waived: {chunk_rid} (by {by}) — 이 청크는 벡터 검색에서 빠진다")
        return 0

    raise typer.Exit(_run(_go()))


@reembed_app.command("create-index")
def reembed_create_index(column: str = typer.Option("embedding_1024", "--column")) -> None:
    """재임베딩이 **끝난 뒤** 행 수를 세어 ivfflat 인덱스를 만든다 (§4.2)."""
    from nexus.index.reembed import create_index

    async def _go():
        rows, lists = await create_index(column)
        typer.echo(f"인덱스 생성: {column} · 행 {rows} → lists={lists}")
        return 0

    raise typer.Exit(_run(_go()))


@reembed_app.command("status")
def reembed_status(column: str = typer.Option("embedding_1024", "--column"),
                   tenant: str = typer.Option(None, "--tenant"),
                   all_tenants: bool = typer.Option(
                       False, "--all-tenants",
                       help="청크를 가진 테넌트를 모두 본다 — 조건은 테넌트마다 선다")) -> None:
    """컷오버 전제 조건 (§4.5). 막는 것이 있으면 **무엇이 막는지** 말한다.

    조건은 테넌트마다 서야 한다. 하나를 빠뜨린 채 flip 하면 그 테넌트의 벡터 다리만 조용히 비고,
    범위를 손으로 세는 절차는 언젠가 하나를 빠뜨린다 (SPEC-nexus-embedding-cutover-seam §4.6).
    """
    from nexus.index.reembed import counts, cutover_blockers, tenants_with_chunks, waived_rows

    if all_tenants and tenant:
        typer.echo("--tenant 와 --all-tenants 는 함께 쓸 수 없다 — 범위는 하나여야 한다", err=True)
        raise typer.Exit(2)

    async def _go():
        scopes = await tenants_with_chunks() if all_tenants else [tenant]
        blocked = 0
        for scope in scopes:
            label = f"[{scope}] " if all_tenants else ""
            c = await counts(column, scope)
            typer.echo(f"{label}[{column}] 활성 {c['active']} · 임베딩됨 {c['embedded']} · "
                       f"waived {c['waived']} · 남은 {c['pending']}")
            blockers = await cutover_blockers(column, tenant=scope)
            if blockers:
                blocked += 1
                typer.echo(f"{label}컷오버 불가:")
                for b in blockers:
                    typer.echo(f"  ✗ {b}")
        for w in await waived_rows():
            typer.echo(f"  waived {w['chunk_rid']} ({w['waived_by']}): {w['reason'][:80]}")
        if blocked:
            return 1
        typer.echo("\n✓ 컷오버 조건 충족 — 배포 env 의 세대 셋(모델·컬럼·백엔드)을 함께 전환")
        return 0

    raise typer.Exit(_run(_go()))


# ── 질의 텍스트 보존 (SPEC-nexus-query-text-retention §3.2~§3.4) ──────────────
#
# 켜는 명령은 여기 없다. 옵트인은 `notice_shown` 이 가리킬 고지가 **실제로 있어야** 성립하고,
# 그것은 사람이 하는 일이다 — CLI 한 줄로 켜지게 만들면 고지 없는 켜짐이 기본 경로가 된다.
# 켤 때는 `query_retention` 에 직접 INSERT 하고, 무엇을 가리켰는지 PR 본문에 인용한다(§6.2).

async def _with_pool_closed(go):
    """명령이 연 풀을 명령이 닫는다.

    `asyncio.run` 이 끝나면 루프는 사라지는데 `nexus.db` 의 전역 풀은 그 루프에 묶인 채 남는다.
    프로세스가 곧 죽는 CLI 에서는 무해하지만, 같은 프로세스에서 두 번 부르면(테스트가 그렇다)
    다음 호출이 죽은 루프의 풀을 집는다 — 실제로 그렇게 깨졌다.
    """
    from nexus import db
    try:
        return await go()
    finally:
        await db.close_pool()


retention_app = typer.Typer(help="질의 텍스트 보존 — 옵트인·만료·철회 "
                                 "(SPEC-nexus-query-text-retention)")
app.add_typer(retention_app, name="query-text")


@retention_app.command("status")
def query_text_status() -> None:
    """테넌트별 보존 현황. **가장 오래된 행과 만료 초과분을 함께 낸다** — 안 도는 purge 는
    증상이 없고, 그 침묵을 깨는 것이 이 줄의 목적이다."""
    from nexus.search.query_retention import NotMigrated
    from nexus.search.query_retention import status as retention_status

    async def _go() -> int:
        try:
            rows = await retention_status()
        except NotMigrated as e:
            typer.echo(f"{e}. `python -m scripts.migrate` 를 먼저 돌려라.", err=True)
            return 2
        if not rows:
            typer.echo("보존 중인 테넌트 없음 (기본값: 아무것도 저장하지 않는다)")
            return 0
        for r in rows:
            tag = " [고아 — 옵트인 행 없음]" if r.get("orphan") else ""
            notice = "" if r["has_notice"] else "  ⚠ 고지 없음 → 쓰기 거부 중"
            days = r["retain_days"] if r["retain_days"] is not None else "-"
            oldest = r["oldest"].date().isoformat() if r["oldest"] else "-"
            over = f"  ⚠ 만료 초과 {r['overdue']}건" if r["overdue"] else ""
            typer.echo(f"{r['tenant']:20s} 보관 {r['stored']:5d}건  "
                       f"최고령 {oldest}  보존 {days}일{over}{notice}{tag}")
        return 0

    raise typer.Exit(_run(_with_pool_closed(_go)))


@retention_app.command("purge")
def query_text_purge(
    tenant: str = typer.Option("", "--tenant", "-t", help="비우면 모든 테넌트"),
) -> None:
    """만료된 텍스트를 지운다(기준: `first_seen`). 고아 행은 나이와 무관하게 지운다."""
    from nexus.search.query_retention import purge

    async def _go() -> int:
        deleted = await purge(tenant or None)
        if not deleted:
            typer.echo("지울 것 없음")
            return 0
        for t, n in sorted(deleted.items()):
            typer.echo(f"{t}: {n}건 삭제")
        return 0

    raise typer.Exit(_run(_with_pool_closed(_go)))


@retention_app.command("export")
def query_text_export(
    tenant: str = typer.Option(..., "--tenant", "-t"),
    out: Path = typer.Option(..., "--out", help="쓸 파일 경로 — 운영자가 이름을 준다"),
    min_count: int = typer.Option(1, "--min-count", help="이 횟수 이상 물어본 질문만"),
) -> None:
    """보존된 질문을 파일로 내보낸다 — 라벨 저술용.

    **API 로는 나가지 않는다**(§3.5). 읽는 길은 이 명령 하나이고, 쓰는 곳은 운영자가 정한다.
    나온 파일은 `tests/eval/local/` 처럼 커밋하지 않는 자리에 둔다 — 조직의 질문이다.
    """
    import json

    async def _go() -> int:
        from nexus import db
        rows = await db.fetch_all(
            "SELECT query_text, seen_count, first_seen, last_seen "
            "FROM search_query_text WHERE tenant = $1 AND seen_count >= $2 "
            "ORDER BY seen_count DESC, last_seen DESC", tenant, min_count)
        payload = [{"query": r["query_text"], "seen_count": r["seen_count"],
                    "first_seen": r["first_seen"].isoformat(),
                    "last_seen": r["last_seen"].isoformat()} for r in rows]
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n",
                       encoding="utf-8")
        typer.echo(f"{len(payload)}건 → {out}")
        if payload:
            typer.echo("라벨로 옮길 때 provenance: from_user_query 를 쓴다 "
                       "— 저술된 질의와 섞이면 천장을 잴 수 없다")
        return 0

    raise typer.Exit(_run(_with_pool_closed(_go)))


@retention_app.command("disable")
def query_text_disable(
    tenant: str = typer.Option(..., "--tenant", "-t"),
    yes: bool = typer.Option(False, "--yes", help="확인 없이 진행"),
) -> None:
    """보존을 끈다 — 저장된 텍스트와 옵트인 행을 **함께** 지운다(되돌릴 수 없다)."""
    from nexus.search.query_retention import disable

    async def _go() -> int:
        from nexus import db
        n = await db.fetch_val(
            "SELECT count(*) FROM search_query_text WHERE tenant = $1", tenant) or 0
        if not yes:
            typer.echo(f"[{tenant}] 저장된 질문 {n}건과 옵트인 행을 지운다. --yes 로 진행.")
            return 1
        deleted = await disable(tenant)
        typer.echo(f"[{tenant}] 텍스트 {deleted}건 + 옵트인 행 삭제됨")
        return 0

    raise typer.Exit(_run(_with_pool_closed(_go)))


code_app = typer.Typer(
    help="문서↔코드 앵커 — '이 문서 낡았나' 를 판단이 아니라 조인으로 (SPEC-nexus-doc-code-anchors)")
app.add_typer(code_app, name="code")


def _repo_or_die(config_path: str) -> str:
    """대상 저장소 경로는 **설정에서만** 온다. 리포에 박아두지 않는다."""
    repo = _load_config(config_path).get("code_source", {}).get("repo_path", "")
    if not repo:
        typer.echo("config.code_source.repo_path 가 비어있습니다 "
                   "(배포별 값이므로 리포에 커밋하지 않습니다).", err=True)
        raise typer.Exit(1)
    return repo


@code_app.command("scan")
def code_scan(
    tenant: str = typer.Option("default", "--tenant"),
    config_path: str = typer.Option("config.yaml", "--config", "-c"),
    require_mainline: bool = typer.Option(
        False, "--require-mainline",
        help="기본 브랜치가 아니면 거부한다 (경고만으로는 놓친다)"),
) -> None:
    """체크아웃을 훑어 심볼 인덱스를 대체한다. LLM 을 부르지 않는다."""
    from pathlib import Path

    from nexus.index import anchor_store, snapshot
    from nexus.index.history import DELETED, classify, deletion_map
    from nexus.index.symbols import scan_repo

    repo_path = Path(_repo_or_die(config_path))
    commit = snapshot.head_commit(repo_path)
    if commit is None:
        typer.echo("git 저장소가 아니거나 git 을 실행할 수 없습니다.", err=True)
        raise typer.Exit(1)

    state = snapshot.check(repo_path, commit)
    if not state.ok:
        # 스캔 시점의 더러운 트리는 인덱스 자체를 커밋과 어긋나게 만든다.
        typer.echo(f"스캔 거부: {state.explain()}", err=True)
        raise typer.Exit(1)

    # 통과해도 **무엇을 사실로 삼았는지** 는 항상 말한다. 이게 없어서 3주 된 피처 브랜치를
    # 조용히 스캔하고 그 심볼 수를 보고한 적이 있다.
    typer.echo(f"대상: {state.context()}")
    for w in state.warnings():
        typer.echo(f"⚠ {w}")

    if require_mainline and state.warnings():
        # 경고를 읽고도 그냥 넘긴 적이 있다. 3주 된 피처 브랜치를 재고 그 숫자를 보고했고,
        # 이미 고쳐진 항목 6건이 목록에 올라갔다. 막을 수 있으면 막는 편이 낫다.
        typer.echo("거부: --require-mainline 인데 위 경고가 있습니다.", err=True)
        raise typer.Exit(1)

    result = scan_repo(repo_path)

    # **지워진 이름은 지금 같이 저장한다.** 문서가 부르는데 코드에 없는 이름의 이유는 셋인데
    # (외부 타입·미구현·삭제됨) 그중 삭제됨만이 읽는 사람에게 조치를 요구하고, 그 판정에는
    # git 이력이 필요하다. 여기서 한 번 훑어 두면 요청 경로는 조인만 하면 된다 —
    # 답변마다 git 을 부를 수는 없다. 훑기는 `git log --diff-filter=D` **한 번**이다.
    deletions = deletion_map(repo_path)
    deleted = [v for v in classify(sorted(deletions), imported=result.imported_names,
                                   deletions=deletions)
               if v.kind == DELETED]

    async def _go():
        await anchor_store.replace_scan(tenant, repo_path.name, result, commit)
        return await anchor_store.replace_deletions(tenant, repo_path.name, deleted, commit)

    n_deleted = _run(_with_pool_closed(_go))

    typer.echo(f"스캔 완료 — 심볼 {len(result.symbols)}개 "
               f"/ 파일 {result.scanned_files}개 "
               f"(선언 0: {result.no_symbol_files}개) @ {commit[:12]}")
    typer.echo(f"지워진 이름 {n_deleted}개 기록 — 문서가 이 이름을 부르면 답변이 "
               f"삭제 날짜와 함께 말합니다.")
    # **읽지 못한 파일만** 경고다 (migration 033). 선언이 없는 파일(`__init__.py`·스크립트)은
    # 평범한 사실이고, 둘을 한 칸에 세던 동안에는 여기에 경고를 걸 수 없었다 — 걸면 정상
    # 상태에서 영원히 울린다. 읽기 실패는 다르다: 그 파일의 심볼이 통째로 빠지므로 문서가
    # 그 이름을 부르면 **코드에 없는 이름**으로 판정된다(거짓 드리프트).
    if result.unreadable_files:
        typer.echo(f"⚠ 읽지 못한 파일 {result.unreadable_files}개 — 그 파일의 심볼은 "
                   f"인덱스에 없습니다. 문서가 그 이름을 부르면 없는 이름으로 판정됩니다.")


@code_app.command("bind")
def code_bind(
    tenant: str = typer.Option("default", "--tenant"),
    config_path: str = typer.Option("config.yaml", "--config", "-c"),
) -> None:
    """이미 적재된 청크에 앵커를 붙인다 (백필). LLM 을 부르지 않는다.

    적재 시점 바인딩만으로는 기존 코퍼스가 영원히 어둡다 — 재적재하지 않는 한 후보 추출조차
    되지 않기 때문이다. 스캔을 새로 돌린 뒤에도 이 명령으로 다시 훑는다.
    """
    from pathlib import Path

    from nexus.index import anchor_store
    from nexus.index.anchors import bind, extract_candidates

    repo_path = Path(_repo_or_die(config_path))
    repo = repo_path.name

    async def _go():
        scan = await anchor_store.last_scan(tenant, repo)
        if scan is None:
            typer.echo("스캔 기록이 없습니다. 먼저 `nexus code scan`.", err=True)
            return 1

        chunks = await anchor_store.iter_chunk_texts(tenant)
        cache: dict[str, list] = {}
        n_chunks = n_cand = n_anchor = 0
        refused = {"unresolved": 0, "ambiguous": 0}

        for rid, text in chunks:
            candidates = extract_candidates(text or "")
            if not candidates:
                continue
            n_chunks += 1
            n_cand += len(candidates)
            for c in candidates:
                if c not in cache:
                    cache[c] = await anchor_store.resolve_symbol(tenant, repo, c)
            outcome = bind(candidates, lambda c: cache[c])
            n_anchor += len(outcome.anchors)
            for r in outcome.refusals:
                refused[r.reason] += 1
            await anchor_store.save_bindings(
                tenant, repo, rid, outcome.anchors, outcome.refusals, scan.scan_commit)

        typer.echo(f"대상 청크 {len(chunks)}개 중 후보를 가진 청크 {n_chunks}개")
        typer.echo(f"후보 {n_cand}개 → 앵커 {n_anchor}개")
        typer.echo(f"거부  unresolved {refused['unresolved']} · ambiguous {refused['ambiguous']}")
        typer.echo("※ 바인딩률은 거부 분할과 함께 읽으십시오 (SPEC §6.1).")
        return 0

    raise typer.Exit(_run(_with_pool_closed(_go)) or 0)


@code_app.command("drift")
def code_drift(
    tenant: str = typer.Option("default", "--tenant"),
    config_path: str = typer.Option("config.yaml", "--config", "-c"),
    classify_missing: bool = typer.Option(
        False, "--classify",
        help="미해소 후보를 external/deleted/never_existed 로 가른다 (git 이력 1회 훑음)"),
) -> None:
    """앵커를 재바인딩하고 현재 상태를 보고한다. LLM 을 부르지 않는다."""
    from pathlib import Path

    from nexus.index import anchor_store, snapshot
    from nexus.index.anchors import AMBIGUOUS_NOW, CHANGED, FRESH, ORPHANED, recheck

    repo_path = Path(_repo_or_die(config_path))
    repo = repo_path.name

    async def _go():
        scan = await anchor_store.last_scan(tenant, repo)
        if scan is None:
            typer.echo("스캔 기록이 없습니다. 먼저 `nexus code scan`.", err=True)
            return 1

        state = snapshot.check(repo_path, scan.scan_commit)
        if not state.ok:
            # "모름" 은 정답이다. 더러운 트리에서 계산한 fresh 는 아니다.
            typer.echo(f"unknown — {state.explain()}")
            typer.echo("드리프트 상태를 보고하지 않습니다.")
            return 0

        # §3.6 재바인딩: 스캔보다 먼저 적재된 문서가 영구 미앵커로 남지 않게.
        promoted = 0
        for chunk_rid, candidate in await anchor_store.unresolved_refusals(tenant, repo):
            matches = await anchor_store.resolve_symbol(tenant, repo, candidate)
            if len(matches) == 1:
                await anchor_store.promote_refusal(
                    tenant, repo, chunk_rid, candidate, matches[0], scan.scan_commit)
                promoted += 1

        counts = {FRESH: 0, CHANGED: 0, ORPHANED: 0, AMBIGUOUS_NOW: 0}
        changed_rows: list[tuple[str, str]] = []
        for a in await anchor_store.all_anchors(tenant, repo):
            matches = await anchor_store.resolve_symbol(tenant, repo, a["symbol_name"])
            st = recheck(a["span_hash"], matches)
            counts[st] += 1
            if st in (CHANGED, ORPHANED):
                changed_rows.append((st, a["symbol_name"]))

        refusals = await anchor_store.refusal_counts(tenant, repo)

        typer.echo(f"대상: {state.context()}")
        for w in state.warnings():
            typer.echo(f"⚠ {w}")
        typer.echo(f"심볼 {scan.symbol_count}개 (미파싱 파일 {scan.unparsed_files}개) "
                   f"@ 스캔 {scan.scan_commit[:12]}")
        if promoted:
            typer.echo(f"재바인딩 {promoted}건")
        typer.echo(f"앵커  fresh {counts[FRESH]} · changed {counts[CHANGED]} · "
                   f"orphaned {counts[ORPHANED]} · ambiguous_now {counts[AMBIGUOUS_NOW]}")
        typer.echo(f"거부  unresolved {refusals.get('unresolved', 0)} · "
                   f"ambiguous {refusals.get('ambiguous', 0)}")

        if classify_missing:
            # 왜 없는지가 처분을 가른다. 프레임워크 클래스를 "사라졌다" 고 올리면
            # 받는 쪽이 목록 전체를 신뢰하지 않는다.
            from nexus.index.history import DELETED, EXTERNAL, classify, deletion_map
            from nexus.index.symbols import scan_repo

            names = sorted({c for _, c in
                            await anchor_store.unresolved_refusals(tenant, repo)})
            verdicts = classify(names, imported=scan_repo(repo_path).imported_names,
                                deletions=deletion_map(repo_path))
            buckets: dict[str, list] = {}
            for v in verdicts:
                buckets.setdefault(v.kind, []).append(v)

            typer.echo("")
            typer.echo(f"미해소 후보 {len(verdicts)}건 분류:")
            for kind, label in ((EXTERNAL, "외부 타입 (문서 잘못 아님)"),
                                (DELETED, "삭제됨 — 드리프트"),
                                ("never_existed", "이력 없음 — 미구현일 수 있음")):
                got = buckets.get(kind, [])
                typer.echo(f"  {label}: {len(got)}건")

            # **목록은 자기 표제 아래 놓는다.** 세 수를 먼저 다 찍고 목록을 이어 붙였더니,
            # 63건짜리 삭제 목록이 바로 위 "이력 없음 1,354건" 라벨에 붙어 보였다. 읽는 사람이
            # 오해하면 그건 출력 결함이지 사소한 서식 문제가 아니다.
            gone = buckets.get(DELETED, [])
            if gone:
                typer.echo("")
                typer.echo(f"삭제됨 {len(gone)}건 — 문서가 아직 부르는 이름:")
                for v in gone[:25]:
                    typer.echo(f"    {v.name:<38} {v.explain()}")
                if len(gone) > 25:
                    typer.echo(f"    … 외 {len(gone) - 25}건")

        if changed_rows:
            typer.echo("")
            typer.echo("읽어볼 것 — changed 는 결함 목록이 아니라 읽기 목록입니다 "
                       "(의미 판정은 후속 SPEC):")
            for st, name in changed_rows[:40]:
                typer.echo(f"  {st:<10} {name}")
            if len(changed_rows) > 40:
                typer.echo(f"  … 외 {len(changed_rows) - 40}건")
        return 0

    raise typer.Exit(_run(_with_pool_closed(_go)) or 0)


if __name__ == "__main__":
    app()
