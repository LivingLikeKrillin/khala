"""통합 테스트 공통 fixture.

docker-compose.test.yml의 PostgreSQL에 연결한다.
KHALA_TEST_DB_URL 환경변수가 설정되어 있을 때만 통합 테스트가 실행된다.
"""

from __future__ import annotations

import os

import pytest


def pytest_collection_modifyitems(config, items):
    """integration 마크가 붙은 테스트는 DB URL 없으면 자동 skip."""
    if os.getenv("KHALA_TEST_DB_URL"):
        return
    skip = pytest.mark.skip(reason="KHALA_TEST_DB_URL이 설정되지 않음 (docker-compose.test.yml 필요)")
    for item in items:
        if "integration" in item.keywords:
            item.add_marker(skip)


@pytest.fixture(scope="session")
def db_url() -> str:
    return os.getenv("KHALA_TEST_DB_URL", "postgresql://khala:khala@localhost:5433/khala_test")


@pytest.fixture(scope="session")
async def db_pool(db_url: str):
    """세션 스코프 asyncpg 연결 풀. integration 테스트에서만 사용."""
    import asyncpg

    pool = await asyncpg.create_pool(db_url, min_size=2, max_size=5)
    yield pool
    await pool.close()


@pytest.fixture(autouse=True)
async def clean_db(request):
    """integration 테스트 전 모든 테이블 TRUNCATE."""
    if "integration" not in [m.name for m in request.node.iter_markers()]:
        yield
        return

    pool = request.getfixturevalue("db_pool")
    async with pool.acquire() as conn:
        await conn.execute("""
            TRUNCATE evidence, edges, observed_edges, chunks, documents, entities
            CASCADE
        """)

    yield
