"""임베딩 세대 분포 판정 — SPEC-nexus-embed-generation-drift §5 (순수).

embed_generation_report: (embed_model, count) 분포에서 mixed(>1 세대) 감지 + 결정론 정렬.
"""

from __future__ import annotations

from nexus.index.embed_health import embed_generation_report


def test_single_generation_not_mixed():
    r = embed_generation_report([("nomic-embed-text", 100)])
    assert r["mixed"] is False
    assert r["dominant"] == "nomic-embed-text"
    assert r["distinct"] == 1
    assert r["total"] == 100
    assert r["generations"] == [{"model": "nomic-embed-text", "count": 100}]


def test_two_generations_mixed_sorted_desc():
    r = embed_generation_report([("kure-v1", 30), ("nomic-embed-text", 100)])
    assert r["mixed"] is True
    assert r["distinct"] == 2
    assert r["total"] == 130
    assert r["dominant"] == "nomic-embed-text"           # count 큰 쪽
    assert r["generations"][0] == {"model": "nomic-embed-text", "count": 100}
    assert r["generations"][1] == {"model": "kure-v1", "count": 30}


def test_count_tie_breaks_by_model_asc_deterministic():
    r = embed_generation_report([("b-model", 50), ("a-model", 50)])
    assert r["dominant"] == "a-model"                    # tie → model asc
    assert [g["model"] for g in r["generations"]] == ["a-model", "b-model"]


def test_empty_is_zero_false_none():
    r = embed_generation_report([])
    assert r == {"generations": [], "distinct": 0, "total": 0, "mixed": False, "dominant": None}
