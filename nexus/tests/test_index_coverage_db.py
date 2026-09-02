"""인덱스 커버리지 (DB 통합) — SPEC-nexus-index-completeness §6.

여기서 지키는 것은 하나다: **없는 것을 센다.** 있는 것만 세는 집계는 빠진 청크를 모집단에서
먼저 지워버리기 때문에, 무엇이 검색에서 사라졌는지 영원히 대답할 수 없다 (§2.1).

정리는 `clean_db`(autouse TRUNCATE)에 맡긴다 — 손으로 DELETE 를 얹었더니 그 커넥션이 픽스처의
TRUNCATE 와 잠금으로 엉켜 스위트가 멈췄다.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration

_V768 = "[" + ",".join(["0"] * 768) + "]"
_V1024 = "[" + ",".join(["0"] * 1024) + "]"

_T = "cov_test_tenant"


async def _seed(pool, rows: list[dict], doc_status: str = "active") -> None:
    """청크를 심는다. **문서 상태도 인자다** — §3.1a 가 보는 것이 그것이다."""
    async with pool.acquire() as con:
        await con.execute(
            "INSERT INTO documents (rid, source_uri, hash, tenant, status) "
            "VALUES ('cov_doc','git://cov','h',$1,$2::resource_status)", _T, doc_status)
        for r in rows:
            await con.execute(
                "INSERT INTO chunks (rid, source_uri, doc_rid, chunk_text, tenant, status, "
                "  is_quarantined, embedding, embedding_1024, tsvector_ko) "
                "VALUES ($1,'git://cov','cov_doc','t',$2,$3::resource_status,$4,"
                "        $5::vector,$6::vector,$7::tsvector)",
                r["rid"], _T, r.get("status", "active"), r.get("quarantined", False),
                r.get("v768"), r.get("v1024"), r.get("ts"))


async def _coverage(db_url: str) -> list[dict]:
    """설정 경로가 아니라 **테스트가 여는 풀**로 조회한다 — 대상 DB 를 인자로 못박기 위해서."""
    import os

    from nexus import db
    from nexus.index.embed_health import fetch_coverage_by_tenant

    os.environ["DATABASE_URL"] = db_url
    await db.close_pool()
    await db.get_pool()
    try:
        return await fetch_coverage_by_tenant()
    finally:
        await db.close_pool()


def _row(coverage: list[dict]) -> dict:
    return next(r for r in coverage if r["tenant"] == _T)


async def test_counts_the_missing_and_excludes_what_no_leg_reads(db_pool, db_url):
    """§6-1 — 벡터 없는 활성 청크는 세고, 격리·superseded 는 안 센다."""
    await _seed(db_pool, [
        {"rid": "cov_ok", "v1024": _V1024, "ts": "'a'"},
        {"rid": "cov_gap", "v1024": None, "ts": "'a'"},           # ← 이것이 구멍이다
        {"rid": "cov_quar", "v1024": None, "ts": "'a'", "quarantined": True},
        {"rid": "cov_sup", "v1024": None, "ts": "'a'", "status": "superseded"},
    ])
    row = _row(await _coverage(db_url))
    assert row["active"] == 2, "격리·superseded 는 활성 모집단이 아니다"
    assert row["embedding_1024"] == 1
    assert row["gap_1024"] == 1


async def test_active_chunk_under_a_dead_document_is_not_a_gap(db_pool, db_url):
    """§6-1·§3.1a — 어느 경로도 읽지 않는 청크를 구멍으로 세면 영원히 안 꺼지는 경보가 된다."""
    await _seed(db_pool, [{"rid": "cov_orphan", "v1024": None, "ts": "'a'"}],
                doc_status="superseded")
    row = next((r for r in await _coverage(db_url) if r["tenant"] == _T), None)
    assert row is None or row["active"] == 0


async def test_empty_tsvector_is_as_dark_as_a_null_one(db_pool, db_url):
    """§6-2 — `''::tsvector` 는 NULL 이 아니지만 키워드 경로에서 똑같이 안 잡힌다."""
    await _seed(db_pool, [
        {"rid": "cov_ts_ok", "v1024": _V1024, "ts": "'a'"},
        {"rid": "cov_ts_null", "v1024": _V1024, "ts": None},
        {"rid": "cov_ts_empty", "v1024": _V1024, "ts": ""},
    ])
    row = _row(await _coverage(db_url))
    assert row["bm25"] == 1
    assert row["gap_bm25"] == 2, "NULL 과 빈 tsvector 는 둘 다 어둡다"


async def test_a_waived_chunk_is_still_a_gap(db_pool, db_url):
    """§6-3·§3.1c — **웨이버를 커버리지에서 빼지 않는다.** 빼면 진짜 구멍을 가린다.

    (2026-08-14: "웨이버는 청크당 1행이라 세대를 표현하지 못한다" 던 원래 이유는
    `SPEC-nexus-embedding-provenance-grain` §3.4 로 사라졌다 — PK 가 `(chunk_rid, model)` 다.
    그래도 **빼지 않는다는 결론은 그대로**다: 포기한 내용도 검색에서 빠진 내용이다.)

    `clean_db` 는 `embed_waivers` 를 TRUNCATE 하지 않으므로 **여기서 치운다** — 안 치웠더니
    다음 파일의 reembed 시험 둘이 내가 흘린 행 위에서 빨갛게 됐다.
    """
    await _seed(db_pool, [{"rid": "cov_waived", "v1024": None, "ts": "'a'"}])
    async with db_pool.acquire() as con:
        await con.execute(
            "INSERT INTO embed_waivers (chunk_rid, model, reason, waived_by) "
            "VALUES ('cov_waived','nomic-embed-text','over-length','test') "
            "ON CONFLICT (chunk_rid, model) DO NOTHING")
    try:
        assert _row(await _coverage(db_url))["gap_1024"] == 1
    finally:
        async with db_pool.acquire() as con:
            await con.execute("DELETE FROM embed_waivers WHERE chunk_rid = 'cov_waived'")


async def test_both_vector_columns_are_reported(db_pool, db_url):
    """§3.2 — 옛 컬럼의 구멍이 곧 롤백이 잃을 것이다 (ADR-0009 미결 항목)."""
    await _seed(db_pool, [
        {"rid": "cov_new_only", "v768": None, "v1024": _V1024, "ts": "'a'"},
        {"rid": "cov_both", "v768": _V768, "v1024": _V1024, "ts": "'a'"},
    ])
    row = _row(await _coverage(db_url))
    assert row["embedding_1024"] == 2 and row["gap_1024"] == 0
    assert row["embedding"] == 1 and row["gap_768"] == 1
