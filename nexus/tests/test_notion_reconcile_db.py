"""soft_delete/revive 프리미티브 + containment scope 조회를 REAL Postgres 로 검증한다.

SPEC-nexus-notion-reconciliation §3.2(containment) · §3.4(primitives).

핵심 불변식 둘:
  1. revive 는 **현재 세대 청크만** 되살린다 (낡은 superseded 세대는 죽은 채로).
  2. superseded 문서는 prune 도 revive 도 되지 않는다.

NOTE(Windows + pytest-asyncio): test_supersede_db.py 와 동일하게 자체 SelectorEventLoop +
asyncpg 풀을 돌리고 db._pool 에 주입한다.
"""

from __future__ import annotations

import asyncio
import os
import sys

import pytest

from nexus.rid import chunk_rid

DB_URL = os.getenv("NEXUS_TEST_DB_URL")
pytestmark = pytest.mark.skipif(not DB_URL, reason="NEXUS_TEST_DB_URL 필요 (docker-compose.test.yml)")

_TENANT = "acme"

# 문서들 — rid 는 sink 매핑을 그대로 쓴다.
from nexus.ingest.sources.notion_reconcile import notion_doc_rid  # noqa: E402

_RID_A = notion_doc_rid(_TENANT, "pageA")   # active, prov_inputs={rootA}
_RID_SHARED = notion_doc_rid(_TENANT, "pageS")  # active, prov_inputs={rootA,rootB}
_RID_DEL = notion_doc_rid(_TENANT, "pageD")     # soft_deleted, prov_inputs={rootA}
_RID_SUP = notion_doc_rid(_TENANT, "pageN")     # superseded,   prov_inputs={rootA}
_RID_BARE = notion_doc_rid(_TENANT, "pageB")    # active, prov_inputs={} (백필 전 레거시)
_RID_GIT = "doc_gitgitgitgi"                    # notion 아님
_RID_QUAR = notion_doc_rid(_TENANT, "pageQ")    # quarantined — provenance 를 쓰면 안 된다

# pageA 의 청크: 현재 세대(hash=chash-a2) + 낡은 세대(hash=chash-a1, 이미 superseded)
_CHUNK_A_CUR = chunk_rid(_RID_A, "", 0)
_CHUNK_A_OLD = chunk_rid(_RID_A, "", 1)
# pageD(soft_deleted) 의 청크: 현재 세대 + 낡은 세대
_CHUNK_D_CUR = chunk_rid(_RID_DEL, "", 0)
_CHUNK_D_OLD = chunk_rid(_RID_DEL, "", 1)


async def _seed(conn) -> None:
    async def doc(rid, uri, status, prov, chash, quarantined=False):
        await conn.execute(
            "INSERT INTO documents (rid, tenant, source_uri, hash, content_hash, status, prov_inputs, is_quarantined) "
            "VALUES ($1, $2, $3, $4, $5, $6::resource_status, $7, $8)",
            rid, _TENANT, uri, chash, chash, status, prov, quarantined,
        )

    await doc(_RID_A, f"{_TENANT}:ext-notion-pageA.md", "active", ["rootA"], "chash-a2")
    await doc(_RID_SHARED, f"{_TENANT}:ext-notion-pageS.md", "active", ["rootA", "rootB"], "chash-s")
    await doc(_RID_DEL, f"{_TENANT}:ext-notion-pageD.md", "soft_deleted", ["rootA"], "chash-d2")
    await doc(_RID_SUP, f"{_TENANT}:ext-notion-pageN.md", "superseded", ["rootA"], "chash-n")
    await doc(_RID_BARE, f"{_TENANT}:ext-notion-pageB.md", "active", [], "chash-b")
    await doc(_RID_GIT, f"{_TENANT}:specs/x.md", "active", ["rootA"], "chash-g")
    await doc(_RID_QUAR, f"{_TENANT}:ext-notion-pageQ.md", "active", [], "chash-q", quarantined=True)

    async def chunk(rid, doc_rid_, status, chash, text):
        await conn.execute(
            "INSERT INTO chunks (rid, tenant, source_uri, doc_rid, chunk_text, status, hash, chunk_index) "
            "VALUES ($1, $2, $3, $4, $5, $6::resource_status, $7, $8)",
            rid, _TENANT, "u", doc_rid_, text, status, chash, 0,
        )

    # pageA: 현재 세대 active + 낡은 세대 superseded
    await chunk(_CHUNK_A_CUR, _RID_A, "active", "chash-a2", "현재 본문")
    await chunk(_CHUNK_A_OLD, _RID_A, "superseded", "chash-a1", "낡은 본문")
    # pageD(soft_deleted): 현재 세대는 superseded 로 기록돼 있다(파이프라인이 non-active 부모의
    # 청크를 superseded 로 쓴다) + 진짜 낡은 세대도 superseded
    await chunk(_CHUNK_D_CUR, _RID_DEL, "superseded", "chash-d2", "현재 본문 D")
    await chunk(_CHUNK_D_OLD, _RID_DEL, "superseded", "chash-d1", "낡은 본문 D")


def _run(coro_fn):
    from nexus import db

    loop = asyncio.SelectorEventLoop() if sys.platform == "win32" else asyncio.new_event_loop()

    async def _outer():
        import asyncpg
        pool = await asyncpg.create_pool(DB_URL, min_size=1, max_size=3)
        db._pool = pool
        try:
            async with pool.acquire() as con:
                await con.execute("TRUNCATE documents, chunks CASCADE")
                await _seed(con)
            return await coro_fn()
        finally:
            await pool.close()
            db._pool = None

    try:
        return loop.run_until_complete(_outer())
    finally:
        loop.close()


# ── §3.2 containment scope ────────────────────────────────────────────────────

def test_scope_excludes_docs_whose_roots_are_not_all_walked():
    from nexus.ingest.sources.notion_reconcile import fetch_notion_scope

    async def inner():
        # rootA 만 걸었다 → prov_inputs={rootA,rootB} 인 shared 는 범위 밖이어야 한다.
        rows = await fetch_notion_scope(_TENANT, {"rootA"})
        rids = {r.rid for r in rows}
        assert _RID_A in rids
        assert _RID_SHARED not in rids          # {rootA,rootB} ⊄ {rootA}
        assert _RID_BARE not in rids            # prov_inputs 비어있음 → 절대 prune 후보 아님
        assert _RID_GIT not in rids             # notion 문서 아님

        # 두 root 를 모두 걸면 shared 도 범위에 든다.
        rows2 = await fetch_notion_scope(_TENANT, {"rootA", "rootB"})
        assert _RID_SHARED in {r.rid for r in rows2}

    _run(inner)


def test_scope_includes_soft_deleted_and_superseded_rows():
    """revive 후보를 찾으려면 soft_deleted 도 범위에 들어와야 한다 (판정은 plan_reconcile 이 한다)."""
    from nexus.ingest.sources.notion_reconcile import fetch_notion_scope

    async def inner():
        rows = await fetch_notion_scope(_TENANT, {"rootA"})
        by_rid = {r.rid: r.status for r in rows}
        assert by_rid[_RID_DEL] == "soft_deleted"
        assert by_rid[_RID_SUP] == "superseded"

    _run(inner)


def test_scope_is_tenant_scoped():
    from nexus.ingest.sources.notion_reconcile import fetch_notion_scope

    async def inner():
        assert await fetch_notion_scope("other-tenant", {"rootA"}) == []

    _run(inner)


# ── §3.4 soft_delete ──────────────────────────────────────────────────────────

def test_soft_delete_hides_doc_and_its_active_chunks_only():
    from nexus import db
    from nexus.lifecycle import soft_delete

    async def inner():
        assert await soft_delete(_RID_A, _TENANT) == "soft_deleted"

        doc = await db.fetch_one("SELECT status FROM documents WHERE rid=$1", _RID_A)
        assert doc["status"] == "soft_deleted"

        cur = await db.fetch_one("SELECT status FROM chunks WHERE rid=$1", _CHUNK_A_CUR)
        old = await db.fetch_one("SELECT status FROM chunks WHERE rid=$1", _CHUNK_A_OLD)
        assert cur["status"] == "soft_deleted"
        assert old["status"] == "superseded"   # 낡은 세대는 건드리지 않는다

    _run(inner)


def test_soft_delete_is_idempotent():
    from nexus.lifecycle import soft_delete

    async def inner():
        assert await soft_delete(_RID_A, _TENANT) == "soft_deleted"
        assert await soft_delete(_RID_A, _TENANT) == "noop"

    _run(inner)


def test_soft_delete_refuses_superseded_doc():
    from nexus import db
    from nexus.lifecycle import soft_delete

    async def inner():
        assert await soft_delete(_RID_SUP, _TENANT) == "noop"
        row = await db.fetch_one("SELECT status FROM documents WHERE rid=$1", _RID_SUP)
        assert row["status"] == "superseded"   # 상태 불변

    _run(inner)


# ── §3.4 revive ───────────────────────────────────────────────────────────────

def test_revive_restores_only_the_current_chunk_generation():
    """되살릴 때 낡은 세대 청크가 함께 부활하면 '죽은 텍스트'가 검색에 돌아온다."""
    from nexus import db
    from nexus.lifecycle import revive

    async def inner():
        assert await revive(_RID_DEL, _TENANT) == "revived"

        doc = await db.fetch_one("SELECT status FROM documents WHERE rid=$1", _RID_DEL)
        assert doc["status"] == "active"

        cur = await db.fetch_one("SELECT status FROM chunks WHERE rid=$1", _CHUNK_D_CUR)
        old = await db.fetch_one("SELECT status FROM chunks WHERE rid=$1", _CHUNK_D_OLD)
        assert cur["status"] == "active"        # hash == documents.content_hash
        assert old["status"] == "superseded"    # 낡은 세대는 죽은 채로

    _run(inner)


def test_revive_is_idempotent():
    from nexus.lifecycle import revive

    async def inner():
        assert await revive(_RID_DEL, _TENANT) == "revived"
        assert await revive(_RID_DEL, _TENANT) == "noop"

    _run(inner)


def test_revive_never_resurrects_a_superseded_doc():
    from nexus import db
    from nexus.lifecycle import revive

    async def inner():
        assert await revive(_RID_SUP, _TENANT) == "noop"
        row = await db.fetch_one("SELECT status FROM documents WHERE rid=$1", _RID_SUP)
        assert row["status"] == "superseded"

    _run(inner)


# ── §3.1 prov_inputs 기록 (백필의 실질) ────────────────────────────────────────

def test_write_source_roots_refreshes_only_the_walked_roots():
    """이번에 걸은 root 에 대해서만 귀속을 갱신하고, 걷지 않은 root 의 기록은 보존한다.

    I-010 회귀 가드. 통째로 덮어쓰면 rootB 를 걷지 않은 실행이 'P 는 B 에도 걸려 있다'는
    사실을 지워버리고, 다음 실행에서 P 가 B 밑에 살아있는데도 prune 후보가 된다.
    """
    from nexus import db
    from nexus.ingest.sources.notion_reconcile import write_source_roots

    async def inner():
        # _RID_SHARED 는 {rootA, rootB}. rootA 만 걷고, 이번에도 rootA 에서 닿았다.
        await write_source_roots(_RID_SHARED, _TENANT, reached=["rootA"], walked=["rootA"])
        row = await db.fetch_one("SELECT prov_inputs FROM documents WHERE rid=$1", _RID_SHARED)
        assert sorted(row["prov_inputs"]) == ["rootA", "rootB"]  # rootB 보존

    _run(inner)


def test_write_source_roots_drops_a_walked_root_that_no_longer_reaches_the_page():
    """rootA·rootB 를 모두 걸었는데 이번엔 rootA 에서만 닿았다면 rootB 귀속은 사라져야 한다."""
    from nexus import db
    from nexus.ingest.sources.notion_reconcile import write_source_roots

    async def inner():
        await write_source_roots(_RID_SHARED, _TENANT, reached=["rootA"], walked=["rootA", "rootB"])
        row = await db.fetch_one("SELECT prov_inputs FROM documents WHERE rid=$1", _RID_SHARED)
        assert row["prov_inputs"] == ["rootA"]

    _run(inner)


def test_subset_run_cannot_make_a_multi_root_page_prunable():
    """I-010 의 실제 피해 시나리오를 끝까지 재현한다.

    rootA 만 걷는 실행을 두 번 한다. 1회차에 P 는 rootA 에서 닿았고, 2회차엔 rootA 에서
    사라졌다(하지만 rootB 밑에는 여전히 살아있다). P 가 prune 후보가 되면 안 된다.
    """
    from nexus.ingest.sources.notion_reconcile import (
        fetch_notion_scope,
        plan_reconcile,
        write_source_roots,
    )

    async def inner():
        # 1회차: rootA 만 걷고 P(shared) 에 닿음
        await write_source_roots(_RID_SHARED, _TENANT, reached=["rootA"], walked=["rootA"])
        # 2회차: rootA 만 걷고 P 는 더 이상 rootA 밑에 없다 → live 에서 빠짐
        scope = await fetch_notion_scope(_TENANT, {"rootA"})
        plan = plan_reconcile(scope, live_rids={_RID_A}, force=True)
        assert _RID_SHARED not in plan.prune  # rootB 를 안 걸었으므로 판정 불가 → 건드리지 않음

    _run(inner)


def test_write_source_roots_backfills_a_legacy_row():
    """SPEC 이전에 적재된 행(prov_inputs={})은 첫 전체 실행에서 귀속된다 — 마이그레이션 불필요."""
    from nexus import db
    from nexus.ingest.sources.notion_reconcile import fetch_notion_scope, write_source_roots

    async def inner():
        assert _RID_BARE not in {r.rid for r in await fetch_notion_scope(_TENANT, {"rootA"})}
        await write_source_roots(_RID_BARE, _TENANT, reached=["rootA"], walked=["rootA"])
        row = await db.fetch_one("SELECT prov_inputs FROM documents WHERE rid=$1", _RID_BARE)
        assert row["prov_inputs"] == ["rootA"]
        assert _RID_BARE in {r.rid for r in await fetch_notion_scope(_TENANT, {"rootA"})}

    _run(inner)


def test_write_source_roots_never_touches_a_quarantined_row():
    from nexus import db
    from nexus.ingest.sources.notion_reconcile import write_source_roots

    async def inner():
        await write_source_roots(_RID_QUAR, _TENANT, reached=["rootA"], walked=["rootA"])
        row = await db.fetch_one("SELECT prov_inputs FROM documents WHERE rid=$1", _RID_QUAR)
        assert row["prov_inputs"] == []

    _run(inner)


# ── 프로덕션 재조정 함수 (계획 → 적용) ─────────────────────────────────────────

def test_reconcile_fn_applies_prune_and_revive():
    from nexus import db
    from nexus.ingest.sources.notion_reconcile import make_reconcile_fn

    async def inner():
        # rootA scope: A(active), DEL(soft_deleted), SUP(superseded)
        # live = {A, DEL} → prune 없음, revive=[DEL]
        fn = make_reconcile_fn()
        out = await fn(_TENANT, {"rootA"}, {_RID_A, _RID_DEL})
        assert out.pruned == 0
        assert out.revived == 1
        assert out.refused is False

        assert (await db.fetch_one("SELECT status FROM documents WHERE rid=$1", _RID_DEL))["status"] == "active"
        assert (await db.fetch_one("SELECT status FROM documents WHERE rid=$1", _RID_SUP))["status"] == "superseded"

    _run(inner)


def test_reconcile_fn_refuses_over_threshold_and_applies_nothing():
    from nexus import db
    from nexus.ingest.sources.notion_reconcile import make_reconcile_fn

    async def inner():
        fn = make_reconcile_fn()
        out = await fn(_TENANT, {"rootA"}, set())  # A 가 사라진 것처럼 → 1/1 = 100%
        assert out.refused is True
        assert out.pruned == 0                     # 적용 안 함
        assert (await db.fetch_one("SELECT status FROM documents WHERE rid=$1", _RID_A))["status"] == "active"

    _run(inner)


def test_reconcile_fn_dry_run_mutates_nothing():
    from nexus import db
    from nexus.ingest.sources.notion_reconcile import make_reconcile_fn

    async def inner():
        fn = make_reconcile_fn(dry_run=True, force=True)
        out = await fn(_TENANT, {"rootA"}, {_RID_DEL})  # A prune 대상, DEL revive 대상
        assert out.pruned == 1 and out.revived == 1     # 계획은 보고
        # 그러나 DB 는 불변
        assert (await db.fetch_one("SELECT status FROM documents WHERE rid=$1", _RID_A))["status"] == "active"
        assert (await db.fetch_one("SELECT status FROM documents WHERE rid=$1", _RID_DEL))["status"] == "soft_deleted"

    _run(inner)


def test_reconcile_fn_force_applies_over_threshold():
    from nexus import db
    from nexus.ingest.sources.notion_reconcile import make_reconcile_fn

    async def inner():
        fn = make_reconcile_fn(force=True)
        out = await fn(_TENANT, {"rootA"}, set())
        assert out.refused is False and out.pruned == 1
        assert (await db.fetch_one("SELECT status FROM documents WHERE rid=$1", _RID_A))["status"] == "soft_deleted"

    _run(inner)
