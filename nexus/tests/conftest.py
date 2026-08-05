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


def pytest_sessionstart(session) -> None:
    """스위트가 붙기 전에, 대상 DB 가 버려도 되는 DB 인지 확인한다.

    `clean_db` 와 여러 픽스처가 TRUNCATE 를 한다. NEXUS_TEST_DB_URL 을 개발 DB 로 두고 돌리면
    코퍼스가 사라지고 테스트는 초록으로 끝난다 — 실제로 그렇게 한 번 날렸다. URL 은 믿지 않는다
    (포트·DB 이름은 환경마다 다르고 CI 는 5432 를 쓴다). DB 안의 선언만 믿는다.
    """
    db_url = os.getenv("NEXUS_TEST_DB_URL")
    if not db_url:
        return

    import asyncio
    import sys

    from tests.disposable import NotDisposable, assert_disposable

    if sys.platform == "win32":                     # asyncpg 는 Proactor 루프에서 안 돈다
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    try:
        asyncio.run(assert_disposable(db_url))
    except NotDisposable as e:
        pytest.exit(f"\n거부: {e}\n", returncode=2)


@pytest.fixture(scope="session", autouse=True)
def _selector_event_loop_policy():
    """asyncpg 는 Windows 기본 ProactorEventLoop 에서 동작하지 않는다. Linux CI 는 무영향."""
    import asyncio
    import sys

    if sys.platform == "win32":
        prev = asyncio.get_event_loop_policy()
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        yield
        asyncio.set_event_loop_policy(prev)
    else:
        yield


def pytest_collection_modifyitems(config, items):
    """integration 마크가 붙은 테스트는 DB URL 없으면 자동 skip."""
    if os.getenv("NEXUS_TEST_DB_URL"):
        return
    skip = pytest.mark.skip(reason="NEXUS_TEST_DB_URL이 설정되지 않음 (docker-compose.test.yml 필요)")
    for item in items:
        if "integration" in item.keywords:
            item.add_marker(skip)


@pytest.fixture(scope="session")
def mcp_tools() -> dict:
    """등록된 MCP 도구를 이름으로 조회 — 공개 `list_tools()` 경유.

    예전엔 `mcp._tool_manager._tools` 를 직접 열었다. 사설 내부에 스위트를 묶어두면 상류가
    내부를 옮기는 순간 같이 깨진다 — mcp 2.0 이 `_mcp_server` 를 `_lowlevel_server` 로
    옮긴 게 정확히 그 예다. 공개 API 는 스키마를 `input_schema` 로 준다(2.0 에서 필드명이
    snake_case 로 통일됐다. 1.x 의 `inputSchema`/`.parameters` 가 아니다).
    """
    import asyncio

    from nexus.mcp.server import mcp

    return {t.name: t for t in asyncio.run(mcp.list_tools())}


@pytest.fixture(scope="session")
def db_url() -> str:
    return os.getenv("NEXUS_TEST_DB_URL", "postgresql://nexus:nexus@localhost:5433/nexus_test")


@pytest.fixture
async def db_pool(db_url: str):
    """asyncpg 연결 풀 (함수 스코프).

    세션 스코프였을 때 pytest-asyncio 의 함수 스코프 event_loop 와 충돌해
    `ScopeMismatch` 로 **setup 단계에서 죽었다** — 즉 이 fixture 를 쓰는 통합테스트는
    한 번도 실행된 적이 없다. 풀을 테스트마다 새로 열면(로컬 DB 라 값싸다) 루프 스코프가
    맞아떨어진다. 새 DB 테스트들이 각자 루프를 직접 돌리던 우회도 이제 필요 없다.
    """
    import asyncpg

    pool = await asyncpg.create_pool(db_url, min_size=1, max_size=5)
    try:
        yield pool
    finally:
        await pool.close()


@pytest.fixture(autouse=True)
async def clean_db(request):
    """integration 테스트 전 모든 테이블 TRUNCATE.

    db_pool 을 `getfixturevalue` 로 끌어오면 async fixture 가 이미 도는 루프 안에서 다시
    해석되어 "This event loop is already running" 으로 죽는다. 마커가 붙은 테스트에서만
    지연 요청하되, pytest-asyncio 가 아니라 우리가 직접 풀을 연다.
    """
    if "integration" not in [m.name for m in request.node.iter_markers()]:
        yield
        return

    import asyncpg
    pool = await asyncpg.create_pool(request.getfixturevalue("db_url"), min_size=1, max_size=3)
    async with pool.acquire() as conn:
        await conn.execute("""
            TRUNCATE evidence, edges, observed_edges, chunks, documents, entities, claims, search_log
            CASCADE
        """)
        # `ko_eval_embeddings` rows reference chunks that the TRUNCATE above just removed.
        # Leaving them behind produces an *orphaned* store: the rows survive, the chunks they
        # point at do not, and anything that folds chunks into documents silently reads nothing.
        # That happened on 2026-08-05 (SPEC-nexus-ko-eval-pool-sensitivity §5). Truncating the
        # store with the chunks keeps the two consistent, which is what this suite's
        # disposable-database discipline already assumes.
        # The table is created by the eval harness (`ko_eval_vector.ensure_table`), not by a
        # migration, so it is absent on a fresh database and TRUNCATE has no IF EXISTS.
        if os.getenv("NEXUS_PRESERVE_KO_EVAL_STORE") != "1":
            await conn.execute("""
                DO $$ BEGIN
                    IF to_regclass('public.ko_eval_embeddings') IS NOT NULL THEN
                        EXECUTE 'TRUNCATE ko_eval_embeddings';
                    END IF;
                END $$;
            """)
    await pool.close()

    yield
