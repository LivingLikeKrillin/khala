"""근거 적합도의 **크기**가 신호로 남는가 (`search/confidence.py` → `search_log`).

문턱(`FAR_DISTANCE`·`WEAK_BM25`)은 지어낸 질문 17개로 정해졌다. 진짜 기준은 실사용 질문에서만
나오는데, 지금은 그 질문이 어떤 거리·어떤 키워드 점수로 답해졌는지 **아무 데도 안 남는다** —
즉 문턱을 다시 측정할 재료가 매 요청마다 버려진다.

**불리언이 아니라 크기를 남긴다.** `weak` 는 오늘의 문턱으로 계산된 값이라, 문턱을 옮기면
지나간 행의 뜻이 조용히 바뀐다. 거리와 점수는 문턱과 무관한 사실이다.

**죽은 다리는 `None` 이다.** 0.0 으로 채우면 거리 0 = "완벽히 맞았다", BM25 0 = "전혀 못 맞췄다"
로 읽혀 두 방향으로 거짓말한다. 못 측정한 것과 측정해서 낮은 것은 다른 사실이다.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

import pytest


@dataclass
class _Hit:
    score: float = 0.5
    doc_rid: str = "doc_1"


@dataclass
class _Result:
    hits: list = field(default_factory=list)
    graph: object | None = None
    route_used: str = "hybrid_only"
    confidence: object | None = None


def test_the_magnitudes_reach_the_signal():
    from nexus.search.confidence import Confidence
    from nexus.search.signals import extract_signals

    sig = extract_signals(
        _Result(hits=[_Hit()], confidence=Confidence(top_distance=0.31, top_bm25=2.4)),
        None, path="search_answer", tenant="t", clearance="INTERNAL", query="q")
    assert sig.top_distance == pytest.approx(0.31)
    assert sig.top_bm25 == pytest.approx(2.4)


def test_a_dead_leg_stays_unmeasured():
    """벡터 다리가 죽으면 거리는 **없는 것**이지 0 이 아니다."""
    from nexus.search.confidence import Confidence
    from nexus.search.signals import extract_signals

    sig = extract_signals(
        _Result(hits=[_Hit()], confidence=Confidence(top_distance=None, top_bm25=1.1)),
        None, path="search", tenant="t", clearance="INTERNAL", query="q")
    assert sig.top_distance is None, "못 측정한 것을 0 으로 적으면 '완벽히 맞았다' 로 읽힌다"
    assert sig.top_bm25 == pytest.approx(1.1)


def test_a_result_without_confidence_does_not_break_the_signal():
    """대조군: 적합도를 안 싣는 호출부(스트림·구형 더블)가 신호를 죽이지 않는다."""
    from nexus.search.signals import extract_signals

    sig = extract_signals(_Result(hits=[_Hit()]), None, path="search",
                          tenant="t", clearance="INTERNAL", query="q")
    assert sig.top_distance is None and sig.top_bm25 is None


@pytest.mark.skipif(not os.getenv("NEXUS_TEST_DB_URL"), reason="NEXUS_TEST_DB_URL 필요")
async def test_the_magnitudes_land_in_search_log(db_pool):
    """행에 실제로 앉는가 — 컬럼을 만들어 두고 INSERT 목록에 안 넣은 적이 이 리포에 있다."""
    from nexus import db
    from nexus.search.confidence import Confidence
    from nexus.search.signals import extract_signals, record_search

    db._pool = db_pool
    tenant = "evidence_fit_signal"
    async with db_pool.acquire() as con:
        await con.execute("DELETE FROM search_log WHERE tenant=$1", tenant)
    try:
        sig = extract_signals(
            _Result(hits=[_Hit()], confidence=Confidence(top_distance=0.512, top_bm25=0.7)),
            None, path="search_answer", tenant=tenant, clearance="INTERNAL", query="q")
        await record_search(sig, await_persist=True)
        row = await db.fetch_one(
            "SELECT top_distance, top_bm25 FROM search_log WHERE tenant=$1", tenant)
        assert row is not None, "행이 안 남았다"
        assert row["top_distance"] == pytest.approx(0.512)
        assert row["top_bm25"] == pytest.approx(0.7)
    finally:
        async with db_pool.acquire() as con:
            await con.execute("DELETE FROM search_log WHERE tenant=$1", tenant)
        db._pool = None


# ── 못 측정한 것과 측정해서 0점 (2026-08-24 라이브에서 잡힘) ──────────────────────────

async def test_a_keyword_leg_that_matched_nothing_reports_zero_not_unknown(monkeypatch):
    """*"오늘 서울 날씨 알려줘"* 는 거리 0.608(멀다)인데도 약함 판정을 못 받았다.

    키워드 다리가 **돌았고 한 행도 못 잡은** 것을 `None` 으로 돌려줬고, `Confidence.weak` 은
    `None` 을 *못 측정한 것*으로 읽어(그건 옳다) 판정을 접었다. 코퍼스 밖의 가장 강한 증거가
    그 뭉침 속에서 사라진 것이다.
    """
    from nexus.search import hybrid

    async def _no_rows(*a, **k):
        return []

    monkeypatch.setattr(hybrid.db, "fetch_all", _no_rows)
    _hits, top = await hybrid._bm25_search("날씨", "default", "INTERNAL")
    assert top == 0.0, "돌았는데 못 잡은 것은 0점이다"


async def test_a_keyword_leg_that_never_ran_still_reports_unknown(monkeypatch):
    """토크나이저가 텀을 못 만들면 질의가 없었던 것이다 — 그때는 여전히 `None`.

    이 구분이 무너지면 **다리가 죽은 배포**가 전부 '코퍼스 밖' 으로 보고된다.
    """
    from nexus.search import hybrid

    async def _boom(*a, **k):
        raise AssertionError("tsquery 가 비면 DB 를 만지면 안 된다")

    monkeypatch.setattr(hybrid.db, "fetch_all", _boom)
    _hits, top = await hybrid._bm25_search("   ", "default", "INTERNAL")
    assert top is None


def test_zero_counts_as_weak_but_unknown_does_not():
    """두 사실이 `Confidence` 에서 갈리는지 — 여기가 갈라지지 않으면 위 구분은 장식이다."""
    from nexus.search.confidence import Confidence

    assert Confidence(top_distance=0.9, top_bm25=0.0).weak is True
    assert Confidence(top_distance=0.9, top_bm25=None).weak is False
