"""span 저장 — postgres. NEXUS_TEST_DB_URL 이 필요하다."""
import os

import pytest

from nexus import db
from nexus.search.span_store import persist_spans
from nexus.search.spans import Candidate, SpanSet

pytestmark = pytest.mark.asyncio

_DB = os.getenv("NEXUS_TEST_DB_URL")


@pytest.fixture(autouse=True)
async def _db_pool():
    """`clean_db`(conftest, autouse)는 TRUNCATE 만 한다 — `nexus.db` 의 전역 풀은
    직접 열어야 `persist_spans` 가 보는 풀과 검사가 보는 풀이 같아진다
    (`test_signals_db.py`·`test_answer_feedback_store.py` 와 같은 관례)."""
    os.environ["DATABASE_URL"] = _DB or ""
    await db.get_pool()
    yield
    await db.close_pool()


async def _a_search_log_row() -> int:
    return await db.fetch_val(
        "INSERT INTO search_log (path, route) VALUES ('/t', 'hybrid_only') RETURNING id")


@pytest.mark.integration
async def test_children_attach_to_the_right_stage(clean_db):
    log_id = await _a_search_log_row()
    spans = SpanSet(max_candidates=100)
    spans.add_leg(channel="original", leg="bm25",
                  candidates=[Candidate(rank=1, chunk_rid="b1", doc_rid="d1", raw_score=4.7)])
    spans.add_leg(channel="original", leg="vector",
                  candidates=[Candidate(rank=1, chunk_rid="v1", doc_rid="d2", raw_score=0.19)])
    await persist_spans(log_id, spans)

    rows = await db.fetch_all(
        """SELECT s.leg, c.chunk_rid FROM search_span s
           JOIN search_span_candidate c ON c.span_id = s.id
           WHERE s.search_log_id = $1 ORDER BY s.seq""", log_id)
    # 다중행 RETURNING 의 행 순서를 가정하면 여기서 뒤바뀐다.
    assert [(r["leg"], r["chunk_rid"]) for r in rows] == [("bm25", "b1"), ("vector", "v1")]


@pytest.mark.integration
async def test_deleting_the_parent_takes_everything(clean_db):
    log_id = await _a_search_log_row()
    spans = SpanSet(max_candidates=100)
    spans.add_leg(channel="original", leg="bm25",
                  candidates=[Candidate(rank=1, chunk_rid="b1", doc_rid="d1")])
    await persist_spans(log_id, spans)
    await db.execute("DELETE FROM search_log WHERE id = $1", log_id)
    assert await db.fetch_val("SELECT count(*) FROM search_span_candidate") == 0


@pytest.mark.integration
async def test_a_second_fusion_row_is_refused(clean_db):
    log_id = await _a_search_log_row()
    spans = SpanSet(max_candidates=100)
    spans.add_fusion(candidates=[], rrf_k=60, n_channels=1)
    spans.add_fusion(candidates=[], rrf_k=60, n_channels=1)   # 같은 요청에 둘째 fusion
    with pytest.raises(Exception):
        await persist_spans(log_id, spans, swallow=False)


@pytest.mark.integration
async def test_a_failing_batch_does_not_take_the_parent_with_it(clean_db):
    """⭐ 이 단위의 핵심 불변식. 부모가 같이 롤백되면 '유실' 을 기록할 수 없다."""
    log_id = await _a_search_log_row()
    spans = SpanSet(max_candidates=100)
    spans.add_fusion(candidates=[], rrf_k=60, n_channels=1)
    spans.add_fusion(candidates=[], rrf_k=60, n_channels=1)
    ok = await persist_spans(log_id, spans)          # swallow=True (프로덕션 경로)
    assert ok is False                                # 실패는 **보고된다**
    assert await db.fetch_val(
        "SELECT count(*) FROM search_log WHERE id = $1", log_id) == 1   # 부모는 살아 있다
    assert await db.fetch_val(
        "SELECT count(*) FROM search_span WHERE search_log_id = $1", log_id) == 0
