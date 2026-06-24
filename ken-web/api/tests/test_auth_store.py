import pytest

from ken_web_api.auth_store import FakeAuthStore, User


def _ttl(now_iso: str, days: int) -> str:
    from datetime import timedelta

    from ken.schedule import _parse_ts

    return (_parse_ts(now_iso) + timedelta(days=days)).isoformat()


def test_create_user_and_lookup():
    s = FakeAuthStore()
    u = s.create_user("Alice@X.com", "hash1")
    assert isinstance(u, User) and u.email == "alice@x.com"  # normalized lower
    got = s.get_user_by_email("alice@x.com")
    assert got is not None and got[0].id == u.id and got[1] == "hash1"
    assert s.get_user_by_email("missing@x.com") is None


def test_duplicate_email_raises():
    s = FakeAuthStore()
    s.create_user("a@x.com", "h")
    with pytest.raises(Exception):
        s.create_user("A@x.com", "h2")  # case-insensitive duplicate


def test_session_lifecycle_and_expiry_boundary():
    s = FakeAuthStore()
    u = s.create_user("a@x.com", "h")
    now = "2026-06-24T00:00:00+00:00"
    exp = _ttl(now, 1)  # expires 2026-06-25T00:00:00+00:00
    s.create_session(u.id, "tok", exp)
    # valid strictly before expiry
    assert s.user_for_session("tok", now="2026-06-24T23:59:59.999999+00:00").email == "a@x.com"
    # rejected at/after expiry (parsed compare, not lexicographic)
    assert s.user_for_session("tok", now="2026-06-25T00:00:00+00:00") is None
    assert s.user_for_session("nope", now=now) is None


def test_delete_session():
    s = FakeAuthStore()
    u = s.create_user("a@x.com", "h")
    s.create_session(u.id, "tok", "2099-01-01T00:00:00+00:00")
    s.delete_session("tok")
    assert s.user_for_session("tok", now="2026-06-24T00:00:00+00:00") is None
    s.delete_session("already-gone")  # idempotent, no raise
