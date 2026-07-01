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
        return {"success": False, "error": data.get("error", f"API 오류 (HTTP {resp.status_code})")}

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
async def nexus_supersede(old_rid: str, new_rid: str, tenant: str = "default") -> str:
    """옛 문서를 새 문서로 supersede(명시적·멱등). old 를 new 로 대체하고 검색에서 배제한다.

    자동 감지 없음 — 책임자가 명시적으로 선언한다. tenant 인자는 조언용(advisory)이며
    서버가 강제 재정의한다: effective_scope 는 요청 tenant 를 무시하고 항상
    NEXUS_MCP_TOKEN principal 의 tenant 를 사용한다(상한이 아니라 무시). 다른 값을 넣어도
    반영되지 않는다.

    Args:
        old_rid: 대체될 옛 문서 rid
        new_rid: 대체하는 새 문서 rid
        tenant: 테넌트 ID (advisory — 서버가 principal 의 tenant 로 강제 재정의, 무시됨)
    """
    result = await _api_call("post", "/supersede", json={
        "old_rid": old_rid,
        "new_rid": new_rid,
        "tenant": tenant,
    })
    if not result.get("success"):
        return f"supersede 실패: {result.get('error', '알 수 없는 오류')}"
    return f"{old_rid} → {new_rid}: {result['data']['result']}"


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
