"""기대한 문서가 **몇 위였나** — 패킷에 못 든 것까지.

⛔ **왜 생겼나 (설명 층 보고 2026-09-20, 두 판 연속).** 소비자가 *"사건에 맞는 절차 문서만
근거에 안 온다"* 를 보고했는데 그쪽이 볼 수 있는 것은 패킷에 **든** 조각의 제목뿐이라
*"빠진 문서가 21등인지 200등인지 구별할 수 없다"* 고 적었다. 우리 쪽은 질의 원문이 없어
네 모양으로 재현을 시도했고 네 번 다 반대 결과였다. 양쪽이 각자 절반만 보는 상태에서
처방을 고르면 추측이다.

⭐ **값은 이미 쌓이고 있었다** — `search_span_candidate` 가 경로별 순위·원점수를 남기는데
읽는 코드가 만료 작업 하나뿐이었다(실측 55,027행). 이 단위는 기능이 아니라 **읽을 자리**다.
"""

from __future__ import annotations

import os

import pytest

pytestmark_db = pytest.mark.skipif(
    not os.getenv("NEXUS_TEST_DB_URL"), reason="NEXUS_TEST_DB_URL 필요")

_TENANT = "search_explain_test"
_OTHER = "search_explain_other"


def test_the_hash_is_what_lets_a_caller_point_at_their_own_run():
    """호출자는 요청 식별자를 못 받는다. 같은 문자열을 다시 보내는 것이 유일한 손잡이이고,
    그 해시는 **순수**해야 한다 — 소금이나 시각이 섞이면 같은 질의가 다른 행을 가리킨다."""
    from nexus.search.signals import query_sha256

    assert query_sha256("파지 실패") == query_sha256("파지 실패")
    assert query_sha256("파지 실패") != query_sha256("파지 실패 ")
    assert len(query_sha256("x")) == 64


def test_the_reader_asks_for_the_policy_filter_by_name():
    """⛔ 제목을 내놓는 조인에 네 절이 **전부** 걸려야 한다.

    외부 평가 F3 이 정확히 이 자리였다 — 대체 문서 제목이 등급 필터 없이 프롬프트로 갔다.
    진단 경로라고 예외가 아니다. 오히려 진단은 *못 읽는 것까지* 보려는 경로라 더 샌다.
    """
    from nexus.search import span_store

    sql = span_store._EXPLAIN_SQL
    for clause in ("ch.tenant = ANY(", "ch.classification <= ",
                   "ch.is_quarantined = false", "ch.status = 'active'"):
        assert clause in sql, f"진단 조인에 {clause!r} 가 없다 — 못 읽는 문서의 제목이 샌다"
    assert "tenant = $2" in sql, "남의 principal 이 돌린 실행을 읽을 수 있다"


def test_it_reads_the_record_and_does_not_re_run_the_search():
    """⛔ 다시 돌리면 **그 사이 바뀐 코퍼스·설정** 위에서 다른 답이 나온다.

    그것은 사고를 재현한 것이 아니라 새 사고를 만든 것이다. 이 모듈은 검색을 부르지 않는다.
    """
    import inspect

    from nexus.search import span_store

    src = inspect.getsource(span_store)
    for forbidden in ("hybrid_search", "_bm25_search", "_vector_search"):
        assert forbidden not in src, f"{forbidden} 를 부른다 — 기록이 아니라 재실행이다"


# ── 배선: 실제로 기록에서 읽어 오는가 ────────────────────────────────────────

async def _seed_run(pool, tenant: str, query: str, titles_ranks):
    """`search_log` 한 행 + span 하나 + 후보들. 문서·조각도 같이 심는다."""
    from nexus.search.signals import query_sha256

    async with pool.acquire() as con:
        await con.execute("DELETE FROM chunks WHERE tenant=$1", tenant)
        await con.execute("DELETE FROM documents WHERE tenant=$1", tenant)
        await con.execute("DELETE FROM search_log WHERE tenant=$1", tenant)

        log_id = await con.fetchval(
            "INSERT INTO search_log (path, tenant, clearance, route, query_sha256, "
            "query_len, n_snippets) VALUES ('search_answer',$1,'INTERNAL','hybrid_only',"
            "$2,$3,10) RETURNING id",
            tenant, query_sha256(query), len(query))
        span_id = await con.fetchval(
            "INSERT INTO search_span (search_log_id, seq, stage, channel, leg, "
            "n_in, n_out, fired, score_kind) "
            "VALUES ($1, 1, 'leg', 'original', 'bm25', 200, 25, true, 'ts_rank_cd') RETURNING id",
            log_id)
        for rank, (title, classification) in enumerate(titles_ranks, 1):
            drid = f"doc_{tenant}_{rank}"
            crid = f"chunk_{tenant}_{rank}"
            await con.execute(
                "INSERT INTO documents (rid, tenant, source_uri, hash, title, doc_type, "
                "classification, status) VALUES ($1,$2,$3,'h',$4,'policy',"
                "$5::classification_level,'active')",
                drid, tenant, f"{tenant}:{rank}.md", title, classification)
            await con.execute(
                "INSERT INTO chunks (rid, tenant, source_uri, doc_rid, section_path, "
                "chunk_text, classification, status) VALUES ($1,$2,$3,$4,'5. 절차','본문',"
                "$5::classification_level,'active')",
                crid, tenant, f"{tenant}:{rank}.md", drid, classification)
            await con.execute(
                "INSERT INTO search_span_candidate (span_id, rank, chunk_rid, doc_rid, "
                "raw_score, dropped) VALUES ($1,$2,$3,$4,$5,$6)",
                span_id, rank, crid, drid, 1.0 / rank, rank > 20)
    return log_id


@pytestmark_db
@pytest.mark.asyncio
async def test_a_document_that_never_reached_the_packet_still_has_a_rank(db_pool):
    """⭐ **이 파일이 존재하는 이유가 이 한 줄이다.** 21위는 200위와 다른 사실이고,
    패킷만 보는 소비자에게는 둘이 똑같이 「없음」이다."""
    from nexus import db
    from nexus.search.signals import query_sha256
    from nexus.search.span_store import explain_query

    previous = db._pool
    db._pool = db_pool
    try:
        q = "failureClass=PAYLOAD_LOST 운영자 조치"
        await _seed_run(db_pool, _TENANT, q,
                        [(f"SOP-0{i} 절차", "INTERNAL") for i in range(1, 7)])

        got = await explain_query(query_sha256(q), _TENANT, [_TENANT], "INTERNAL")
        assert got is not None, "심은 실행을 못 찾았다"
        cands = got["spans"][0]["candidates"]
        by_title = {c["doc_title"]: c["rank"] for c in cands}
        assert by_title["SOP-06 절차"] == 6, f"순위가 안 왔다: {by_title}"
        assert all(c["raw_score"] is not None for c in cands), "원점수가 비었다"
        assert got["route"] == "hybrid_only"

        async with db_pool.acquire() as con:
            await con.execute("DELETE FROM search_log WHERE tenant=$1", _TENANT)
            await con.execute("DELETE FROM chunks WHERE tenant=$1", _TENANT)
            await con.execute("DELETE FROM documents WHERE tenant=$1", _TENANT)
    finally:
        db._pool = previous


@pytestmark_db
@pytest.mark.asyncio
async def test_a_rank_survives_what_the_caller_may_not_read_but_the_name_does_not(db_pool):
    """⛔ **순위는 보이고 이름은 권한이 있어야 보인다.**

    이름을 못 읽는다고 그 줄을 통째로 지우면, 빠진 이유가 「못 찾았다」인지 「권한이
    없다」인지 호출자가 영영 못 가른다. 그 둘은 고칠 사람이 다르다.
    """
    from nexus import db
    from nexus.search.signals import query_sha256
    from nexus.search.span_store import explain_query

    previous = db._pool
    db._pool = db_pool
    try:
        q = "등급이 갈리는 질의"
        await _seed_run(db_pool, _TENANT, q,
                        [("보이는 절차", "INTERNAL"), ("가려진 절차", "RESTRICTED")])

        got = await explain_query(query_sha256(q), _TENANT, [_TENANT], "INTERNAL")
        cands = {c["rank"]: c["doc_title"] for c in got["spans"][0]["candidates"]}
        assert cands[1] == "보이는 절차"
        assert cands[2] is None, "읽을 권한이 없는 문서의 제목이 샜다"
        assert set(cands) == {1, 2}, "권한 없는 후보의 **순위까지** 사라졌다"

        async with db_pool.acquire() as con:
            await con.execute("DELETE FROM search_log WHERE tenant=$1", _TENANT)
            await con.execute("DELETE FROM chunks WHERE tenant=$1", _TENANT)
            await con.execute("DELETE FROM documents WHERE tenant=$1", _TENANT)
    finally:
        db._pool = previous


@pytestmark_db
@pytest.mark.asyncio
async def test_another_principals_run_is_not_visible(db_pool):
    """귀속이 다른 실행은 안 보인다 — 질의 문자열을 알아도 마찬가지다."""
    from nexus import db
    from nexus.search.signals import query_sha256
    from nexus.search.span_store import explain_query

    previous = db._pool
    db._pool = db_pool
    try:
        q = "남의 질의"
        await _seed_run(db_pool, _OTHER, q, [("남의 문서", "INTERNAL")])

        mine = await explain_query(query_sha256(q), _TENANT, [_TENANT], "INTERNAL")
        assert mine is None, "다른 principal 의 실행이 보인다"
        theirs = await explain_query(query_sha256(q), _OTHER, [_OTHER], "INTERNAL")
        assert theirs is not None, "대조군 — 자기 것은 보여야 한다"

        async with db_pool.acquire() as con:
            await con.execute("DELETE FROM search_log WHERE tenant=$1", _OTHER)
            await con.execute("DELETE FROM chunks WHERE tenant=$1", _OTHER)
            await con.execute("DELETE FROM documents WHERE tenant=$1", _OTHER)
    finally:
        db._pool = previous


@pytestmark_db
@pytest.mark.asyncio
async def test_a_query_never_run_is_not_found_rather_than_empty(db_pool):
    """**「안 돌렸다」와 「돌렸는데 후보가 없었다」는 다른 사실이다.**"""
    from nexus import db
    from nexus.search.signals import query_sha256
    from nexus.search.span_store import explain_query

    previous = db._pool
    db._pool = db_pool
    try:
        got = await explain_query(query_sha256("한 번도 안 던진 질의"), _TENANT,
                                  [_TENANT], "INTERNAL")
        assert got is None
    finally:
        db._pool = previous
