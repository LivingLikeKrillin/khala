import pytest

from khala.adept_web.admin import add_user_to_store, create_tenant_in_store
from khala.adept_web.auth_store import FakeAuthStore, User
from khala.adept_web.security import verify_password


def test_add_user_stores_verifiable_hash():
    s = FakeAuthStore()
    # "default" tenant is pre-seeded in FakeAuthStore
    result = add_user_to_store(s, "Alice@X.com", "password1", tenant_slug="default")
    assert isinstance(result, User)
    got = s.get_user_by_email("alice@x.com")
    assert got is not None
    assert verify_password(got[1], "password1") is True
    assert verify_password(got[1], "wrong") is False


def test_add_user_rejects_weak_password():
    s = FakeAuthStore()
    with pytest.raises(ValueError):
        add_user_to_store(s, "a@x.com", "short", tenant_slug="default")  # < 8 chars


def test_add_user_duplicate_email_errors():
    s = FakeAuthStore()
    add_user_to_store(s, "a@x.com", "password1", tenant_slug="default")
    with pytest.raises(Exception):
        add_user_to_store(s, "A@x.com", "password2", tenant_slug="default")


def test_add_user_to_store_assigns_tenant():
    s = FakeAuthStore()
    s.create_tenant("acme", "Acme")
    add_user_to_store(s, "a@x.com", "password1", tenant_slug="acme")
    got = s.get_user_by_email("a@x.com")
    assert got is not None and got[0].tenant_slug == "acme"


def test_create_tenant_to_store():
    s = FakeAuthStore()
    create_tenant_in_store(s, "acme", "Acme")
    # creating a user there now works
    add_user_to_store(s, "a@x.com", "password1", tenant_slug="acme")
    assert s.get_user_by_email("a@x.com") is not None


def test_create_tenant_to_store_duplicate_raises():
    s = FakeAuthStore()
    create_tenant_in_store(s, "acme", "Acme")
    with pytest.raises(Exception):
        create_tenant_in_store(s, "acme", "Acme2")
