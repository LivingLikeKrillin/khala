"""Nexus MCP Server — AI Agent용 tool provider.

FastMCP를 사용하여 Nexus API를 MCP 도구로 노출한다.
Agent가 stdio 또는 streamable-http로 접속하여 검색/그래프/상태를 질의할 수 있다.

실행:
    # stdio (로컬 Agent 연동)
    python -m nexus.mcp.server

    # streamable-http (원격 Agent 연동)
    python -m nexus.mcp.server --transport http --port 8001
"""

from __future__ import annotations

import os

import httpx
from mcp.server.fastmcp import FastMCP

NEXUS_API_URL = os.getenv("NEXUS_API_URL", "http://localhost:8000")

mcp = FastMCP(
    "Nexus",
    instructions="Enterprise RAG + GraphRAG — 조직 내부 지식과 운영 사실 기반 검색·추론",
)


def _auth_headers() -> dict:
    """Forward the MCP service credential. The MCP is an HTTP client — it does NOT resolve
    principals; the API does. One ``NEXUS_MCP_TOKEN`` ⇒ one (tenant, clearance) ceiling."""
    token = os.getenv("NEXUS_MCP_TOKEN")
    return {"Authorization": f"Bearer {token}"} if token else {}


async def _api_call(method: str, path: str, **kwargs) -> dict:
    """Nexus API 호출 래퍼 (인증 토큰 포워딩 포함)."""
    headers = {**_auth_headers(), **(kwargs.pop("headers", None) or {})}
    async with httpx.AsyncClient(timeout=60.0, base_url=NEXUS_API_URL) as client:
        resp = await getattr(client, method)(path, headers=headers, **kwargs)

    if resp.status_code == 503:
        return {"success": False, "error": "Nexus 데이터베이스에 연결할 수 없습니다"}
    if resp.status_code == 401:
        return {"success": False,
                "error": "Nexus 인증 실패 (401). NEXUS_MCP_TOKEN 환경변수에 유효한 bearer 토큰을 설정하세요."}

    data = resp.json()
    if not data.get("success"):
        # FastAPI 의 HTTPException 은 {detail} 로 온다(봉투가 아니다). 이걸 읽지 않으면
        # 403/409/400 이 전부 "API 오류 (HTTP 403)" 이 되어, 에이전트는 왜 막혔는지 모른다.
        reason = data.get("error") or data.get("detail") or f"API 오류 (HTTP {resp.status_code})"
        return {"success": False, "error": reason}

    return data


@mcp.tool()
async def nexus_search(
    query: str,
    top_k: int = 10,
    route: str = "auto",
    classification_max: str = "INTERNAL",
    tenant: str = "default",
    include_graph: bool = True,
) -> str:
    """Nexus 하이브리드 검색 (BM25 + Vector + Graph).

    조직 내부 문서와 운영 데이터를 통합 검색한다.
    결과에는 근거 snippet, 점수, 그래프 관계가 포함된다.

    Args:
        query: 검색 질의 (한국어/영어)
        top_k: 반환할 결과 수
        route: 검색 경로 (auto|keyword_only|vector_only|hybrid_then_graph)
        classification_max: 최대 접근 등급 (PUBLIC|INTERNAL|RESTRICTED)
        tenant: 테넌트 ID
        include_graph: 그래프 관계 포함 여부
    """
    result = await _api_call("post", "/search", json={
        "query": query,
        "top_k": top_k,
        "route": route,
        "classification_max": classification_max,
        "tenant": tenant,
        "include_graph": include_graph,
    })

    if not result.get("success"):
        return f"검색 실패: {result.get('error', '알 수 없는 오류')}"

    data = result["data"]
    lines = []
    for i, r in enumerate(data.get("results", []), 1):
        lines.append(
            f"[{i}] {r['doc_title']} > {r['section_path']} (score: {r['score']:.2f})\n"
            f"    {r['snippet'][:200]}\n"
            f"    출처: {r['source_uri']}"
        )

    if data.get("graph_findings"):
        gf = data["graph_findings"]
        if gf.get("designed_edges"):
            lines.append("\n--- 설계 관계 ---")
            for e in gf["designed_edges"]:
                lines.append(f"  {e['from_name']} --{e['edge_type']}--> {e['to_name']} (confidence: {e['confidence']})")
        if gf.get("observed_edges"):
            lines.append("\n--- 관측 관계 ---")
            for o in gf["observed_edges"]:
                lines.append(f"  {o['from_name']} --{o['edge_type']}--> {o['to_name']} ({o['call_count']} calls)")

    lines.append(f"\n경로: {data.get('route_used', 'N/A')}")
    return "\n".join(lines) if lines else "검색 결과가 없습니다."


@mcp.tool()
async def nexus_answer(
    query: str,
    top_k: int = 10,
    route: str = "auto",
    classification_max: str = "INTERNAL",
    tenant: str = "default",
) -> str:
    """Nexus 검색 + LLM 근거 기반 답변 생성.

    검색 결과를 바탕으로 LLM이 근거를 인용하며 답변한다.
    모든 답변에는 출처 chunk와 문서 포인터가 포함된다.

    Args:
        query: 질문 (한국어/영어)
        top_k: 검색 결과 수
        route: 검색 경로 (auto|keyword_only|vector_only|hybrid_then_graph)
        classification_max: 최대 접근 등급
        tenant: 테넌트 ID
    """
    result = await _api_call("post", "/search/answer", json={
        "query": query,
        "top_k": top_k,
        "route": route,
        "classification_max": classification_max,
        "tenant": tenant,
    })

    if not result.get("success"):
        return f"답변 생성 실패: {result.get('error', '알 수 없는 오류')}"

    data = result["data"]
    lines = [data.get("answer", "답변 없음")]

    # 근거 표시
    snippets = data.get("evidence_snippets", [])
    if snippets:
        lines.append("\n--- 근거 ---")
        for i, s in enumerate(snippets[:5], 1):
            lines.append(f"[{i}] {s['doc_title']} > {s['section_path']} (score: {s.get('score', 0):.2f})")

    # 출처
    provenance = data.get("provenance", [])
    if provenance:
        sources = [p["source_uri"] for p in provenance[:3]]
        lines.append(f"\n출처: {', '.join(sources)}")

    lines.append(f"경로: {data.get('route_used', 'N/A')}")
    return "\n".join(lines)


@mcp.tool()
async def nexus_graph(
    entity: str,
    hops: int = 1,
    tenant: str = "default",
    include_evidence: bool = True,
) -> str:
    """엔티티 관계 그래프 조회.

    특정 엔티티(서비스, 토픽 등)의 설계/관측 관계를 조회한다.
    entity에는 rid(ent_...) 또는 이름(예: payment-service)을 전달할 수 있다.

    Args:
        entity: 엔티티 rid 또는 이름
        hops: 탐색 깊이 (1 또는 2)
        tenant: 테넌트 ID
        include_evidence: 관계의 근거 포함 여부
    """
    result = await _api_call("get", f"/graph/{entity}", params={
        "hops": hops,
        "tenant": tenant,
        "include_evidence": include_evidence,
    })

    if not result.get("success"):
        return f"그래프 조회 실패: {result.get('error', '알 수 없는 오류')}"

    data = result["data"]
    center = data.get("center_entity", {})
    lines = [f"엔티티: {center.get('name', 'N/A')} ({center.get('type', 'N/A')})"]

    if center.get("description"):
        lines.append(f"설명: {center['description']}")

    edges = data.get("edges", [])
    if edges:
        lines.append("\n--- 설계 관계 ---")
        for e in edges:
            line = f"  {e['from_name']} --{e['edge_type']}--> {e['to_name']} (confidence: {e['confidence']})"
            lines.append(line)
            for ev in e.get("evidence", []):
                lines.append(f"    근거: {ev['doc_title']} > {ev['section_path']}")

    observed = data.get("observed_edges", [])
    if observed:
        lines.append("\n--- 관측 관계 ---")
        for o in observed:
            lines.append(
                f"  {o['from_name']} --{o['edge_type']}--> {o['to_name']} "
                f"({o['call_count']} calls, error: {o.get('error_rate', 0):.1%})"
            )

    return "\n".join(lines) if lines else "엔티티를 찾을 수 없습니다."


@mcp.tool()
async def nexus_suggest(
    query: str,
    tenant: str = "default",
    limit: int = 10,
) -> str:
    """엔티티 자동완성/검색.

    이름 또는 별칭으로 엔티티를 검색한다.
    서비스, 토픽, 팀 등의 엔티티를 찾을 때 사용한다.

    Args:
        query: 검색어
        tenant: 테넌트 ID
        limit: 최대 결과 수
    """
    result = await _api_call("get", "/entities/suggest", params={
        "q": query,
        "tenant": tenant,
        "limit": limit,
    })

    if not result.get("success"):
        return f"엔티티 검색 실패: {result.get('error', '알 수 없는 오류')}"

    entities = result.get("data", [])
    if not entities:
        return f"'{query}'와 일치하는 엔티티가 없습니다."

    lines = []
    for e in entities:
        aliases = f" (별칭: {', '.join(e['aliases'])})" if e.get("aliases") else ""
        lines.append(f"- {e['name']} [{e['type']}]{aliases}")
        if e.get("description"):
            lines.append(f"  {e['description']}")

    return "\n".join(lines)


@mcp.tool()
async def nexus_diff(
    tenant: str = "default",
    flag_filter: str | None = None,
    entity_filter: str | None = None,
) -> str:
    """설계-관측 불일치(diff) 보고서 조회.

    문서에 정의된 관계(설계)와 실제 OTel trace(관측) 간의 차이를 분석한다.
    diff 유형: doc_only(문서에만 존재), observed_only(관측에만 존재), conflict(불일치)

    Args:
        flag_filter: 특정 diff 유형만 조회 (doc_only|observed_only|conflict)
        entity_filter: 특정 엔티티 관련 diff만 조회
        tenant: 테넌트 ID
    """
    params: dict = {"tenant": tenant}
    if flag_filter:
        params["flag_filter"] = flag_filter
    if entity_filter:
        params["entity_filter"] = entity_filter

    result = await _api_call("get", "/diff", params=params)

    if not result.get("success"):
        return f"Diff 조회 실패: {result.get('error', '알 수 없는 오류')}"

    data = result["data"]
    lines = [
        f"설계 edge: {data['total_designed_edges']}개, 관측 edge: {data['total_observed_edges']}개",
    ]

    diffs = data.get("diffs", [])
    if not diffs:
        lines.append("불일치 없음 — 설계와 관측이 일치합니다.")
    else:
        for d in diffs:
            flag = d["flag"]
            lines.append(f"\n[{flag}] {d['from_name']} → {d['to_name']} ({d['edge_type']})")
            if d.get("detail"):
                lines.append(f"  상세: {d['detail']}")

    lines.append(f"\n생성 시각: {data.get('generated_at', 'N/A')}")
    return "\n".join(lines)


@mcp.tool()
async def archon_claim_value(
    concept: str,
    tenant: str = "default",
    classification_max: str = "INTERNAL",
) -> str:
    """Archon — 개념의 도메인 값/불변식 현재값 조회.

    "Basic 프로젝트 최대 몇 개?", "작업 제한 시간?" 같은 도메인 전제조건의
    *현재 값*을 코드 상수에서 직접 읽어 답한다. 값은 조회 시점에 재읽기하므로 낡지 않으며,
    확실한 것은 단정하고 모르는 것은 모른다고 정직히 표기한다(캘리브레이션).

    Args:
        concept: 개념 (예: Basic, 프로젝트, 작업)
        tenant: 테넌트 ID
        classification_max: 최대 접근 등급 (PUBLIC|INTERNAL|RESTRICTED)
    """
    result = await _api_call("get", "/claims/value", params={
        "concept": concept,
        "tenant": tenant,
        "classification_max": classification_max,
    })
    if not result.get("success"):
        return f"값 조회 실패: {result.get('error', '알 수 없는 오류')}"

    answers = result.get("data", [])
    if not answers:
        return f"'{concept}'에 등록된 값 claim이 없습니다. (모름 — 추측하지 않음)"

    lines = []
    for a in answers:
        if a["value"] is not None and a["confidence"] == "high" and a["fresh"]:
            line = f"- {a['statement']}: 현재 {a['value']} (확실: 코드 상수 {a['source']}, 조회 시점 기준)"
            if a.get("drifted"):
                line += f" ⚠️ {a['note']}"
            lines.append(line)
        elif a["value"] is None:
            lines.append(f"- {a['statement']}: 값 확인 실패 — {a['note']}. (확신 없음)")
        else:
            lines.append(f"- {a['statement']}: {a['value']} (신뢰 {a['confidence']})")
    return "\n".join(lines)


@mcp.tool()
async def archon_grade_authority(
    grade: str | None = None,
    enum_name: str = "GradeType",
    subpath: str = "",
) -> str:
    """Archon — 등급 계층의 권한 도출. "MEMBER가 뭘 할 수 있나" 같은 *창발적/여집합* 질문.

    코드의 권한 게이트(예: '이 액션은 ≥MODERATOR 필요')를 추출해, 각 등급이 차단되는
    액션을 여집합으로 도출한다. 고정 게이트 여집합은 확실(high), '액션가드 vs 필터'
    의미확정은 확인 필요(medium) — 정직하게 구분해 표기한다.

    Args:
        grade: 특정 등급만 (예: MEMBER). 생략 시 전체 등급.
        enum_name: 등급 enum 이름 (기본 GradeType)
        subpath: 코드 하위경로로 범위 제한
    """
    result = await _api_call("get", "/claims/grade-authority", params={
        "enum_name": enum_name, "subpath": subpath,
    })
    if not result.get("success"):
        return f"권한 도출 실패: {result.get('error', '알 수 없는 오류')}"

    d = result["data"]
    cap = d.get("capabilities", {})
    lines = [f"등급 레벨: {d.get('levels', {})}", f"\n고정 게이트 {len(d.get('fixed_gates', []))}개 (액션 → 요구등급):"]
    for g in d.get("fixed_gates", []):
        lines.append(f"  - {g['action']}  [{g['check']}({g['grade']})]")
    targets = [grade] if grade else list(cap.keys())
    lines.append("")
    for gr in targets:
        if gr in cap:
            b = cap[gr]["blocked"]
            lines.append(f"{gr}({cap[gr]['level']}): 차단 {len(b)}개 — {b if b else '없음(고정 게이트 모두 통과)'}")
        elif grade:
            lines.append(f"'{gr}' 등급을 {enum_name}에서 찾지 못함. (확신 없음)")
    lines.append("\n(확실: 고정 게이트 여집합. '액션가드 vs 필터' 의미확정은 확인 필요 — medium.)")
    return "\n".join(lines)


@mcp.tool()
async def nexus_supersede(old_ref: str, new_ref: str, tenant: str = "default") -> str:
    """옛 문서를 새 문서로 supersede(명시적·멱등). old/new 는 rid 또는 경로/URI 를 받는다.

    자동 감지 없음 — 책임자가 명시적으로 선언한다. 경로/URI 는 서버가 active 문서 rid 로
    해석하며, 모호(동명 다건)하면 거부한다. tenant 인자는 조언용(advisory)이며 서버가
    강제 재정의한다: effective_scope 는 요청 tenant 를 무시하고 항상 principal 의 tenant 를
    사용한다(상한이 아니라 무시). 다른 값을 넣어도 반영되지 않는다.

    Args:
        old_ref: 대체될 옛 문서 — rid 또는 경로/URI
        new_ref: 대체하는 새 문서 — rid 또는 경로/URI
        tenant: 테넌트 ID (advisory — 서버가 principal 의 tenant 로 강제 재정의, 무시됨)
    """
    result = await _api_call("post", "/supersede", json={
        "old_ref": old_ref,
        "new_ref": new_ref,
        "tenant": tenant,
    })
    if not result.get("success"):
        return f"supersede 실패: {result.get('error', '알 수 없는 오류')}"
    d = result["data"]
    old_rid = d.get("old_rid", old_ref)
    # 되돌리려면 rid 가 필요하다 — 그때 옛 문서는 active 가 아니라 경로로 다시 못 찾는다.
    return (f"{old_ref} → {new_ref}: {d['result']}\n"
            f"되돌리려면: nexus_unsupersede(rid='{old_rid}', reason='...')")


@mcp.tool()
async def nexus_status() -> str:
    """Nexus 시스템 상태 확인.

    DB 연결, Ollama, Tempo 상태와 인덱싱 통계를 조회한다.
    """
    result = await _api_call("get", "/status")

    if not result.get("success"):
        return f"상태 조회 실패: {result.get('error', '알 수 없는 오류')}"

    data = result["data"]
    lines = [
        "--- Nexus 시스템 상태 ---",
        f"DB 연결: {'정상' if data.get('db_connected') else '실패'}",
        f"Ollama: {'정상' if data.get('ollama_connected') else '실패'}",
        f"Tempo: {'정상' if data.get('tempo_connected') else '실패'}",
    ]

    if data.get("db_connected"):
        lines.extend([
            "",
            f"문서: {data.get('documents_count', 0)}개",
            f"청크: {data.get('chunks_count', 0)}개",
            f"엔티티: {data.get('entities_count', 0)}개",
            f"설계 edge: {data.get('edges_count', 0)}개",
            f"관측 edge: {data.get('observed_edges_count', 0)}개",
            f"격리됨: {data.get('quarantined_count', 0)}개",
        ])

        diff = data.get("diff_summary", {})
        if diff:
            lines.append(
                f"\nDiff: doc_only={diff.get('doc_only_count', 0)}, "
                f"observed_only={diff.get('observed_only_count', 0)}, "
                f"conflict={diff.get('conflict_count', 0)}"
            )

    return "\n".join(lines)


# ── 소스(Notion) 관리 — SPEC-nexus-notion-source-console §4.8 ──
# 웹 UI 와 **같은 엔드포인트**를 쓴다. 기능이 API 를 건너뛰면 사람도 에이전트도 그것을 잃는다.


@mcp.tool()
async def nexus_sources_list() -> str:
    """연결된 Notion root 페이지 목록과 토큰 설정 여부를 조회한다."""
    result = await _api_call("get", "/sources/notion/roots")
    if not result.get("success"):
        return f"소스 조회 실패: {result['error']}"

    data = result["data"]
    if not data["roots"]:
        return "연결된 Notion 페이지가 없습니다. nexus_sources_add 로 추가하세요."
    lines = [f"Notion 토큰: {'설정됨' if data['token_configured'] else '없음 — 동기화 불가'}"]
    lines += [f"- {r['root_id']}  {r['label'] or ''}".rstrip() for r in data["roots"]]
    return "\n".join(lines)


@mcp.tool()
async def nexus_sources_add(url_or_id: str, label: str = "") -> str:
    """Notion root 페이지를 연결한다. 브라우저 URL 도, 대시 유무 무관한 page id 도 받는다.

    그 페이지 하위 트리 전체가 이후 동기화 대상이 된다.
    """
    result = await _api_call("post", "/sources/notion/roots",
                             json={"url_or_id": url_or_id, "label": label})
    if not result.get("success"):
        return f"추가 실패: {result['error']}"
    return f"연결됨: {result['data']['root_id']}"


@mcp.tool()
async def nexus_sources_sync(reconcile: bool = False, dry_run: bool = False,
                             confirm_plan: str = "") -> str:
    """Notion 동기화를 시작한다. 즉시 run_id 를 돌려주고 백그라운드에서 돈다.

    reconcile=True 는 Notion 에서 사라진 문서를 검색에서 내린다. **먼저 dry_run=True 로
    무엇이 내려갈지 확인**하고, 그 run_id 를 confirm_plan 에 넣어 적용하는 것이 안전하다.
    confirm_plan 은 다른 인자와 함께 쓸 수 없다(미리보기와 다른 조건으로 적용되는 것을 막는다).
    """
    body = {"confirm_plan": confirm_plan} if confirm_plan else {
        "reconcile": reconcile, "dry_run": dry_run,
    }
    result = await _api_call("post", "/sources/notion/sync", json=body)
    if not result.get("success"):
        return f"동기화 시작 실패: {result['error']}"
    return f"run_id={result['data']['run_id']} — nexus_sync_status 로 진행을 확인하세요"


@mcp.tool()
async def nexus_sync_status(run_id: str = "") -> str:
    """동기화 실행 상태. run_id 를 비우면 가장 최근 실행을 본다."""
    path = f"/sources/notion/sync/{run_id}" if run_id else "/sources/notion/sync/latest"
    result = await _api_call("get", path)
    if not result.get("success"):
        return f"상태 조회 실패: {result['error']}"

    d = result["data"]
    c = d.get("counts") or {}
    lines = [
        f"run {d['run_id']} — {d['status']}",
        f"적재 {c.get('ingested', 0)} · 변경없음 {c.get('idempotent', 0)} · 건너뜀 {c.get('skipped', 0)}",
    ]
    if d.get("reconcile"):
        lines.append(f"내림 {c.get('pruned', 0)} · 되살림 {c.get('revived', 0)}")
    if d.get("reason"):
        lines.append(f"사유: {d['reason']}")
    plan = d.get("plan") or {}
    if d.get("dry_run") and plan.get("prune"):
        lines.append(f"적용 시 내려갈 문서 {len(plan['prune'])}건:")
        lines += [f"  - {p.get('title') or p['rid']}" for p in plan["prune"][:20]]
        lines.append(f"적용하려면: nexus_sources_sync(confirm_plan='{d['run_id']}')")
    return "\n".join(lines)


# ── 문서 생애주기 — SPEC-nexus-document-lifecycle §4.6 ──
# 웹 UI 와 **같은 엔드포인트**. 사람이 확인 패널에서 읽는 문장을 에이전트도 응답에서 읽는다.

_HIDE_NOTE = "검색에서 사라집니다. 문서와 청크는 지워지지 않으며 언제든 되돌릴 수 있습니다."

_ORIGIN_LABEL = {"notion": "Notion", "upload": "업로드", "file": "파일"}

# API 는 기계코드로 거절한다(HTTP 계약). 그대로 뱉으면 호출자는 다음에 뭘 해야 할지 모른다.
_ERROR_PROSE = {
    "reason_required": "사유가 필요합니다 — reason 인자를 채워 다시 호출하세요.",
    "use_unsupersede": "이 문서는 다른 문서로 대체된 상태입니다. "
                       "nexus_unsupersede(rid, reason) 를 쓰세요 — 되돌리는 말이 다릅니다.",
    "already_superseded": "이 문서는 이미 다른 문서로 대체되었습니다. 숨길 대상이 아닙니다.",
}


def _prose(error: str) -> str:
    return _ERROR_PROSE.get(error, error or "알 수 없는 오류")


@mcp.tool()
async def nexus_documents_search(
    q: str = "",
    status: str = "active",
    origin: str = "",
    limit: int = 20,
) -> str:
    """인덱싱된 문서를 **제목으로** 찾는다. 내용 검색은 nexus_search 를 쓴다.

    다른 문서 생애주기 도구들이 요구하는 rid 를 얻는 경로다.

    Args:
        q: 제목 부분일치 (대소문자 무시). 비우면 전체.
        status: active | hidden | pruned | superseded | all
                (hidden=사람이 숨김, pruned=Notion 에서 사라져 내려감)
        origin: notion | upload | file — 비우면 전체
        limit: 최대 건수
    """
    result = await _api_call("get", "/documents", params={
        "q": q, "status": status, "origin": origin, "limit": limit,
    })
    if not result.get("success"):
        return f"문서 조회 실패: {result.get('error', '알 수 없는 오류')}"

    data = result["data"]
    docs = data.get("documents", [])
    if not docs:
        return "해당하는 문서가 없습니다."

    lines = [f"{len(docs)}건 (전체 {data.get('total', len(docs))}건)"]
    for d in docs:
        origin_txt = _ORIGIN_LABEL.get(d.get("origin"), d.get("origin", "?"))
        if d.get("origin_url"):
            origin_txt += f" {d['origin_url']}"
        lines.append(
            f"- {d['title']}  [{d['status']}]  청크 {d.get('chunk_count', 0)}\n"
            f"    rid: {d['rid']}  출처: {origin_txt}"
        )
    return "\n".join(lines)


@mcp.tool()
async def nexus_document_hide(rid: str) -> str:
    """문서를 검색에서 내린다(되돌릴 수 있음). rid 는 nexus_documents_search 로 찾는다.

    Notion 에서 온 문서를 숨기면 다음 동기화가 되살리지 않는다(hold). superseded 문서는
    거부한다 — 그건 이미 다른 문서로 대체된 것이고, 되돌리는 말이 다르다(nexus_unsupersede).
    """
    result = await _api_call("post", f"/documents/{rid}/hide")
    if not result.get("success"):
        return f"숨기기 실패: {_prose(result.get('error', ''))}"
    if result["data"]["result"] == "noop":
        return f"{rid}: 이미 숨겨져 있습니다."
    return (f"{rid}: 숨겼습니다. {_HIDE_NOTE}\n"
            f"되돌리려면: nexus_document_restore(rid='{rid}')")


@mcp.tool()
async def nexus_document_restore(rid: str) -> str:
    """숨겨졌거나 Notion 에서 사라져 내려간 문서를 다시 검색에 올린다.

    superseded 문서에는 쓸 수 없다 — nexus_unsupersede 를 쓴다(사유가 필요하다).
    """
    result = await _api_call("post", f"/documents/{rid}/restore")
    if not result.get("success"):
        return f"되돌리기 실패: {_prose(result.get('error', ''))}"
    if result["data"]["result"] == "noop":
        return f"{rid}: 이미 검색에 나타납니다."
    return f"{rid}: 되돌렸습니다. 이 문서가 다시 검색에 나타납니다."


@mcp.tool()
async def nexus_unsupersede(rid: str, reason: str) -> str:
    """supersession 을 취소해 옛 문서를 다시 검색에 올린다. **사유 필수.**

    체인은 역순으로만 풀린다: v1→v2→v3 에서 v1 을 먼저 되살리면 v3 와 공존하게 되므로
    서버가 거부하고 막고 있는 문서를 이름으로 알려준다. v2 부터 되돌린다.

    Args:
        rid: 되살릴 문서 rid (supersede 응답이 old_rid 로 알려준다)
        reason: 왜 되돌리는가 — 원장(doc_supersession_events)에 남는다
    """
    result = await _api_call("post", f"/documents/{rid}/unsupersede", json={"reason": reason})
    if not result.get("success"):
        return f"supersession 취소 실패: {_prose(result.get('error', ''))}"
    if result["data"]["result"] == "noop":
        return f"{rid}: superseded 상태가 아닙니다."
    return f"{rid}: supersession 을 취소했습니다. 이 문서가 다시 검색에 나타납니다."
