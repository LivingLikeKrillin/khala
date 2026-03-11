"""Graph 데이터 접근 추상화.

GraphRepository Protocol은 search.py, diff_engine.py, api.py, otel_aggregator.py
4곳에서 사용된다. PostgreSQL → Neo4j 전환 시 구현체만 교체하면 된다.

사용법:
    graph: GraphRepository = PostgresGraphRepository(db)
    neighbors = await graph.get_neighbors(entity_rid, hops=2)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass
class EdgeResult:
    """Graph 조회 결과의 edge 표현."""
    rid: str
    edge_type: str
    from_rid: str
    from_name: str
    to_rid: str
    to_name: str
    confidence: float
    source_category: str  # DESIGNED | MANUAL
    hop: int = 1


@dataclass
class ObservedEdgeResult:
    """Graph 조회 결과의 observed edge 표현."""
    rid: str
    edge_type: str
    from_rid: str
    from_name: str
    to_rid: str
    to_name: str
    call_count: int
    error_rate: float
    latency_p95: float | None
    last_seen_at: str
    sample_trace_ids: list[str]
    trace_query_ref: str


@dataclass
class SubGraph:
    """entity 중심 서브그래프."""
    center_rid: str
    center_name: str
    edges: list[EdgeResult]
    observed_edges: list[ObservedEdgeResult]


@dataclass
class DiffItem:
    """설계-관측 diff 항목."""
    flag: str  # doc_only | observed_only | conflict
    edge_rid: str | None
    observed_edge_rid: str | None
    from_name: str
    to_name: str
    edge_type: str
    detail: str


class GraphRepository(Protocol):
    """Graph 데이터 접근 인터페이스.

    1.0: PostgresGraphRepository (adjacency table + recursive CTE)
    2.0: Neo4jGraphRepository (Cypher + Leiden community detection)

    직접 edge/observed_edge SQL을 작성하지 말 것. 이 Protocol을 통해 접근.
    """

    async def get_neighbors(self, entity_rid: str, hops: int = 1) -> SubGraph:
        """entity의 이웃 조회. designed + observed 양쪽 반환."""
        ...

    async def get_subgraph(self, center_rid: str, radius: int = 2) -> SubGraph:
        """entity 중심 서브그래프 조회."""
        ...

    async def upsert_edges(self, edges: list[dict]) -> int:
        """edge 일괄 upsert (idempotent). 반환: upsert된 수."""
        ...

    async def upsert_observed_edges(self, edges: list[dict]) -> int:
        """observed_edge 일괄 upsert. 반환: upsert된 수."""
        ...

    async def find_path(self, from_rid: str, to_rid: str, max_hops: int = 4) -> list[EdgeResult]:
        """두 entity 간 최단 경로 탐색."""
        ...

    async def get_diff(self, tenant: str) -> list[DiffItem]:
        """설계 edge vs 관측 edge 비교. v_edge_diff 뷰 활용."""
        ...


class PostgresGraphRepository:
    """PostgreSQL adjacency table + recursive CTE 기반 구현.

    100-500 문서 규모에서 entity 수백, edge 수천 → 이 구현으로 충분.
    f_graph_neighbors() DB 함수와 v_edge_diff 뷰를 활용한다.
    """

    def __init__(self, pool) -> None:
        self._pool = pool

    async def _fetch(self, query: str, *args) -> list:
        async with self._pool.acquire() as conn:
            return await conn.fetch(query, *args)

    async def _execute(self, query: str, *args) -> str:
        async with self._pool.acquire() as conn:
            return await conn.execute(query, *args)

    async def get_neighbors(self, entity_rid: str, hops: int = 1) -> SubGraph:
        """f_graph_neighbors() DB 함수 호출 + observed_edges 조회."""
        # 엔티티 이름 조회
        center_row = await self._fetch(
            "SELECT name FROM entities WHERE rid = $1", entity_rid,
        )
        center_name = center_row[0]["name"] if center_row else entity_rid

        # Designed edges (f_graph_neighbors 함수 사용)
        edge_rows = await self._fetch(
            "SELECT * FROM f_graph_neighbors($1, $2)", entity_rid, hops,
        )
        edges = [
            EdgeResult(
                rid=r["edge_rid"], edge_type=r["edge_type"],
                from_rid=r["from_rid"], from_name=r["from_name"],
                to_rid=r["to_rid"], to_name=r["to_name"],
                confidence=r["confidence"],
                source_category=r["source_category"],
                hop=r["hop"],
            )
            for r in edge_rows
        ]

        # Observed edges
        obs_rows = await self._fetch(
            """
            SELECT o.rid, o.edge_type, o.from_rid, ef.name as from_name,
                   o.to_rid, et.name as to_name,
                   o.call_count, o.error_rate, o.latency_p95,
                   o.last_seen_at, o.sample_trace_ids, o.trace_query_ref
            FROM observed_edges o
            JOIN entities ef ON o.from_rid = ef.rid
            JOIN entities et ON o.to_rid = et.rid
            WHERE o.status = 'active'
              AND (o.from_rid = $1 OR o.to_rid = $1)
            """,
            entity_rid,
        )
        observed = [
            ObservedEdgeResult(
                rid=r["rid"], edge_type=r["edge_type"],
                from_rid=r["from_rid"], from_name=r["from_name"],
                to_rid=r["to_rid"], to_name=r["to_name"],
                call_count=r["call_count"], error_rate=r["error_rate"],
                latency_p95=r["latency_p95"],
                last_seen_at=str(r["last_seen_at"]),
                sample_trace_ids=list(r["sample_trace_ids"] or []),
                trace_query_ref=r["trace_query_ref"] or "",
            )
            for r in obs_rows
        ]

        return SubGraph(
            center_rid=entity_rid, center_name=center_name,
            edges=edges, observed_edges=observed,
        )

    async def get_subgraph(self, center_rid: str, radius: int = 2) -> SubGraph:
        """entity 중심 서브그래프 (get_neighbors의 확장판)."""
        return await self.get_neighbors(center_rid, hops=radius)

    async def upsert_edges(self, edges: list[dict]) -> int:
        """edge 일괄 upsert. idempotent."""
        count = 0
        for e in edges:
            await self._execute(
                """
                INSERT INTO edges (
                    rid, rtype, tenant, classification, owner,
                    source_kind, status, created_at, updated_at,
                    edge_type, from_rid, to_rid, confidence, source_category,
                    prov_pipeline, prov_inputs
                ) VALUES (
                    $1, 'edge', $2, 'INTERNAL', 'indexer',
                    'git', 'active', now(), now(),
                    $3, $4, $5, $6, $7,
                    $8, $9
                )
                ON CONFLICT (rid) DO UPDATE SET
                    confidence = GREATEST(edges.confidence, EXCLUDED.confidence),
                    updated_at = now()
                """,
                e["rid"], e.get("tenant", "default"),
                e["edge_type"], e["from_rid"], e["to_rid"],
                e.get("confidence", 0.5), e.get("source_category", "DESIGNED"),
                e.get("prov_pipeline", "indexer-v1"),
                e.get("prov_inputs", []),
            )
            count += 1
        return count

    async def upsert_observed_edges(self, edges: list[dict]) -> int:
        """observed_edge 일괄 upsert. 메트릭 갱신."""
        count = 0
        for e in edges:
            await self._execute(
                """
                INSERT INTO observed_edges (
                    rid, rtype, tenant, classification, owner,
                    source_uri, source_kind, status, created_at, updated_at,
                    edge_type, from_rid, to_rid,
                    call_count, error_rate, latency_p50, latency_p95, latency_p99,
                    protocol, interaction_style,
                    sample_trace_ids, trace_query_ref, resolved_via,
                    window_start, window_end, last_seen_at,
                    prov_pipeline
                ) VALUES (
                    $1, 'observed_edge', $2, 'INTERNAL', 'otel-aggregator',
                    'otlp://tempo', 'otel', 'active', now(), now(),
                    $3, $4, $5,
                    $6, $7, $8, $9, $10,
                    $11, $12,
                    $13, $14, $15,
                    $16, $17, now(),
                    'otel-agg-v1'
                )
                ON CONFLICT (rid) DO UPDATE SET
                    call_count = EXCLUDED.call_count,
                    error_rate = EXCLUDED.error_rate,
                    latency_p50 = EXCLUDED.latency_p50,
                    latency_p95 = EXCLUDED.latency_p95,
                    latency_p99 = EXCLUDED.latency_p99,
                    sample_trace_ids = EXCLUDED.sample_trace_ids,
                    trace_query_ref = EXCLUDED.trace_query_ref,
                    window_start = EXCLUDED.window_start,
                    window_end = EXCLUDED.window_end,
                    last_seen_at = now(),
                    updated_at = now()
                """,
                e["rid"], e.get("tenant", "default"),
                e.get("edge_type", "CALLS_OBSERVED"),
                e["from_rid"], e["to_rid"],
                e.get("call_count", 0), e.get("error_rate", 0.0),
                e.get("latency_p50"), e.get("latency_p95"), e.get("latency_p99"),
                e.get("protocol", ""), e.get("interaction_style", ""),
                e.get("sample_trace_ids", []), e.get("trace_query_ref", ""),
                e.get("resolved_via", ""),
                e.get("window_start"), e.get("window_end"),
            )
            count += 1
        return count

    async def find_path(
        self, from_rid: str, to_rid: str, max_hops: int = 4,
    ) -> list[EdgeResult]:
        """두 entity 간 최단 경로 BFS 탐색."""
        rows = await self._fetch(
            """
            WITH RECURSIVE path AS (
                SELECT 1 as hop, e.rid as edge_rid, e.edge_type,
                       e.from_rid, ef.name as from_name,
                       e.to_rid, et.name as to_name,
                       e.confidence, e.source_category,
                       ARRAY[e.rid] as visited
                FROM edges e
                JOIN entities ef ON e.from_rid = ef.rid
                JOIN entities et ON e.to_rid = et.rid
                WHERE e.status = 'active' AND e.from_rid = $1
                UNION ALL
                SELECT p.hop + 1, e.rid, e.edge_type,
                       e.from_rid, ef.name, e.to_rid, et.name,
                       e.confidence, e.source_category,
                       p.visited || e.rid
                FROM edges e
                JOIN entities ef ON e.from_rid = ef.rid
                JOIN entities et ON e.to_rid = et.rid
                JOIN path p ON e.from_rid = p.to_rid
                WHERE e.status = 'active'
                  AND e.rid != ALL(p.visited)
                  AND p.hop < $3
            )
            SELECT * FROM path WHERE to_rid = $2
            ORDER BY hop LIMIT 1
            """,
            from_rid, to_rid, max_hops,
        )
        return [
            EdgeResult(
                rid=r["edge_rid"], edge_type=r["edge_type"],
                from_rid=r["from_rid"], from_name=r["from_name"],
                to_rid=r["to_rid"], to_name=r["to_name"],
                confidence=r["confidence"],
                source_category=r["source_category"],
                hop=r["hop"],
            )
            for r in rows
        ]

    async def get_diff(self, tenant: str) -> list[DiffItem]:
        """v_edge_diff 뷰로 설계-관측 불일치 조회."""
        rows = await self._fetch(
            "SELECT * FROM v_edge_diff",
        )
        return [
            DiffItem(
                flag=r["diff_type"],
                edge_rid=r["edge_rid"],
                observed_edge_rid=r["obs_rid"],
                from_name=r["from_name"],
                to_name=r["to_name"],
                edge_type=r["edge_type"],
                detail=f"confidence={r['confidence']}, calls={r['call_count']}, p95={r['latency_p95']}",
            )
            for r in rows
        ]
