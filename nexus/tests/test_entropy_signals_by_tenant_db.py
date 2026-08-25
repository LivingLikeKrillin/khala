"""DB-backed tests for 마이그레이션 034 — 테넌트별 엔트로피 신호 + `identityless_chunks`.

**무엇을 지키는 검사인가.** 이 뷰는 하중을 받는다: ADR-0006 이 그것을 Slice-2 의 demand-pull
방아쇠로 지정했고, 여러 SPEC 처분이 *"gated on v_entropy_signals"* 로 보류돼 있다. 그런데
전역 집계라 버릴 평가 테넌트가 신호를 삼켰다(2026-08-25 라이브: 전역 정확중복 61,425 vs
`default` 0).

그래서 이 파일의 중심은 **대조군**이다: 테넌트를 가로지르는 중복쌍을 일부러 심고, 그것이
**세어지지 않는 것**을 단언한다. 옛 뷰에서는 이 검사가 실패한다 — 그물을 일부러 깨뜨려
확인하는 자리다.

Own SelectorEventLoop + injected asyncpg pool (see test_entropy_signals_cli_db.py).
"""

from __future__ import annotations

import asyncio
import os
import sys

import pytest

DB_URL = os.getenv("NEXUS_TEST_DB_URL")
pytestmark = pytest.mark.skipif(not DB_URL, reason="NEXUS_TEST_DB_URL 필요 (docker-compose.test.yml)")

_A = "tenant_a"
_B = "tenant_b"


def _run(coro_fn):
    from nexus import db

    loop = asyncio.SelectorEventLoop() if sys.platform == "win32" else asyncio.new_event_loop()

    async def _outer():
        import asyncpg
        pool = await asyncpg.create_pool(DB_URL, min_size=1, max_size=3)
        db._pool = pool
        try:
            async with pool.acquire() as con:
                await con.execute("TRUNCATE documents, chunks, doc_reingest_events CASCADE")
            return await coro_fn()
        finally:
            await pool.close()
            db._pool = None

    try:
        return loop.run_until_complete(_outer())
    finally:
        loop.close()


async def _doc(rid: str, tenant: str, title: str, *, content_hash: str = "",
               status: str = "active") -> None:
    from nexus import db

    await db.execute(
        "INSERT INTO documents (rid, tenant, source_uri, hash, title, status, content_hash) "
        "VALUES ($1, $2, $3, 'h', $4, $5::resource_status, $6)",
        rid, tenant, f"seed:{rid}.md", title, status, content_hash,
    )


async def _chunk(rid: str, doc_rid: str, tenant: str, text: str, *,
                 section_path: str = "root", context_prefix: str | None = None) -> None:
    from nexus import db

    await db.execute(
        "INSERT INTO chunks (rid, tenant, source_uri, doc_rid, section_path, chunk_text, "
        "context_prefix) VALUES ($1, $2, $3, $4, $5, $6, $7)",
        rid, tenant, f"seed:{doc_rid}.md", doc_rid, section_path, text, context_prefix,
    )


async def _by_tenant() -> dict[str, dict]:
    from nexus import db

    rows = await db.fetch_all("SELECT * FROM v_entropy_signals_by_tenant")
    return {r["tenant"]: dict(r) for r in rows}


# ── 대조군: 테넌트를 가로지르는 중복은 공존이 아니다 ────────────────────────────────

def test_cross_tenant_duplicate_is_not_counted():
    """같은 content_hash 라도 **다른 테넌트**면 중복쌍이 아니다.

    테넌트는 격리 경계다 — 검색이 둘을 같이 보는 일이 없으므로 어느 답변에서도 충돌하지
    않는다. 옛 전역 뷰는 이 쌍을 셌고, 그래서 평가 코퍼스 사본이 라이브 신호를 삼켰다.
    """
    async def inner():
        await _doc("doc_x_a", _A, "결제 스펙", content_hash="ch-shared")
        await _doc("doc_x_b", _B, "결제 스펙", content_hash="ch-shared")
        sig = await _by_tenant()
        assert sig[_A]["exact_dup_pairs"] == 0
        assert sig[_B]["exact_dup_pairs"] == 0

    _run(inner)


def test_same_tenant_duplicate_is_counted():
    """같은 테넌트 안의 같은 해시 두 문서는 여전히 센다 — 고친 것은 경계뿐이다."""
    async def inner():
        await _doc("doc_d1", _A, "결제 스펙 사본 1", content_hash="ch-dup")
        await _doc("doc_d2", _A, "결제 스펙 사본 2", content_hash="ch-dup")
        await _doc("doc_other", _B, "무관 문서", content_hash="ch-other")
        sig = await _by_tenant()
        assert sig[_A]["exact_dup_pairs"] == 1
        assert sig[_B]["exact_dup_pairs"] == 0

    _run(inner)


def test_title_collision_stays_in_its_own_tenant():
    """제목 충돌도 테넌트 안에서만 센다."""
    async def inner():
        await _doc("doc_t1", _A, "개정 이력 동기화", content_hash="ch1")
        await _doc("doc_t2", _A, "개정 이력 동기화", content_hash="ch2")
        await _doc("doc_t3", _B, "개정 이력 동기화", content_hash="ch3")
        sig = await _by_tenant()
        assert sig[_A]["title_stem_collisions"] == 1     # 한 그룹
        assert sig[_B]["title_stem_collisions"] == 0     # 혼자면 충돌이 아니다

    _run(inner)


# ── 새 신호: 색인 텍스트에 신원이 없는 청크 ─────────────────────────────────────

def test_identityless_chunk_counted_and_the_three_ways_out():
    """`search_text` 에 문서 신원이 하나도 안 들어가는 청크만 센다.

    `search_text = COALESCE(context_prefix, '[' || section_path || ']') || ' ' || chunk_text`
    이므로 빠져나가는 길은 셋이다: 접두사가 있거나 · 섹션이 `root` 가 아니거나 · 본문이 제목을
    품거나. 셋 다 각각 확인한다 — 하나만 검사하면 나머지 둘은 조용히 틀릴 수 있다.
    """
    async def inner():
        await _doc("doc_frag", _A, "10", content_hash="c1")
        await _chunk("chunk_bare", "doc_frag", _A, "- **디제잉 포인트**: 4000")

        await _doc("doc_prefixed", _A, "11", content_hash="c2")
        await _chunk("chunk_prefixed", "doc_prefixed", _A, "- **디제잉 포인트**: 7000",
                     context_prefix="[아바타 해금 표 > 레벨 11]")

        await _doc("doc_sectioned", _A, "12", content_hash="c3")
        await _chunk("chunk_sectioned", "doc_sectioned", _A, "- **디제잉 포인트**: 10000",
                     section_path="아바타 해금 표")

        await _doc("doc_titled", _A, "로그인 정책", content_hash="c4")
        await _chunk("chunk_titled", "doc_titled", _A, "로그인 정책 — 비로그인 사용자는 …")

        sig = await _by_tenant()
        assert sig[_A]["identityless_chunks"] == 1

    _run(inner)


def test_empty_title_is_identityless():
    """제목이 빈 문서는 어디에도 신원이 없다 — `position('' in x)` 이 1 을 돌려주는 바람에
    조용히 통과하면 안 된다."""
    async def inner():
        await _doc("doc_untitled", _A, "", content_hash="c5")
        await _chunk("chunk_untitled", "doc_untitled", _A, "본문뿐인 조각")
        sig = await _by_tenant()
        assert sig[_A]["identityless_chunks"] == 1

    _run(inner)


# ── 전역 뷰는 테넌트별 뷰의 합 ─────────────────────────────────────────────────

def test_global_view_is_the_sum_of_tenants():
    async def inner():
        from nexus import db

        await _doc("doc_g1", _A, "사본", content_hash="ch-g")
        await _doc("doc_g2", _A, "사본 둘", content_hash="ch-g")
        await _doc("doc_g3", _B, "다른 테넌트 사본", content_hash="ch-g")
        await _chunk("chunk_g", "doc_g3", _B, "신원 없는 조각")

        per = await _by_tenant()
        row = dict(await db.fetch_one("SELECT * FROM v_entropy_signals"))
        for key in ("reingest_overwrite_events", "exact_dup_pairs",
                    "title_stem_collisions", "supersessions", "identityless_chunks"):
            assert row[key] == sum(t[key] for t in per.values()), key
        # 가로지르는 쌍이 사라졌는지 전역에서도 확인 (A 안의 1쌍만 남는다)
        assert row["exact_dup_pairs"] == 1

    _run(inner)


def test_global_view_returns_one_row_when_empty():
    """빈 DB 에서도 한 행. 기존 소비자가 `fetch_one` 이라 None 이 오면 그대로 죽는다."""
    async def inner():
        from nexus import db

        row = await db.fetch_one("SELECT * FROM v_entropy_signals")
        assert row is not None
        assert dict(row)["exact_dup_pairs"] == 0

    _run(inner)
