"""통합 테스트 공통 fixture.

docker-compose.test.yml의 PostgreSQL에 연결한다.
NEXUS_TEST_DB_URL 환경변수가 설정되어 있을 때만 통합 테스트가 실행된다.
"""

from __future__ import annotations

import importlib.util
import os
import pathlib
import re

import pytest

# A2A tests import the optional `a2a-sdk` (pyproject `[a2a]` extra, off by default —
# only `nexus/a2a/` imports it, flag-gated). When the SDK isn't installed (e.g. CI
# installs only `[dev,mcp]`), skip COLLECTING any test module that imports a2a
# (directly or via `nexus.a2a`) instead of erroring at import time. Content-scanned
# rather than name-matched, so new a2a-touching tests are covered automatically.
# With the extra installed locally, every such test runs unchanged.
collect_ignore: list[str] = []
if importlib.util.find_spec("a2a") is None:
    _A2A_IMPORT = re.compile(
        r"^\s*(?:import\s+a2a|from\s+a2a|import\s+nexus\.a2a|"
        r"from\s+nexus\.a2a|from\s+nexus\s+import\s+a2a)\b",
        re.MULTILINE,
    )
    for _f in pathlib.Path(__file__).parent.glob("test_*.py"):
        if _A2A_IMPORT.search(_f.read_text(encoding="utf-8")):
            collect_ignore.append(_f.name)


def pytest_collection_modifyitems(config, items):
    """integration 마크가 붙은 테스트는 DB URL 없으면 자동 skip."""
    if os.getenv("NEXUS_TEST_DB_URL"):
        return
    skip = pytest.mark.skip(reason="NEXUS_TEST_DB_URL이 설정되지 않음 (docker-compose.test.yml 필요)")
    for item in items:
        if "integration" in item.keywords:
            item.add_marker(skip)


@pytest.fixture(scope="session")
def db_url() -> str:
    return os.getenv("NEXUS_TEST_DB_URL", "postgresql://nexus:nexus@localhost:5433/nexus_test")


@pytest.fixture(scope="session")
async def db_pool(db_url: str):
    """세션 스코프 asyncpg 연결 풀. integration 테스트에서만 사용.

    NOTE(2026-06-06): 이 환경(Windows + pytest-asyncio)에서 async-generator fixture가
    `run_until_complete` 재진입으로 깨진다("This event loop is already running"). 따라서
    이 fixture에 의존하는 통합테스트는 현재 동작하지 않는다. Archon 통합테스트는
    pytest-asyncio를 우회해 자체 asyncio 루프를 쓴다(tests/test_claim_integration.py 참고).
    """
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
            TRUNCATE evidence, edges, observed_edges, chunks, documents, entities, claims, search_log
            CASCADE
        """)

    yield
