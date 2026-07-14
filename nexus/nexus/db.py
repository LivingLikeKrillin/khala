"""PostgreSQL 연결 관리 + 쿼리 헬퍼.

asyncpg connection pool을 관리하고, CRM 기반 공통 쿼리를 제공한다.
모든 DB 접근은 이 모듈을 통해 이루어져야 한다.
"""

from __future__ import annotations

import os
from typing import Any

import asyncpg
import structlog

logger = structlog.get_logger(__name__)

# 전역 connection pool
_pool: asyncpg.Pool | None = None


def has_pool() -> bool:
    """A live pool이 이미 있는지(연결 시도 없이) 확인. best-effort 부가 작업의 게이트."""
    return _pool is not None


async def get_pool() -> asyncpg.Pool:
    """Connection pool 획득. 없으면 생성."""
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(
            dsn=os.getenv("DATABASE_URL", "postgresql://nexus:nexus@localhost:5432/nexus"),
            min_size=2,
            max_size=10,
        )
        logger.info("db_pool_created")
    return _pool


async def close_pool() -> None:
    """애플리케이션 종료 시 pool 정리."""
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None
        logger.info("db_pool_closed")


async def fetch_all(query: str, *args: Any) -> list[asyncpg.Record]:
    """SELECT 쿼리 실행. 결과 목록 반환."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetch(query, *args)


async def fetch_one(query: str, *args: Any) -> asyncpg.Record | None:
    """SELECT 쿼리 실행. 결과 1건 반환."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchrow(query, *args)


async def fetch_val(query: str, *args: Any) -> Any:
    """SELECT 쿼리 실행. 단일 값 반환."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchval(query, *args)


async def execute(query: str, *args: Any) -> str:
    """INSERT/UPDATE/DELETE 실행. 영향 받은 행 수 반환."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.execute(query, *args)


async def execute_many(query: str, args_list: list[tuple]) -> None:
    """배치 INSERT/UPDATE. executemany 래퍼."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.executemany(query, args_list)


async def execute_in_transaction(queries: list[tuple[str, tuple]]) -> None:
    """트랜잭션 내에서 여러 쿼리 실행."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            for query, args in queries:
                await conn.execute(query, *args)


async def check_connection() -> bool:
    """DB 연결 상태 확인."""
    try:
        result = await fetch_val("SELECT 1")
        return result == 1
    except Exception:
        return False


# search_log 멱등 DDL — init.sql과 동일. 기존 배포 DB도 startup에서 즉시 적재 가능하게.
SEARCH_LOG_DDL = """
CREATE TABLE IF NOT EXISTS search_log (
    id              BIGSERIAL PRIMARY KEY,
    ts              TIMESTAMPTZ NOT NULL DEFAULT now(),
    path            TEXT NOT NULL,
    tenant          TEXT,
    clearance       TEXT,
    route           TEXT,
    query_sha256    TEXT NOT NULL DEFAULT '',
    query_len       INTEGER NOT NULL DEFAULT 0,
    n_snippets      INTEGER NOT NULL DEFAULT 0,
    top_score       DOUBLE PRECISION,
    n_entities      INTEGER NOT NULL DEFAULT 0,
    graph_requested BOOLEAN NOT NULL DEFAULT false,
    n_graph_edges   INTEGER NOT NULL DEFAULT 0,
    no_answer       BOOLEAN NOT NULL DEFAULT false,
    llm_failed      BOOLEAN NOT NULL DEFAULT false,
    latency_ms      INTEGER NOT NULL DEFAULT 0,
    n_citations          INTEGER,
    unverified_citations INTEGER,
    prompt_tokens        INTEGER,
    completion_tokens    INTEGER,
    cost_usd             DOUBLE PRECISION
);
-- 기존 테이블(IF NOT EXISTS 로 안 바뀐)에도 컬럼을 더한다(멱등). migration 005·006 과 동일.
ALTER TABLE search_log ADD COLUMN IF NOT EXISTS n_citations          INTEGER;
ALTER TABLE search_log ADD COLUMN IF NOT EXISTS unverified_citations INTEGER;
ALTER TABLE search_log ADD COLUMN IF NOT EXISTS prompt_tokens        INTEGER;
ALTER TABLE search_log ADD COLUMN IF NOT EXISTS completion_tokens    INTEGER;
ALTER TABLE search_log ADD COLUMN IF NOT EXISTS cost_usd             DOUBLE PRECISION;
CREATE INDEX IF NOT EXISTS idx_search_log_ts     ON search_log (ts DESC);
CREATE INDEX IF NOT EXISTS idx_search_log_tenant ON search_log (tenant, ts DESC);
CREATE INDEX IF NOT EXISTS idx_search_log_route  ON search_log (route, ts DESC);
-- 뷰 컬럼 집합이 바뀌므로 CREATE OR REPLACE 대신 DROP+CREATE.
DROP VIEW IF EXISTS v_search_health;
CREATE VIEW v_search_health AS
SELECT path, route,
       count(*)                                                        AS n,
       avg((no_answer)::int)::numeric(4,3)                             AS no_answer_rate,
       avg((graph_requested AND n_graph_edges = 0)::int)::numeric(4,3) AS graph_empty_rate,
       avg((llm_failed)::int)::numeric(4,3)                            AS llm_fail_rate,
       avg(n_snippets)::numeric(6,2)                                   AS avg_snippets,
       percentile_disc(0.95) WITHIN GROUP (ORDER BY latency_ms)        AS p95_latency_ms,
       (SUM(unverified_citations)::numeric
          / NULLIF(SUM(n_citations), 0))::numeric(4,3)                 AS citation_fabrication_rate,
       avg(cost_usd)::numeric(12,6)                                    AS avg_cost_priced_usd,
       sum(cost_usd)::numeric(14,6)                                    AS total_cost_usd
FROM search_log
WHERE ts > now() - interval '7 days'
GROUP BY path, route;
"""


async def ensure_search_log() -> None:
    """search_log 테이블/인덱스/뷰를 멱등 생성. 풀 있을 때만, 실패는 삼킴(startup을 깨지 않음)."""
    if not has_pool():
        return
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute(SEARCH_LOG_DDL)  # 인자 없는 execute = simple protocol, 다중 구문 허용
    except Exception as exc:  # noqa: BLE001
        logger.warning("ensure_search_log_failed", error=str(exc))
