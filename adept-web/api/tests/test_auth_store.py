import os

import pytest

from khala.adept_web.auth_store import FakeAuthStore, User


def _ttl(now_iso: str, days: int) -> str:
    from datetime import timedelta

    from khala.adept.schedule import _parse_ts

    return (_parse_ts(now_iso) + timedelta(days=days)).isoformat()


def test_create_user_and_lookup():
    s = FakeAuthStore()
    u = s.create_user("Alice@X.com", "hash1")
    assert isinstance(u, User) and u.email == "alice@x.com"  # normalized lower
    got = s.get_user_by_email("alice@x.com")
    assert got is not None and got[0].id == u.id and got[1] == "hash1"
    assert s.get_user_by_email("missing@x.com") is None
    assert s.get_user_by_email("Alice@X.com") is not None  # lookup normalizes too


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
    # Parsed-not-lexicographic proof: +01:00 instant equals UTC midnight. A lexicographic
    # compare would wrongly read this as still-valid ("...T00:00:00+00:00" < "...T01:00:00+01:00").
    s.create_session(u.id, "tz", "2026-06-25T01:00:00+01:00")  # == 2026-06-25T00:00:00Z
    assert s.user_for_session("tz", now="2026-06-25T00:00:00+00:00") is None  # expired at the same instant


def test_delete_session():
    s = FakeAuthStore()
    u = s.create_user("a@x.com", "h")
    s.create_session(u.id, "tok", "2099-01-01T00:00:00+00:00")
    s.delete_session("tok")
    assert s.user_for_session("tok", now="2026-06-24T00:00:00+00:00") is None
    s.delete_session("already-gone")  # idempotent, no raise


_PG_DSN = os.getenv("ADEPT_TEST_DATABASE_URL")
pg_only = pytest.mark.skipif(_PG_DSN is None, reason="ADEPT_TEST_DATABASE_URL unset")


@pg_only
def test_postgres_auth_store_roundtrip():
    import psycopg

    from khala.adept_web.auth_store import PostgresAuthStore

    with psycopg.connect(_PG_DSN) as c, c.cursor() as cur:
        cur.execute("TRUNCATE users, sessions CASCADE")
        cur.execute("INSERT INTO tenants (slug, name) VALUES ('default', 'Default') ON CONFLICT DO NOTHING")
    s = PostgresAuthStore(_PG_DSN)
    u = s.create_user("Alice@X.com", "hash1")
    assert u.email == "alice@x.com"
    with pytest.raises(Exception):
        s.create_user("alice@x.com", "h2")  # duplicate
    got = s.get_user_by_email("alice@x.com")
    assert got is not None and got[0].id == u.id and got[1] == "hash1"
    s.create_session(u.id, "tok", "2099-01-01T00:00:00+00:00")
    assert s.user_for_session("tok", now="2026-06-24T00:00:00+00:00").email == "alice@x.com"
    s.create_session(u.id, "old", "2000-01-01T00:00:00+00:00")
    assert s.user_for_session("old", now="2026-06-24T00:00:00+00:00") is None  # expired
    s.delete_session("tok")
    assert s.user_for_session("tok", now="2026-06-24T00:00:00+00:00") is None


def test_create_user_carries_tenant_slug():
    s = FakeAuthStore()
    s.create_tenant("acme", "Acme")
    u = s.create_user("a@x.com", "h", tenant_slug="acme")
    assert u.tenant_slug == "acme"
    got = s.get_user_by_email("a@x.com")
    assert got is not None and got[0].tenant_slug == "acme"


def test_user_for_session_returns_tenant_slug():
    s = FakeAuthStore()
    s.create_tenant("acme", "Acme")
    u = s.create_user("a@x.com", "h", tenant_slug="acme")
    s.create_session(u.id, "tok", "2099-01-01T00:00:00+00:00")
    got = s.user_for_session("tok", now="2026-06-24T00:00:00+00:00")
    assert got is not None and got.tenant_slug == "acme"


def test_create_tenant_duplicate_raises():
    s = FakeAuthStore()
    s.create_tenant("acme", "Acme")
    with pytest.raises(Exception):
        s.create_tenant("acme", "Acme2")


def test_create_user_defaults_tenant_to_default():
    s = FakeAuthStore()  # back-compat: 2-arg create_user lands in 'default'
    u = s.create_user("a@x.com", "h")
    assert u.tenant_slug == "default"


def test_create_user_unknown_tenant_raises():
    s = FakeAuthStore()
    with pytest.raises(Exception):
        s.create_user("a@x.com", "h", tenant_slug="ghost")


@pg_only
def test_postgres_auth_store_tenant_slug_roundtrip():
    import psycopg

    from khala.adept_web.auth_store import PostgresAuthStore

    with psycopg.connect(_PG_DSN) as c, c.cursor() as cur:
        cur.execute("TRUNCATE users, sessions CASCADE")
        cur.execute("INSERT INTO tenants (slug, name) VALUES ('acme', 'Acme') ON CONFLICT DO NOTHING")
    s = PostgresAuthStore(_PG_DSN)
    s.create_tenant("acme2", "Acme2")
    u = s.create_user("b@x.com", "hash1", tenant_slug="acme2")
    assert u.tenant_slug == "acme2"
    s.create_session(u.id, "tok2", "2099-01-01T00:00:00+00:00")
    got = s.user_for_session("tok2", now="2026-06-24T00:00:00+00:00")
    assert got is not None and got.tenant_slug == "acme2"
