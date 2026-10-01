"""예시 목록이 테넌트마다 심어 둔 엔티티를 **내리고**, 그 밖은 건드리지 않는다 — 진짜 Postgres 로.

migration 049 는 데이터를 바꾸는 마이그레이션이다. 고르는 기준이 틀리면 남의 엔티티를 내리거나(이름만으로
골랐을 때) 아무것도 못 내린다(설명이 어긋났을 때). 그래서 **라이브와 같은 경로로** 심는다 —
`ensure_entity_exists` 에 예시 파일을 그대로 먹여서. 2026-10-01 라이브에는 이렇게 심긴 행이 일곱 테넌트에
35개, 그 사이 간선이 1개 있었다.

지우지 않고 `soft_deleted` 로 내린다 — 목록을 다시 쓰면 같은 함수가 되살린다(둘째 검사).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from nexus.index import graph_extractor as gx
from nexus.rid import edge_rid, entity_rid

pytestmark = pytest.mark.integration

_NEXUS = Path(__file__).resolve().parents[1]
_MIGRATION = _NEXUS / "migrations" / "049_retire_the_sample_gazetteer.sql"
_EXAMPLE = _NEXUS / "entities.example.yaml"
_T = "gz_retire_test"
#: 같은 이름을 **자기 목록에** 둔 배포 — 설명이 다르다. 이것은 내려가면 안 된다.
_OWN = "gz_retire_own"


@pytest.fixture
async def seeded(db_pool):
    from nexus import db

    previous_pool = db._pool
    db._pool = db_pool

    async def clear():
        async with db_pool.acquire() as con:
            for t in (_T, _OWN):
                await con.execute("DELETE FROM edges WHERE tenant=$1", t)
                await con.execute("DELETE FROM entities WHERE tenant=$1", t)

    await clear()
    for ent in gx._load_gazetteer(str(_EXAMPLE)):
        await gx.ensure_entity_exists(_T, ent["name"], ent["type"],
                                      description=ent.get("description", ""),
                                      aliases=ent.get("aliases", []))
    await gx.ensure_entity_exists(_T, "ledger-service", "Service", description="장부")
    await gx.ensure_entity_exists(_OWN, "payment-service", "Service", description="우리 결제 서비스")
    frm = entity_rid(_T, "Service", "notification-service")
    to = entity_rid(_T, "Service", "payment-service")
    async with db_pool.acquire() as con:
        await con.execute(
            "INSERT INTO edges (rid, tenant, edge_type, from_rid, to_rid, confidence) "
            "VALUES ($1,$2,'CALLS',$3,$4,0.9)", edge_rid(_T, "CALLS", frm, to), _T, frm, to)
    yield db_pool
    await clear()
    db._pool = previous_pool


async def _statuses(pool) -> dict[tuple[str, str], str]:
    async with pool.acquire() as con:
        rows = await con.fetch(
            "SELECT tenant, name, status::text AS status FROM entities WHERE tenant = ANY($1)",
            [_T, _OWN])
    return {(r["tenant"], r["name"]): r["status"] for r in rows}


async def _migrate(pool) -> None:
    async with pool.acquire() as con:
        await con.execute(_MIGRATION.read_text(encoding="utf-8"))


async def test_the_seeded_sample_and_its_edge_are_retired_and_nothing_else(seeded):
    await _migrate(seeded)
    await _migrate(seeded)                      # 두 번 돌아도 같다 — 배포마다 한 번씩 돈다

    got = await _statuses(seeded)
    assert {name for (t, name), s in got.items() if t == _T and s == "soft_deleted"} == {
        "payment-service", "notification-service", "order-service",
        "payment.completed", "order.created"}
    assert got[(_T, "ledger-service")] == "active", "예시에 없는 엔티티를 내렸다"
    assert got[(_OWN, "payment-service")] == "active", "같은 이름의 남의 엔티티를 내렸다"
    async with seeded.acquire() as con:
        edge = await con.fetchval("SELECT status::text FROM edges WHERE tenant=$1", _T)
    assert edge == "soft_deleted", "내린 엔티티에 걸린 간선이 살아 있다"


async def test_listing_a_retired_entity_again_brings_it_back(seeded):
    """⛔ 되살리지 않으면 함정이 된다 — 예시를 복사해 다시 켠 배포에서 그래프가 조용히 빈다
    (`ON CONFLICT DO NOTHING` 이 내린 행을 그대로 둔다)."""
    await _migrate(seeded)
    await gx.ensure_entity_exists(_T, "order-service", "Service", description="주문 생성 및 관리")

    got = await _statuses(seeded)
    assert got[(_T, "order-service")] == "active"
    assert got[(_T, "payment-service")] == "soft_deleted", "다시 적지 않은 것까지 되살렸다"
