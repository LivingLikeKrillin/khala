import pytest

from ken.vouch import is_fresh, record_vouch, load_vouches
from ken.models import Vouch


def mk(h="sha256:cur", ts="2026-06-23T00:00:00Z", passed=True):
    return Vouch("a1", "kr", h, 0.9, passed, 5, ts)


# --- is_fresh (pure) ---


def test_fresh_when_hash_matches_and_within_ttl():
    assert is_fresh(mk(), current_hash="sha256:cur", now="2026-06-23T00:10:00Z", ttl_days=90)


def test_stale_when_hash_differs():
    assert not is_fresh(mk(), current_hash="sha256:NEW", now="2026-06-23T00:10:00Z", ttl_days=90)


def test_stale_when_ttl_lapsed():
    assert not is_fresh(
        mk(ts="2026-01-01T00:00:00Z"),
        current_hash="sha256:cur",
        now="2026-06-23T00:00:00Z",
        ttl_days=90,
    )


def test_stale_when_not_passed():
    assert not is_fresh(
        mk(passed=False),
        current_hash="sha256:cur",
        now="2026-06-23T00:00:00Z",
        ttl_days=90,
    )


# --- persistence (fail-loud JSONL ledger) ---


def test_record_then_load_roundtrip(tmp_path):
    p = tmp_path / "ledger.jsonl"
    v = mk()
    record_vouch(v, ledger_path=p)
    assert load_vouches(p) == [v]


def test_record_fails_loud_on_unwritable_path(tmp_path):
    bad = tmp_path / "nope" / "ledger.jsonl"  # parent dir missing
    with pytest.raises(OSError):
        record_vouch(mk(), ledger_path=bad, make_parents=False)


def test_load_missing_ledger_returns_empty(tmp_path):
    assert load_vouches(tmp_path / "absent.jsonl") == []
