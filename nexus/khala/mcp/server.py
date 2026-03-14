"""Khala MCP Server — AI Agent용 tool provider.

FastMCP를 사용하여 Khala API를 MCP 도구로 노출한다.
Agent가 stdio 또는 streamable-http로 접속하여 검색/그래프/상태를 질의할 수 있다.

실행:
    # stdio (로컬 Agent 연동)
    python -m khala.mcp.server

    # streamable-http (원격 Agent 연동)
    python -m khala.mcp.server --transport http --port 8001
"""

from __future__ import annotations

import os

import httpx
from mcp.server.fastmcp import FastMCP

KHALA_API_URL = os.getenv("KHALA_API_URL", "http://localhost:8000")

mcp = FastMCP(
    "Khala",
    instructions="Enterprise RAG + GraphRAG — 조직 내부 지식과 운영 사실 기반 검색·추론",
)


async def _api_call(method: str, path: str, **kwargs) -> dict:
    """Khala API 호출 래퍼."""
    async with httpx.AsyncClient(timeout=60.0, base_url=KHALA_API_URL) as client:
        resp = await getattr(client, method)(path, **kwargs)

    if resp.status_code == 503:
        return {"success": False, "error": "Khala 데이터베이스에 연결할 수 없습니다"}

    data = resp.json()
    if not data.get("success"):
        return {"success": False, "error": data.get("error", f"API 오류 (HTTP {resp.status_code})")}

    return data


@mcp.tool()
async def khala_search(
    query: str,
    top_k: int = 10,
    route: str = "auto",
    classification_max: str = "INTERNAL",
    tenant: str = "default",
    include_graph: bool = True,
) -> str:
    """Khala 하이브리드 검색 (BM25 + Vector + Graph).

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
async def khala_answer(
    query: str,
    top_k: int = 10,
    route: str = "auto",
    classification_max: str = "INTERNAL",
    tenant: str = "default",
) -> str:
    """Khala 검색 + LLM 근거 기반 답변 생성.

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
async def khala_graph(
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
async def khala_suggest(
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
async def khala_diff(
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
async def khala_status() -> str:
    """Khala 시스템 상태 확인.

    DB 연결, Ollama, Tempo 상태와 인덱싱 통계를 조회한다.
    """
    result = await _api_call("get", "/status")

    if not result.get("success"):
        return f"상태 조회 실패: {result.get('error', '알 수 없는 오류')}"

    data = result["data"]
    lines = [
        "--- Khala 시스템 상태 ---",
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
