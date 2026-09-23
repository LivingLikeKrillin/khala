"""ClaimRepository 통합 테스트.

주의: 이 환경(Windows + pytest-asyncio)에서 async-generator fixture가
`run_until_complete` 재진입으로 깨지므로(conftest db_pool 포함), pytest-asyncio를
거치지 않고 동기 테스트 + 자체 asyncio 루프로 풀을 관리한다.
asyncpg는 Windows에서 SelectorEventLoop를 요구하므로 명시적으로 사용.
"""

import asyncio
import os
import sys

import pytest

from nexus.claims.repository import ClaimRepository
from nexus.models.claim import Claim

DB_URL = os.getenv("NEXUS_TEST_DB_URL")
pytestmark = pytest.mark.skipif(not DB_URL, reason="NEXUS_TEST_DB_URL 필요 (통합 테스트)")


def _run(coro_fn):
    """자체 SelectorEventLoop에서 coro_fn(pool)을 실행. 풀 생성·정리·claims TRUNCATE 포함."""
    if sys.platform == "win32":
        loop = asyncio.SelectorEventLoop()
    else:
        loop = asyncio.new_event_loop()

    async def _outer():
        import asyncpg

        pool = await asyncpg.create_pool(DB_URL, min_size=1, max_size=3)
        try:
            async with pool.acquire() as con:
                await con.execute("TRUNCATE claims CASCADE")
            return await coro_fn(pool)
        finally:
            await pool.close()

    try:
        return loop.run_until_complete(_outer())
    finally:
        loop.close()


def test_upsert_and_find_by_concept():
    async def inner(pool):
        repo = ClaimRepository(pool)
        c = Claim(
            claim_id="basic-max-projects",
            kind="invariant",
            concepts=["Basic", "프로젝트"],
            statement="Basic 최대 N개",
            value_source="PlanPolicy.BASIC_MAX_PROJECTS",
            value_ref_kind="code_constant",
            owner="@be",
            value_symbol_hash="abc123",
            last_verified_commit="deadbee",
        )
        await repo.upsert(c)
        return await repo.find_by_concept("Basic", tenant="default", clearance="INTERNAL")

    found = _run(inner)
    got = next(x for x in found if x.claim_id == "basic-max-projects")
    assert got.value_source.endswith("BASIC_MAX_PROJECTS")
    assert got.value_symbol_hash == "abc123"  # 신선도용 hash 왕복 보존
    assert got.claim_status == "unverified"


def test_find_respects_classification_clearance():
    async def inner(pool):
        repo = ClaimRepository(pool)
        await repo.upsert(Claim(
            claim_id="secret-rule", kind="invariant", concepts=["비밀"],
            statement="기밀 규칙", owner="@be", classification="RESTRICTED",
        ))
        return await repo.find_by_concept("비밀", tenant="default", clearance="INTERNAL")

    found = _run(inner)
    assert all(x.claim_id != "secret-rule" for x in found)  # RESTRICTED는 INTERNAL에 안 보임


def test_ruling_fields_round_trip():
    """소유자의 판정 다섯 칸(migration 044)이 저장·조회를 왕복하는가 — 값 없는 판정도."""
    async def inner(pool):
        repo = ClaimRepository(pool)
        await repo.upsert(Claim(
            claim_id="nickname-max", kind="invariant", concepts=["닉네임"],
            statement="닉네임 길이 상한", value_source="Req.nickname@Size.max",
            value_ref_kind="code_annotation", owner="@be",
            ruled_value="12", ruled_source="정책 문서", ruled_by="@owner", ruled_on="2026-08-31",
            ruling_note="코드 20 은 12 로",
        ))
        await repo.upsert(Claim(
            claim_id="capacity", kind="invariant", concepts=["정원"],
            statement="정원", owner="@be",
            ruled_value=None, ruled_by="@owner", ruled_on="2026-08-31",
            ruling_note="코드 값 기각, 대체 미정",
        ))
        return await repo.find_all(tenant="default", clearance="INTERNAL")

    found = {c.claim_id: c for c in _run(inner)}
    n = found["nickname-max"]
    assert (n.ruled_value, n.ruled_source, n.ruled_by, n.ruled_on, n.ruling_note) == (
        "12", "정책 문서", "@owner", "2026-08-31", "코드 20 은 12 로")
    assert n.has_ruling
    c = found["capacity"]
    assert c.ruled_value is None and c.ruling_note == "코드 값 기각, 대체 미정" and c.has_ruling
