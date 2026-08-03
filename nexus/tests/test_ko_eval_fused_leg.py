"""평가용 융합 다리 — **프로덕션 RRF 를 그대로 부른다**
(SPEC-nexus-korean-embedding-comparison §8 Unit 2, §6).

평가용으로 RRF 를 다시 구현하면 fused 숫자가 사용자가 겪는 것과 다른 뜻이 된다. 그러면 "벡터
다리는 이겼는데 융합에서 지워졌다" 같은 판정이 프로덕션에 대해 아무 말도 못 하게 된다.
그래서 재구현이 아니라 **호출**이어야 하고, 그 사실을 구조로 못박는다.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from scripts import ko_eval_harness
from scripts.ko_eval_harness import RRF_K, run_legs


def _labels(n: int = 3) -> dict:
    return {"queries": [
        {"id": f"q{i}", "query": f"질의 {i}", "answerable": True, "gold": [f"d{i}.md"]}
        for i in range(n)
    ] + [{"id": "u1", "query": "답 없음", "answerable": False, "gold": []}]}


def test_the_harness_calls_the_production_fusion_rather_than_its_own():
    """`_rrf_fusion` 호출이 사라지면 누군가 평가용 RRF 를 새로 짰다는 뜻이다."""
    src = Path(ko_eval_harness.__file__).read_text(encoding="utf-8")
    tree = ast.parse(src)
    calls = [n for n in ast.walk(tree)
             if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
             and n.func.attr == "_rrf_fusion"]
    assert calls, "평가 하니스가 프로덕션 RRF 를 부르지 않는다 — 재구현했는지 확인하라"
    assert "def _rrf_fusion" not in src, "하니스가 자체 RRF 를 정의했다 (재구현 금지)"


def test_the_fusion_parameter_matches_production_config():
    """`config.yaml search.rrf_k` 와 다른 k 로 융합하면 프로덕션과 다른 것을 재게 된다."""
    import yaml

    cfg = yaml.safe_load(
        (Path(ko_eval_harness.__file__).resolve().parents[1] / "config.yaml").read_text(
            encoding="utf-8"))
    assert RRF_K == cfg["search"]["rrf_k"]


@pytest.mark.asyncio
async def test_fusion_promotes_the_document_both_legs_agree_on(monkeypatch):
    """두 다리가 각각 2위로 꼽은 문서가, 어느 한 다리의 1위보다 위로 올라와야 융합이다.

    RRF 점수는 순위의 역수 합이므로 `2/(k+3)` > `1/(k+2)` — 양쪽이 동의한 문서가 이긴다.
    이 단언이 깨지면 융합이 실제로는 한 다리를 그대로 흘려보내고 있다는 뜻이다.
    """
    from nexus.search import hybrid

    chunk_doc = {"ck0": "kw_only.md", "shared": "both.md", "cv0": "vec_only.md"}

    async def fake_bm25(query, tenant, clearance, top_k):
        return [("ck0", 1), ("shared", 2)]

    async def fake_vector(query):
        return [("cv0", 1), ("shared", 2)]

    monkeypatch.setattr(hybrid, "_bm25_search", fake_bm25)
    labels = {"queries": [{"id": "q0", "query": "질의", "answerable": True,
                           "gold": ["both.md"]}]}
    legs = await run_legs(labels, "t", chunk_doc, vector_search=fake_vector)

    assert set(legs) == {"keyword", "vector", "fused"}
    assert legs["fused"].scores[0].rr == 1.0, (
        "양쪽 다리가 동의한 문서가 융합 1위가 아니다 — 융합이 한 다리를 흘려보내고 있다")
    assert legs["keyword"].scores[0].rr == 0.5      # 키워드 단독으로는 2위
    assert legs["vector"].scores[0].rr == 0.5       # 벡터 단독으로도 2위


@pytest.mark.asyncio
async def test_without_a_vector_leg_only_keyword_runs(monkeypatch):
    """벡터 팔이 없으면 융합도 없다 — 빈 벡터 다리와 융합하면 키워드를 융합이라 부르게 된다."""
    from nexus.search import hybrid

    async def fake_bm25(query, tenant, clearance, top_k):
        return [("ck0", 1)]

    monkeypatch.setattr(hybrid, "_bm25_search", fake_bm25)
    legs = await run_legs(_labels(2), "t", {"ck0": "d0.md"}, vector_search=None)
    assert set(legs) == {"keyword"}


@pytest.mark.asyncio
async def test_unanswerable_queries_stay_out_of_every_leg(monkeypatch):
    """분모는 답변가능 질의뿐 — 융합 다리도 예외가 아니다 (§4.3)."""
    from nexus.search import hybrid

    async def fake_bm25(query, tenant, clearance, top_k):
        return [("ck0", 1)]

    async def fake_vector(query):
        return [("ck0", 1)]

    monkeypatch.setattr(hybrid, "_bm25_search", fake_bm25)
    legs = await run_legs(_labels(3), "t", {"ck0": "d0.md"}, vector_search=fake_vector)
    for leg in legs.values():
        assert leg.n == 3, f"{leg.leg}: 답변불가 질의가 분모에 들어갔다"
