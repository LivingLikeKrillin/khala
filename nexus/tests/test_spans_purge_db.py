"""span 후보 보존 만료 — postgres. NEXUS_TEST_DB_URL 이 필요하다.

detail tier(`search_span_candidate`)만 만료된다. summary tier(`search_span`)는
`search_log` 에서 캐스케이드될 뿐 여기서 지우지 않는다 — 순위 매겨진 후보 목록이
질의의 지문이라 상관 노출 위험이 있는 것은 후보 행이지, 요약 span 행이 아니다.
"""
import os

import pytest

from nexus import db
from nexus.search.span_store import persist_spans, purge_candidates
from nexus.search.spans import Candidate, SpanSet

pytestmark = pytest.mark.asyncio

_DB = os.getenv("NEXUS_TEST_DB_URL")


@pytest.fixture(autouse=True)
async def _db_pool():
    """`clean_db`(conftest, autouse)는 TRUNCATE 만 한다 — `nexus.db` 의 전역 풀은
    직접 열어야 `purge_candidates` 가 보는 풀과 검사가 보는 풀이 같아진다
    (`test_spans_store_db.py` 와 같은 관례)."""
    os.environ["DATABASE_URL"] = _DB or ""
    await db.get_pool()
    yield
    await db.close_pool()


async def _a_search_log_row() -> int:
    return await db.fetch_val(
        "INSERT INTO search_log (path, route) VALUES ('/t', 'hybrid_only') RETURNING id")


async def _age_spans(log_id: int, days: int) -> None:
    await db.execute(
        "UPDATE search_span SET ts = now() - interval '1 day' * $2 WHERE search_log_id = $1",
        log_id, days)


@pytest.mark.integration
async def test_purge_cuts_candidates_leaves_summaries_and_stamps_only_what_had_rows(clean_db):
    log_id = await _a_search_log_row()
    spans = SpanSet(max_candidates=100)
    spans.add_leg(channel="original", leg="bm25",
                  candidates=[Candidate(rank=1, chunk_rid="b1", doc_rid="d1")])
    spans.add_answer(n_in=1, n_citations=0)          # 후보가 원래 없는 단계
    await persist_spans(log_id, spans)
    await db.execute(
        "UPDATE search_span SET ts = now() - interval '10 days' WHERE search_log_id = $1",
        log_id)

    assert await purge_candidates(retain_days=3) == 1

    assert await db.fetch_val("SELECT count(*) FROM search_span_candidate") == 0
    assert await db.fetch_val("SELECT count(*) FROM search_span") == 2   # 요약은 남는다
    stamped = await db.fetch_all(
        "SELECT stage, candidates_purged_at FROM search_span WHERE search_log_id = $1", log_id)
    by_stage = {r["stage"]: r["candidates_purged_at"] for r in stamped}
    assert by_stage["leg"] is not None
    # 후보가 애초에 없던 단계에 도장을 찍으면 *지워졌다* 와 *원래 없었다* 가 같아진다.
    assert by_stage["answer"] is None


@pytest.mark.integration
async def test_rows_inside_the_window_are_left_untouched(clean_db):
    """3일 창 안(방금 쌓인) 후보는 손대지 않는다 — 지우지도, 도장도 찍지 않는다."""
    log_id = await _a_search_log_row()
    spans = SpanSet(max_candidates=100)
    spans.add_leg(channel="original", leg="bm25",
                  candidates=[Candidate(rank=1, chunk_rid="b1", doc_rid="d1")])
    await persist_spans(log_id, spans)
    # ts 는 기본 now() 그대로 — 창 밖으로 밀지 않는다.

    assert await purge_candidates(retain_days=3) == 0

    assert await db.fetch_val("SELECT count(*) FROM search_span_candidate") == 1
    row = await db.fetch_one(
        "SELECT candidates_purged_at FROM search_span WHERE search_log_id = $1", log_id)
    assert row["candidates_purged_at"] is None


@pytest.mark.integration
async def test_purge_counts_every_span_and_running_twice_is_safe(clean_db):
    """⭐ 카운팅 결함 회귀 — RETURNING 1 스케치는 span 이 몇 개든 1 을 낸다.
    둘 이상을 만료시켜 실제 개수가 나오는지 확인하고, 같은 시각에 다시 돌려도
    이중 도장·에러 없이 안전한지(스케줄러 틱마다 도는 함수라 필수) 함께 본다.
    """
    log_a = await _a_search_log_row()
    log_b = await _a_search_log_row()
    spans_a = SpanSet(max_candidates=100)
    spans_a.add_leg(channel="original", leg="bm25",
                     candidates=[Candidate(rank=1, chunk_rid="a1", doc_rid="d1")])
    spans_b = SpanSet(max_candidates=100)
    spans_b.add_leg(channel="original", leg="vector",
                     candidates=[Candidate(rank=1, chunk_rid="b1", doc_rid="d2")])
    await persist_spans(log_a, spans_a)
    await persist_spans(log_b, spans_b)
    await _age_spans(log_a, 10)
    await _age_spans(log_b, 10)

    first = await purge_candidates(retain_days=3)
    assert first == 2, "두 span 이 만료됐는데 개수가 실제와 다르다"

    assert await db.fetch_val("SELECT count(*) FROM search_span_candidate") == 0
    stamped_at = {r["search_log_id"]: r["candidates_purged_at"] for r in await db.fetch_all(
        "SELECT search_log_id, candidates_purged_at FROM search_span")}
    assert stamped_at[log_a] is not None
    assert stamped_at[log_b] is not None

    second = await purge_candidates(retain_days=3)
    assert second == 0, "이미 지운 span 을 다시 세면 스케줄러 틱마다 값이 부풀어야 하는데 그렇지 않다"
    restamped_at = {r["search_log_id"]: r["candidates_purged_at"] for r in await db.fetch_all(
        "SELECT search_log_id, candidates_purged_at FROM search_span")}
    assert restamped_at[log_a] == stamped_at[log_a], "두 번째 돌 때 도장이 덮어써지면 안 된다"
    assert restamped_at[log_b] == stamped_at[log_b]
