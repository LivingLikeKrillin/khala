"""근거 신선도 판정 — SPEC-nexus-answer-staleness-warning §5 (순수).

staleness: updated_at(적재시각) 나이를 doc_type 별 TTL 과 대조. 결정론·무예외.
미상 나이·null/음수 TTL 은 절대 stale 아님(무고 금지). supersession 과 직교.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from nexus.documents.staleness import annotate_staleness, staleness

NOW = datetime(2026, 7, 14, tzinfo=timezone.utc)
TTL = {"ADR": 365, "RUNBOOK": 90, "default": 365}


def _dt(days_ago: int) -> datetime:
    return NOW - timedelta(days=days_ago)


def test_fresh_not_stale():
    assert staleness(_dt(30), "RUNBOOK", NOW, TTL) == {
        "age_days": 30, "ttl_days": 90, "stale": False}


def test_aged_past_ttl_is_stale():
    r = staleness(_dt(120), "RUNBOOK", NOW, TTL)
    assert r["stale"] is True and r["age_days"] == 120 and r["ttl_days"] == 90


def test_unknown_type_uses_default():
    r = staleness(_dt(400), "wiki", NOW, TTL)      # 미분류 타입 → default 365
    assert r["ttl_days"] == 365 and r["stale"] is True


def test_none_doc_type_uses_default():
    assert staleness(_dt(10), None, NOW, TTL)["ttl_days"] == 365


def test_case_insensitive_type():
    assert staleness(_dt(10), "adr", NOW, TTL)["ttl_days"] == 365


def test_null_ttl_never_stale():
    r = staleness(_dt(9999), "NOTE", NOW, {"NOTE": None, "default": 365})
    assert r["ttl_days"] is None and r["stale"] is False


def test_negative_or_zero_ttl_treated_as_no_ttl():
    assert staleness(_dt(400), "BAD", NOW, {"BAD": -5, "default": 365})["stale"] is False
    assert staleness(_dt(400), "Z", NOW, {"Z": 0, "default": 365})["stale"] is False


def test_none_updated_at_unknown_not_stale():
    assert staleness(None, "RUNBOOK", NOW, TTL) == {
        "age_days": None, "ttl_days": 90, "stale": False}


def test_future_updated_at_age_zero():
    r = staleness(NOW + timedelta(days=5), "RUNBOOK", NOW, TTL)
    assert r["age_days"] == 0 and r["stale"] is False


def test_naive_datetime_coerced_utc_no_raise():
    naive = (NOW - timedelta(days=120)).replace(tzinfo=None)
    assert staleness(naive, "RUNBOOK", NOW, TTL)["stale"] is True   # 예외 없이 판정


def test_annotate_adds_per_snippet_and_counts():
    snips = [
        {"doc_type": "RUNBOOK", "updated_at": _dt(120)},   # stale
        {"doc_type": "ADR", "updated_at": _dt(30)},        # fresh
        {"doc_type": "RUNBOOK", "updated_at": None},       # 미상 → not stale
    ]
    annotated, n = annotate_staleness(snips, NOW, TTL)
    assert n == 1
    assert annotated[0]["staleness"]["stale"] is True
    assert annotated[1]["staleness"]["stale"] is False
    assert annotated[2]["staleness"]["age_days"] is None


def test_annotate_empty():
    assert annotate_staleness([], NOW, TTL) == ([], 0)
