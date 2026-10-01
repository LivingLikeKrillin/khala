"""죽은 경로가 **기록에 남고**, 질의 임베딩이 **기다릴 만큼 기다린다**.

⛔ **왜 생겼나 (2026-10-01).** 소비자의 측정 첫 호출에서 벡터 경로가 `ReadTimeout` 으로 죽었다.
응답은 `degraded: ["vector"]` 를 실었지만 소비자 기록기가 그 칸을 버렸고, 이쪽 `search_log` 에는
**그 칸이 없었다** — 앱 로그를 읽고서야 알았다. 기록으로는 `top_distance IS NULL` 로 짐작만 할 수
있었고, 그것은 첫 채널만 보며 벡터를 안 쓰는 경로(`keyword_only`)와 섞인다.

원인은 사이드카 질의 한도 10초였다. 검색 한 번은 켜진 채널마다 벡터 경로를 동시에 띄우므로
식별자 채널을 켜면 사이드카가 요청 둘을 받고, 긴 질의에서는 따뜻해도 9.1초가 걸렸다(서른한 건
가운데값 6.6초). 쉰 뒤 첫 호출은 10초를 넘겼다 — 하루 사이 두 번.
"""

from __future__ import annotations

import dataclasses
import re

import pytest

from nexus.search import signals as S
from nexus.search.hybrid import SearchResult


def _extract(result):
    return S.extract_signals(result, path="search_answer", tenant="t", clearance="INTERNAL",
                             query="질의")


# ── 기록: 응답이 실은 값을 그대로 옮긴다 ───────────────────────────────────────

def test_a_dead_vector_leg_is_carried_into_the_signal():
    assert _extract(SearchResult(degraded=["vector"])).degraded == ("vector",)


def test_nothing_died_is_recorded_as_an_empty_list_not_as_unknown():
    """⛔ 빈 튜플과 None 은 다른 사실이다 — 「기록했고 죽은 것 없음」과 「기록 안 함」."""
    assert _extract(SearchResult()).degraded == ()


def test_a_double_without_the_field_is_unknown_not_healthy():
    """칸이 없는 더블을 「죽은 것 없음」으로 적으면, 모르는 것을 안다고 적는 것이다."""
    class _Bare:
        hits: list = []
        graph = None
        route_used = "hybrid_only"

    assert _extract(_Bare()).degraded is None


def _columns_and_values(sql: str) -> tuple[list[str], list[str]]:
    cols = re.search(r"INSERT INTO search_log \((.*?)\)\s*VALUES", sql, re.S).group(1)
    vals = re.search(r"VALUES\s*\((.*)\)\s*RETURNING", sql, re.S).group(1)
    return ([c.strip() for c in cols.split(",")], [v.strip() for v in vals.split(",")])


async def _bound(monkeypatch, sig) -> tuple[dict[str, str], tuple]:
    captured: dict = {}

    async def fake_fetch_val(sql, *args):
        captured["sql"], captured["args"] = sql, args
        return 1

    monkeypatch.setattr(S.db, "fetch_val", fake_fetch_val)
    await S._insert(sig, None, None, None)
    cols, vals = _columns_and_values(captured["sql"])
    assert len(cols) == len(vals), "INSERT 의 칸 수와 값 수가 다르다"
    return dict(zip(cols, vals)), captured["args"]


@pytest.mark.asyncio
async def test_every_placeholder_of_the_insert_is_bound_exactly_once(monkeypatch):
    """⚠ 이 INSERT 는 자리 번호가 칸 순서를 안 따른다(`read_scope` 가 `$36`). 칸을 더하는
    사람이 번호를 하나 잘못 적어도 다른 칸에 조용히 들어간다 — 번호와 인자 수를 맞춰 본다."""
    bound, args = await _bound(monkeypatch, _extract(SearchResult()))
    numbers = sorted(int(v[1:]) for v in bound.values() if v.startswith("$"))
    assert numbers == list(range(1, len(args) + 1))


@pytest.mark.asyncio
async def test_the_insert_writes_the_dead_legs_to_their_own_column(monkeypatch):
    bound, args = await _bound(monkeypatch, _extract(SearchResult(degraded=["vector"])))
    assert "degraded" in bound, "search_log INSERT 에 degraded 칸이 없다"
    assert args[int(bound["degraded"][1:]) - 1] == ["vector"]


@pytest.mark.asyncio
async def test_unknown_goes_to_the_column_as_null(monkeypatch):
    sig = dataclasses.replace(_extract(SearchResult()), degraded=None)
    bound, args = await _bound(monkeypatch, sig)
    assert args[int(bound["degraded"][1:]) - 1] is None


# ── 예산: 사이드카 질의 한도 ─────────────────────────────────────────────────

def test_the_sidecar_query_budget_is_twenty_seconds(monkeypatch):
    """10초는 따뜻한 긴 질의(9.1초)에 여유가 1초 안팎이었고 첫 호출은 넘겼다(2026-10-01)."""
    monkeypatch.delenv("EMBEDDING_TIMEOUT", raising=False)
    from nexus.providers.embedding import EmbeddingService

    svc = EmbeddingService(model="KURE-v1", dimensions=1024, backend="sidecar")
    assert svc.timeout == 20.0


def test_the_budget_is_still_set_by_the_environment(monkeypatch):
    monkeypatch.setenv("EMBEDDING_TIMEOUT", "7")
    from nexus.providers.embedding import EmbeddingService

    svc = EmbeddingService(model="KURE-v1", dimensions=1024, backend="sidecar")
    assert svc.timeout == 7.0


def test_the_ollama_budget_and_the_batch_budget_are_untouched(monkeypatch):
    monkeypatch.delenv("EMBEDDING_TIMEOUT", raising=False)
    monkeypatch.delenv("EMBEDDING_BATCH_TIMEOUT", raising=False)
    from nexus.providers.embedding import EmbeddingService

    svc = EmbeddingService(backend="ollama")
    assert (svc.timeout, svc.batch_timeout) == (60.0, 600.0)
