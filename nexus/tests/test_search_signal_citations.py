"""검색 신호에 인용 지표 — SPEC-nexus-search-signal-completeness §6.

extract_signals 가 AnswerResult 에서 n_citations/unverified_citations 를 뽑고, 스트림처럼
answer 가 없을 땐 명시 override 를 받는지 순수 검증. (DB persist·뷰는 통합 테스트.)
"""

from __future__ import annotations

from dataclasses import dataclass, field

from nexus.search.signals import extract_signals


@dataclass
class _Res:
    hits: list = field(default_factory=list)
    graph: object = None
    route_used: str = "hybrid_only"


@dataclass
class _Ans:
    citations: list = field(default_factory=list)
    unverified_citations: int = 0
    llm_failed: bool = False


def _sig(result=None, answer=None, **kw):
    kw.setdefault("path", "search_answer")
    kw.setdefault("tenant", "default")
    kw.setdefault("clearance", "INTERNAL")
    kw.setdefault("query", "q")
    return extract_signals(result or _Res(), answer, **kw)


def test_derives_citations_from_answer():
    ans = _Ans(citations=[{"t": 1}, {"t": 2}], unverified_citations=1)
    sig = _sig(answer=ans)
    assert sig.n_citations == 2
    assert sig.unverified_citations == 1


def test_no_answer_leaves_citations_unmeasured():
    sig = _sig(answer=None)
    assert sig.n_citations is None            # 미측정(≠ 0)
    assert sig.unverified_citations is None
    assert sig.llm_failed is False


def test_explicit_override_for_stream_without_answer():
    sig = _sig(answer=None, n_citations=3, unverified_citations=2, llm_failed=True)
    assert sig.n_citations == 3
    assert sig.unverified_citations == 2
    assert sig.llm_failed is True             # 스트림 경로


def test_explicit_beats_answer_derived():
    ans = _Ans(citations=[{"t": 1}], unverified_citations=0)
    sig = _sig(answer=ans, n_citations=9, unverified_citations=4)
    assert sig.n_citations == 9 and sig.unverified_citations == 4
