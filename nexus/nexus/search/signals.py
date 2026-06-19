"""검색 품질 신호 추출(순수) + 영속(best-effort IO).

extract_signals는 SearchResult/AnswerResult에서 신호를 조립하는 순수 함수,
record_search는 structlog(항상) + best-effort DB insert(절대 raise 안 함)다.
a2a/audit.py의 record_audit 패턴을 미러링한다. 원문 query는 sha256+len으로만 기록.
"""
from __future__ import annotations

import asyncio
import hashlib
from dataclasses import dataclass
from typing import TYPE_CHECKING

import structlog

from nexus import db

if TYPE_CHECKING:  # 런타임 import 불필요(순환 회피) — 속성 접근만 한다
    from nexus.llm.answer import AnswerResult
    from nexus.search.hybrid import SearchResult

log = structlog.get_logger("nexus.search.signals")

SIGNAL_EVENT = "search.signal"
_GRAPH_ROUTES = ("hybrid_then_graph", "graph_then_hybrid")


def query_sha256(query: str) -> str:
    """원문 query의 sha256 hex — 신호에 들어갈 수 있는 유일한 형태."""
    return hashlib.sha256(query.encode("utf-8")).hexdigest()


@dataclass
class SearchSignals:
    path: str
    tenant: str | None
    clearance: str | None
    route: str
    query_sha256: str
    query_len: int
    n_snippets: int
    top_score: float | None
    n_entities: int
    graph_requested: bool
    n_graph_edges: int
    no_answer: bool
    llm_failed: bool
    latency_ms: int


def extract_signals(
    result: SearchResult,
    answer: AnswerResult | None = None,
    *,
    path: str,
    tenant: str | None,
    clearance: str | None,
    query: str,
    n_entities: int = 0,
    latency_ms: int = 0,
) -> SearchSignals:
    """SearchResult(+선택 AnswerResult)와 진입점 스칼라에서 신호를 조립. 순수."""
    hits = result.hits
    graph = result.graph
    n_graph_edges = (len(graph.edges) + len(graph.observed_edges)) if graph else 0
    route = result.route_used or ""
    return SearchSignals(
        path=path,
        tenant=tenant,
        clearance=clearance,
        route=route,
        query_sha256=query_sha256(query),
        query_len=len(query),
        n_snippets=len(hits),
        top_score=hits[0].score if hits else None,
        n_entities=n_entities,
        graph_requested=route in _GRAPH_ROUTES,
        n_graph_edges=n_graph_edges,
        no_answer=len(hits) == 0,
        llm_failed=bool(answer.llm_failed) if answer is not None else False,
        latency_ms=latency_ms,
    )


async def _persist(sig: SearchSignals) -> None:
    """search_log에 1행 insert. 실패는 삼킴(신호 영속은 요청 경로를 깨지 않는다)."""
    try:
        await db.execute(
            """
            INSERT INTO search_log (
                path, tenant, clearance, route, query_sha256, query_len,
                n_snippets, top_score, n_entities, graph_requested, n_graph_edges,
                no_answer, llm_failed, latency_ms
            ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14)
            """,
            sig.path, sig.tenant, sig.clearance, sig.route, sig.query_sha256, sig.query_len,
            sig.n_snippets, sig.top_score, sig.n_entities, sig.graph_requested,
            sig.n_graph_edges, sig.no_answer, sig.llm_failed, sig.latency_ms,
        )
    except Exception as exc:  # noqa: BLE001 - signal persistence must never break the request
        log.warning("search.signal.persist_failed", error=str(exc))


async def record_search(sig: SearchSignals, *, await_persist: bool = False) -> None:
    """structlog(항상, 동기) + best-effort DB 적재. 절대 raise 안 함.

    서버 경로(api/a2a)는 기본 fire-and-forget(create_task) — 응답 지연에 DB 쓰기 미가산.
    CLI는 await_persist=True — asyncio.run 종료/close_pool 이전에 적재 완료 보장.
    """
    log.info(
        SIGNAL_EVENT,
        path=sig.path, tenant=sig.tenant, clearance=sig.clearance, route=sig.route,
        query_sha256=sig.query_sha256, query_len=sig.query_len,
        n_snippets=sig.n_snippets, top_score=sig.top_score, n_entities=sig.n_entities,
        graph_requested=sig.graph_requested, n_graph_edges=sig.n_graph_edges,
        no_answer=sig.no_answer, llm_failed=sig.llm_failed, latency_ms=sig.latency_ms,
    )
    if not db.has_pool():
        return
    if await_persist:
        await _persist(sig)
    else:
        asyncio.create_task(_persist(sig))
