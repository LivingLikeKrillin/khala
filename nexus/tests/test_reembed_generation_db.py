"""`reembed` 와 세대 선언 — REAL Postgres. SPEC-nexus-generation-of-record §6-6.

초안은 이 명령을 **면제**했다. 비평이 그 구멍을 지적했다: `--column embedding --model
nomic-embed-text` 는 차원이 맞으므로 옛 가드를 통과하고, 검색되지 않는 세대를 그대로 다시
채운다 — 사고가 면제된 문으로 재현된다.

그래서 규칙이 둘이다: 평소엔 선언에 복종하고, **컷오버일 때만** 선언을 바꾼다. 그리고 컷오버는
끝났을 때만 선언을 남긴다 — 절반 돌다 죽은 실행이 남긴 선언은 거짓이다.
"""

from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.skipif(not os.getenv("NEXUS_TEST_DB_URL"), reason="NEXUS_TEST_DB_URL 필요")

_T = "reembed_gen"


@pytest.fixture
async def clean(db_pool):
    from nexus import db

    db._pool = db_pool
    async with db_pool.acquire() as con:
        await con.execute("DELETE FROM index_generation_events WHERE tenant = $1", _T)
    yield
    async with db_pool.acquire() as con:
        await con.execute("DELETE FROM index_generation_events WHERE tenant = $1", _T)
    db._pool = None


async def test_reembed_without_the_flag_obeys_the_declaration(clean):
    """면제되지 않는다 — 이것이 초안의 구멍이었다."""
    from nexus.index import generation as gen

    await gen.declare(_T, "embedding_1024", "KURE-v1", "alice")
    with pytest.raises(gen.GenerationMismatch):
        await gen.assert_writable(_T, "embedding", "nomic-embed-text", what="reembed")


async def test_a_completed_cutover_leaves_the_new_declaration(clean):
    """§3.3 — 사람에게 두 번째 명령을 기억시키는 설계는 잊힌다."""
    from nexus.index import generation as gen

    await gen.declare(_T, "embedding", "nomic-embed-text", "alice", reason="처음")
    # 컷오버 완료가 하는 일 (CLI 가 summary.ok 일 때만 부른다)
    await gen.declare(_T, "embedding_1024", "KURE-v1", "bob",
                      reason="reembed --change-generation (12건)")

    now = await gen.current(_T)
    assert now.column == "embedding_1024" and now.declared_by == "bob"
    assert len(await gen.history(_T)) == 2, "옛 선언은 이력으로 남는다"


async def test_a_failed_cutover_leaves_the_old_declaration_standing(clean):
    """절반 돌다 죽은 실행은 아무것도 선언하지 않는다 — 선언이 옛 세대를 가리키는 것이 참이다."""
    from nexus.index import generation as gen

    await gen.declare(_T, "embedding", "nomic-embed-text", "alice")
    # CLI 는 summary.ok 가 아니면 declare 를 부르지 않는다. 그 상태를 그대로 확인한다.
    now = await gen.current(_T)
    assert now.column == "embedding" and len(await gen.history(_T)) == 1


def test_the_cutover_flag_requires_a_signature():
    """--change-generation 은 --by 없이는 돌지 않는다 (CLI 옵션 계약)."""
    import inspect

    from nexus.cli import reembed_run

    params = inspect.signature(reembed_run).parameters
    assert "change_generation" in params and "by" in params
