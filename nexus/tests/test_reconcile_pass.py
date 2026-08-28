"""정정 확인 패스 — 정정당한 문서가 정정한 문서를 이기는 것을 막는 장치.

⛔ 이 검사가 지켜야 할 성질은 둘이다: **정정을 데려온다**, 그리고 **근거를 부풀리지 않는다**.
둘째가 없으면 2026-08-28 의 실험을 반복한다 — 근거를 네 배로 불리고 점수를 하나도 못 샀다.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from nexus.search.reconcile import MAX_NAMES, MAX_PER_NAME, corrections_for, names_in


@dataclass
class _Hit:
    rid: str
    chunk_text: str = ""


class _Found:
    def __init__(self, hits):
        self.hits = hits


def test_only_code_like_names_are_pulled_out():
    """영어 산문 낱말을 이름으로 오인하면 2차 검색이 잡음으로 채워진다."""
    text = "이 문서는 isQueued 필드와 DjChangeType 을 설명한다. The answer should include details."
    got = names_in(text)
    assert "isQueued" in got and "DjChangeType" in got
    assert not any(t in got for t in ("answer", "should", "include", "details"))


def test_korean_prose_yields_no_names():
    assert names_in("큐에서 빠진 상태는 어떻게 표현되나") == []


def _run(hits, found_map, **kw):
    async def fake_search(query, **_):
        for name, res in found_map.items():
            if query.startswith(name):
                return _Found(res)
        return _Found([])
    return asyncio.run(corrections_for(hits, "t", "INTERNAL", search=fake_search, **kw))


def test_a_correction_is_brought_in():
    hits = [_Hit("c1", "DjData 에는 isQueued 필드가 있다")]
    got = _run(hits, {"isQueued": [_Hit("c9", "Phase DB-5: DJ Hard-Delete 전환")]})
    assert [h.rid for h in got] == ["c9"]


def test_chunks_already_in_the_evidence_are_not_added_twice():
    hits = [_Hit("c1", "isQueued 를 설명한다")]
    got = _run(hits, {"isQueued": [_Hit("c1", "같은 청크")]})
    assert got == []


def test_the_expansion_is_bounded():
    """⛔ 상한이 없으면 근거가 답이 아니라 문서 더미가 된다."""
    text = " ".join(f"nameOne{i}" for i in range(20))
    found = {f"nameOne{i}": [_Hit(f"x{i}{j}") for j in range(10)] for i in range(20)}
    got = _run([_Hit("c1", text)], found)
    assert len(got) <= MAX_NAMES * MAX_PER_NAME


def test_a_failing_second_pass_does_not_kill_the_search():
    """보강이 죽었다고 검색 결과까지 버리면, 있던 답도 못 준다."""
    async def boom(*a, **k):
        raise RuntimeError("검색 실패")
    got = asyncio.run(corrections_for([_Hit("c1", "isQueued")], "t", "INTERNAL", search=boom))
    assert got == []


def test_no_hits_means_no_second_pass():
    calls = []

    async def counting(query, **_):
        calls.append(query)
        return _Found([])
    asyncio.run(corrections_for([], "t", "INTERNAL", search=counting))
    assert calls == []
