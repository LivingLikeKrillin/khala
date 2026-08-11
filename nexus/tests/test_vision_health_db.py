"""재현율 컬럼과 표면 (DB 통합) — SPEC-nexus-vision-reproducibility §4.4~§4.7.

컬럼은 **거짓말을 저장할 수 없어야** 하고, 값은 사람이 보는 자리에 닿아야 한다. 둘 다 이 리포가
이미 한 번씩 실패한 자리다: 제약 없는 컬럼은 하니스 버그의 -1 을 정당한 비율로 저장하고,
아무도 join 하지 않는 컬럼은 로그에 묻힌 측정과 같다.
"""

from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.skipif(not os.getenv("NEXUS_TEST_DB_URL"), reason="NEXUS_TEST_DB_URL 필요")

_T = "vh_test"


@pytest.fixture
async def clean(db_pool):
    from nexus import db

    db._pool = db_pool
    async with db_pool.acquire() as con:
        await con.execute("DELETE FROM vision_extractions WHERE tenant = $1", _T)
        await con.execute("DELETE FROM chunks WHERE tenant = $1", _T)
        await con.execute("DELETE FROM documents WHERE tenant = $1", _T)
    yield
    async with db_pool.acquire() as con:
        await con.execute("DELETE FROM vision_extractions WHERE tenant = $1", _T)
    db._pool = None


async def _row(pool, sha: str, rate=None):
    async with pool.acquire() as con:
        await con.execute(
            "INSERT INTO vision_extractions (tenant, image_sha256, extractor_identity, text, "
            "  reader_variation) VALUES ($1,$2,'m/p','t',$3)", _T, sha, rate)


async def test_the_column_refuses_an_impossible_rate(clean, db_pool):
    """§4.4 — 제약이 DB 에 있어야 한다. 애플리케이션 코드가 아니라."""
    import asyncpg

    await _row(db_pool, "ok0", 0)
    await _row(db_pool, "ok1", 1)
    for bad in (-0.1, 1.1):
        with pytest.raises(asyncpg.CheckViolationError):
            await _row(db_pool, f"bad{bad}", bad)


async def test_null_is_the_default_and_means_unmeasured(clean, db_pool):
    from nexus import db

    await _row(db_pool, "sha_null")
    got = await db.fetch_val(
        "SELECT reader_variation FROM vision_extractions WHERE image_sha256 = 'sha_null'")
    assert got is None


async def test_status_counts_unmeasured_and_above_threshold(clean, db_pool):
    """§4.7 — 값이 사람이 보는 자리에 닿는가."""
    from nexus.ingest.vision_health import MAX_VARIATION, fetch_reader_health

    await _row(db_pool, "a")                      # 미측정
    await _row(db_pool, "b", MAX_VARIATION)       # 문턱 이하 — 경고 아님
    await _row(db_pool, "c", 0.9)                 # 문턱 초과

    h = await fetch_reader_health(_T)
    assert h["extractions"] == 3
    assert h["unmeasured"] == 1
    assert h["above_threshold"] == 1


async def test_a_tenant_with_no_machine_read_chunks_reports_none(clean, db_pool):
    """새 상시 경보를 만들지 않는다 — 그림이 없는 테넌트에는 할 말이 없다."""
    from nexus.ingest.vision_health import fetch_reader_health

    h = await fetch_reader_health("vh_empty")
    assert h["machine_read_chunks"] == 0 and h["extractions"] == 0


async def test_measuring_does_not_write_extractions(clean, db_pool):
    """§4.6 — 측정 단계는 DB 를 건드리지 않는다. 두 번째 호출이 조용히 기록이 되면 안 된다."""
    import hashlib
    import json
    from pathlib import Path

    from nexus import db
    from scripts import vision_reproducibility as vr

    await _row(db_pool, "keep", 0.5)

    def digest() -> str:
        return hashlib.sha256(str(rows).encode()).hexdigest()

    rows = await db.fetch_all(
        "SELECT tenant, image_sha256, text, reader_variation FROM vision_extractions "
        "WHERE tenant = $1 ORDER BY image_sha256", _T)
    before = digest()

    tmp = Path("/tmp/vh")
    tmp.mkdir(exist_ok=True)
    (tmp / "one.json").write_text(json.dumps({"k": {"text": "Ava_01 60"}}), encoding="utf-8")
    (tmp / "two.json").write_text(json.dumps({"k": {"text": "Ava_01 61"}}), encoding="utf-8")
    vr.LOCAL = tmp
    vr.ARMS = {"probe": ("one.json", "two.json", lambda v: v["text"], None)}

    await vr.measure("probe")

    rows = await db.fetch_all(
        "SELECT tenant, image_sha256, text, reader_variation FROM vision_extractions "
        "WHERE tenant = $1 ORDER BY image_sha256", _T)
    assert digest() == before, "측정이 추출 행을 바꿨다"
