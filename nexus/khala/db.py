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


async def get_pool() -> asyncpg.Pool:
    """Connection pool 획득. 없으면 생성."""
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(
            dsn=os.getenv("DATABASE_URL", "postgresql://khala:khala@localhost:5432/khala"),
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
