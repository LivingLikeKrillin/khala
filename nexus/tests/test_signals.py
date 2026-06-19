"""검색 품질 신호 — 순수 추출(extract_signals) + best-effort IO(record_search).

a2a_audit 패턴 미러링: 원문 query는 sha256+len으로만 기록(Nexus 원칙 #3).
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field

from structlog.testing import capture_logs

from nexus.search.signals import extract_signals, query_sha256
from nexus.search.signals import SIGNAL_EVENT, record_search  # Task 2에서 추가


# ── 테스트용 더크 타입(실 클래스 import 불필요) ──
@dataclass
class _Hit:
    score: float


@dataclass
class _Graph:
    edges: list = field(default_factory=list)
    observed_edges: list = field(default_factory=list)


@dataclass
class _Result:
    hits: list = field(default_factory=list)
    graph: object | None = None
    route_used: str = "hybrid_only"


@dataclass
class _Answer:
    llm_failed: bool = False


def test_query_sha256_is_stable():
    assert query_sha256("abc") == hashlib.sha256(b"abc").hexdigest()


def test_no_hits_means_no_answer_and_null_top_score():
    sig = extract_signals(_Result(hits=[]), None, path="search",
                          tenant="t", clearance="INTERNAL", query="q")
    assert sig.no_answer is True
    assert sig.top_score is None
    assert sig.n_snippets == 0


def test_top_score_from_first_hit():
    sig = extract_signals(_Result(hits=[_Hit(0.42), _Hit(0.1)]), None, path="search",
                          tenant="t", clearance="INTERNAL", query="q")
    assert sig.top_score == 0.42
    assert sig.n_snippets == 2
    assert sig.no_answer is False


def test_graph_requested_and_empty_graph():
    # route가 graph인데 edge가 0 → graph-empty 신호
    sig = extract_signals(_Result(hits=[_Hit(0.5)], graph=None, route_used="hybrid_then_graph"),
                          None, path="search", tenant="t", clearance="INTERNAL", query="q")
    assert sig.graph_requested is True
    assert sig.n_graph_edges == 0


def test_graph_edges_counted():
    g = _Graph(edges=[1, 2], observed_edges=[3])
    sig = extract_signals(_Result(hits=[_Hit(0.5)], graph=g, route_used="graph_then_hybrid"),
                          None, path="search", tenant="t", clearance="INTERNAL", query="q")
    assert sig.n_graph_edges == 3


def test_llm_failed_only_when_answer_present():
    assert extract_signals(_Result(hits=[_Hit(0.5)]), None, path="search",
                           tenant="t", clearance="INTERNAL", query="q").llm_failed is False
    assert extract_signals(_Result(hits=[_Hit(0.5)]), _Answer(llm_failed=True), path="search_answer",
                           tenant="t", clearance="INTERNAL", query="q").llm_failed is True


def test_scalars_pass_through_and_query_is_hashed():
    secret = "주민번호 901201-1234567"
    sig = extract_signals(_Result(hits=[_Hit(0.5)]), None, path="cli",
                          tenant="t", clearance="INTERNAL", query=secret,
                          n_entities=3, latency_ms=180)
    assert sig.n_entities == 3
    assert sig.latency_ms == 180
    assert sig.query_sha256 == hashlib.sha256(secret.encode("utf-8")).hexdigest()
    assert sig.query_len == len(secret)
    # 원문은 dataclass 어디에도 없음
    assert secret not in json.dumps(sig.__dict__, ensure_ascii=False)


async def test_record_search_without_pool_is_structlog_only(monkeypatch):
    """풀 없으면 structlog만 — DB 연결 시도 없음, 무예외."""
    from nexus import db
    monkeypatch.setattr(db, "has_pool", lambda: False)
    called = {"execute": False}

    async def _fail_execute(*a, **k):
        called["execute"] = True
        raise AssertionError("execute는 호출되면 안 됨")

    monkeypatch.setattr(db, "execute", _fail_execute)

    sig = extract_signals(_Result(hits=[_Hit(0.5)]), None, path="search",
                          tenant="t", clearance="INTERNAL", query="비밀 hunter2", n_entities=1)
    with capture_logs() as logs:
        await record_search(sig, await_persist=True)
    rec = [r for r in logs if r.get("event") == SIGNAL_EVENT][0]
    assert rec["path"] == "search"
    assert rec["n_snippets"] == 1
    assert "hunter2" not in json.dumps(rec, ensure_ascii=False)
    assert called["execute"] is False


async def test_record_search_swallows_persist_error(monkeypatch):
    """풀이 있어도 INSERT 실패는 삼키고 요청 경로를 깨지 않는다."""
    from nexus import db
    monkeypatch.setattr(db, "has_pool", lambda: True)

    async def _boom(*a, **k):
        raise RuntimeError("db down")

    monkeypatch.setattr(db, "execute", _boom)

    sig = extract_signals(_Result(hits=[]), None, path="search",
                          tenant="t", clearance="INTERNAL", query="q")
    # 예외가 전파되지 않아야 한다
    await record_search(sig, await_persist=True)
