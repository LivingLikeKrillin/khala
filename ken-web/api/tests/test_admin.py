import pytest

from ken_web_api.admin import add_user_to_store
from ken_web_api.auth_store import FakeAuthStore, User
from ken_web_api.security import verify_password


def test_add_user_stores_verifiable_hash():
    s = FakeAuthStore()
    result = add_user_to_store(s, "Alice@X.com", "password1")
    assert isinstance(result, User)
    got = s.get_user_by_email("alice@x.com")
    assert got is not None
    assert verify_password(got[1], "password1") is True
    assert verify_password(got[1], "wrong") is False


def test_add_user_rejects_weak_password():
    s = FakeAuthStore()
    with pytest.raises(ValueError):
        add_user_to_store(s, "a@x.com", "short")  # < 8 chars


def test_add_user_duplicate_email_errors():
    s = FakeAuthStore()
    add_user_to_store(s, "a@x.com", "password1")
    with pytest.raises(Exception):
        add_user_to_store(s, "A@x.com", "password2")
