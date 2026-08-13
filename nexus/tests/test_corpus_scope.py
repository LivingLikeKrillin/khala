"""볼 수 있는 것을 설명하는 진단 (`nexus/search/corpus_scope.py`).

검색 모듈에서 갈라져 나온 이유는 그 파일 docstring 에 있다 — 검사가 옳았고 함수가 잘못된
파일에 있었다.
"""

from __future__ import annotations

from nexus.search import corpus_scope as C


class _Row(dict):
    """asyncpg.Record 처럼 __getitem__ 으로 읽히는 최소 대역."""


def _wire(monkeypatch, one, many=None):
    async def fetch_one(_q, *_a):
        return one

    async def fetch_all(_q, *_a):
        return (many or []).pop(0) if many else []
    monkeypatch.setattr(C.db, "fetch_one", fetch_one)
    monkeypatch.setattr(C.db, "fetch_all", fetch_all)


async def test_it_reports_total_visible_and_freshness(monkeypatch):
    _wire(monkeypatch, _Row(total=116, visible=108, newest_visible="2026-08-11"),
          many=[[_Row(src="notion", n=108)], [_Row(title="로그인 정책")]])
    out = await C.visibility_counts("default", "INTERNAL")
    assert (out["total"], out["visible"]) == (116, 108)
    assert out["newest"] == "2026-08-11"
    assert out["sources"] == {"notion": 108}
    assert out["sample_titles"] == ["로그인 정책"]


async def test_nothing_visible_means_no_sources_and_no_samples(monkeypatch):
    """볼 수 없는데 예시를 보여주면 거짓이다 — 그리고 쓸데없는 왕복 둘이 붙는다."""
    asked = []

    async def fetch_one(_q, *_a):
        return _Row(total=116, visible=0, newest_visible=None)

    async def fetch_all(q, *_a):
        asked.append(q)
        return []
    monkeypatch.setattr(C.db, "fetch_one", fetch_one)
    monkeypatch.setattr(C.db, "fetch_all", fetch_all)

    out = await C.visibility_counts("default", "PUBLIC")
    assert out["visible"] == 0 and out["sources"] == {} and out["sample_titles"] == []
    assert asked == [], "안 보이는데 출처·표본을 물었다"


async def test_a_missing_row_is_zero_not_a_crash(monkeypatch):
    _wire(monkeypatch, None)
    out = await C.visibility_counts("default", "PUBLIC")
    assert (out["total"], out["visible"], out["newest"]) == (0, 0, None)


async def test_samples_come_from_the_dominant_source(monkeypatch):
    """**최신은 대표가 아니다.** 문서 8건을 일괄 복구하자 예시가 전부 그것으로 채워졌다 —
    108/116 이 노션 정책인 코퍼스가 "Nexus 문서 모음" 처럼 보였다."""
    seen = []

    async def fetch_one(_q, *_a):
        return _Row(total=116, visible=116, newest_visible="2026-08-13")

    async def fetch_all(q, *_a):
        seen.append(q)
        if len(seen) == 1:
            return [_Row(src="notion", n=108), _Row(src="other", n=8)]
        return [_Row(title="로그인 정책")]
    monkeypatch.setattr(C.db, "fetch_one", fetch_one)
    monkeypatch.setattr(C.db, "fetch_all", fetch_all)

    await C.visibility_counts("default", "INTERNAL")
    assert "ext-notion" in seen[1], "표본을 가장 큰 출처로 좁히지 않았다"
