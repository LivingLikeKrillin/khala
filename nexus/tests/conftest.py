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
        # `ko_eval_embeddings` rows reference the chunks the TRUNCATE above just removed, so
        # after this fixture the store is *orphaned*. It is left alone anyway, and the default
        # is deliberately the opposite of what SPEC-nexus-ko-eval-pool-sensitivity §5.3
        # specifies. Two facts, both learned after that SPEC was stamped, invert the trade:
        #
        #   1. the orphan is already caught where it matters - `ko_eval_vector.verify_arm`
        #      refuses rows whose chunks no longer exist, and `cmd_run` stops there; the
        #      remaining exposure was code that folds chunks without that check, which
        #      `ko_eval_harness` now guards directly;
        #   2. truncating costs hours. The store holds two arms over 1906 chunks, and KURE-v1
        #      is a CPU sentence-transformers pass. On 2026-08-05 it was destroyed exactly this
        #      way while verifying this fixture.
        #
        # So destruction is opt-in. `restore-chunks` repairs an orphaned store without
        # rebuilding it. The table is created by the harness rather than by a migration, so it
        # is absent on a fresh database and TRUNCATE has no IF EXISTS.
        if os.getenv("NEXUS_TRUNCATE_KO_EVAL_STORE") == "1":
            await conn.execute("""
                DO $$ BEGIN
                    IF to_regclass('public.ko_eval_embeddings') IS NOT NULL THEN
                        EXECUTE 'TRUNCATE ko_eval_embeddings';
                    END IF;
                END $$;
            """)
    await pool.close()

    yield


@pytest.fixture(autouse=True)
def _no_accidental_dev_db(monkeypatch):
    """주입 없이 **개발 DB** 에 붙는 것을 막는다.

    `nexus.db.get_pool()` 의 DSN 기본값은 `localhost:5432/nexus` — 이 기계의 실제 코퍼스다.
    DB 를 쓰는 시험은 전부 픽스처가 `db._pool` 을 주입하고 들어오므로, 주입 없이 풀을 열려는
    것은 언제나 사고다: 단위 시험이 조용히 개발 DB 에 붙어 초록으로 끝난다(2026-08-11 에
    실제로 그랬고, 그때 나간 것은 아무 행도 안 맞는 UPDATE 였지만 다음 번에도 그러리라는
    보장은 없다 — 이 리포는 이미 스위트에 코퍼스를 한 번 날렸다).

    `DATABASE_URL` 이 명시된 곳(CI, 그리고 자기 URL 을 직접 세우는 DB 시험)은 막지 않는다.
    그쪽은 버려도 되는 DB 이고, 막으면 DB 를 실제로 쓰는 잡이 죽는다. 막는 것은 **기본값으로
    흘러가는 경로** 하나다.

    판정은 **부를 때** 한다. 픽스처 시점에 보면, 본문에서 `DATABASE_URL` 을 세우고 붙는 시험이
    전부 막힌다 — 실제로 그렇게 6건이 죽었다.
    """
    from nexus import db

    real = db.get_pool

    async def _guarded():
        if db._pool is None and not os.getenv("DATABASE_URL"):
            raise RuntimeError(
                "이 시험이 풀 주입 없이 DB 에 붙으려 했다. 기본 DSN 은 개발 DB 다 — "
                "DB 가 필요하면 픽스처로 db._pool 을 주입하고, 아니면 그 경로를 스텁하라.")
        return await real()

    monkeypatch.setattr(db, "get_pool", _guarded)
    yield
