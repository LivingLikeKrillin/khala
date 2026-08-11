"""세대 선언 — REAL Postgres. SPEC-nexus-generation-of-record §6-1·2·5.

선언은 **코퍼스의 사실**이고 프로세스의 설정이 아니다. 그래서 DB 에 있고, append-only 이고,
쓰기 전에 검증된다.
"""

from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.skipif(not os.getenv("NEXUS_TEST_DB_URL"), reason="NEXUS_TEST_DB_URL 필요")

_T = "gen_test"


@pytest.fixture
async def clean(db_pool):
    from nexus import db

    db._pool = db_pool
    async with db_pool.acquire() as con:
        await con.execute("DELETE FROM index_generation_events WHERE tenant LIKE 'gen\\_%'")
    yield
    async with db_pool.acquire() as con:
        await con.execute("DELETE FROM index_generation_events WHERE tenant LIKE 'gen\\_%'")
    db._pool = None


async def test_declaring_appends_and_current_is_the_latest(clean):
    """§6-1 — 컷오버는 덮어쓰기가 아니다. 언제 바뀌었는지가 이번 사고를 푼 증거였다."""
    from nexus.index import generation as gen

    await gen.declare(_T, "embedding", "nomic-embed-text", "alice", reason="처음")
    await gen.declare(_T, "embedding_1024", "KURE-v1", "bob", reason="컷오버")

    now = await gen.current(_T)
    assert now.column == "embedding_1024" and now.model == "KURE-v1"
    assert now.declared_by == "bob"

    hist = await gen.history(_T)
    assert [h.column for h in hist] == ["embedding_1024", "embedding"], "최신 순, 옛 선언 보존"


async def test_an_undeclared_tenant_is_none_not_a_default(clean):
    """선언 없음은 기본값이 아니다 — 아무도 결정하지 않은 상태다."""
    from nexus.index import generation as gen

    assert await gen.current("gen_never_declared") is None


@pytest.mark.parametrize("column,model,why", [
    ("embedding_9999", "KURE-v1", "레지스트리에 없는 컬럼"),
    ("embedding_1024", "made-up-model", "차원을 모르는 모델"),
    ("embedding_1024", "nomic-embed-text", "768 모델을 1024 컬럼에"),
    ("embedding", "KURE-v1", "1024 모델을 768 컬럼에"),
])
async def test_an_impossible_declaration_is_refused_before_it_is_written(clean, column, model, why):
    """§6-2 — 오타를 받아 두면 존재하지 않는 컬럼을 대며 모든 적재를 영원히 거부하게 된다."""
    from nexus.index import generation as gen

    with pytest.raises(gen.InvalidDeclaration):
        await gen.declare(_T, column, model, "alice")
    assert await gen.current(_T) is None, f"{why}: 거부됐으면 아무것도 안 남아야 한다"


async def test_a_declaration_without_an_author_is_refused(clean):
    from nexus.index import generation as gen

    with pytest.raises(gen.InvalidDeclaration):
        await gen.declare(_T, "embedding_1024", "KURE-v1", "   ")


async def test_assert_writable_stops_the_2026_08_10_accident(clean):
    """호스트가 해석한 768 세대로 1024 코퍼스에 쓰려 하면 멈춘다."""
    from nexus.index import generation as gen

    await gen.declare(_T, "embedding_1024", "KURE-v1", "alice")

    ok = await gen.assert_writable(_T, "embedding_1024", "KURE-v1", what="ingest")
    assert ok is not None

    with pytest.raises(gen.GenerationMismatch) as e:
        await gen.assert_writable(_T, "embedding", "nomic-embed-text", what="ingest")
    msg = str(e.value)
    assert "embedding_1024" in msg and "nomic-embed-text" in msg, "양쪽을 다 말해야 한다"
    assert "--change-generation" in msg, "고치는 명령을 이름으로 대야 한다"


async def test_an_undeclared_tenant_is_allowed_through(clean):
    """§3.2 — 업그레이드가 배포를 멈추면 안 된다. 결정한 적 없는 테넌트는 위반할 결정이 없다."""
    from nexus.index import generation as gen

    assert await gen.assert_writable("gen_never_declared", "embedding", "nomic-embed-text",
                                     what="ingest") is None


async def test_a_declared_and_an_undeclared_tenant_coexist(clean):
    """§6-5 — 스코핑 버그는 언제나 섞인 경우에 산다."""
    from nexus.index import generation as gen

    await gen.declare(_T, "embedding_1024", "KURE-v1", "alice")
    assert await gen.current("gen_other") is None
    with pytest.raises(gen.GenerationMismatch):
        await gen.assert_writable(_T, "embedding", "nomic-embed-text", what="ingest")
    assert await gen.assert_writable("gen_other", "embedding", "nomic-embed-text",
                                     what="ingest") is None
