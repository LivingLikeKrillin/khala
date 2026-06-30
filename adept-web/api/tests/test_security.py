from khala.adept_web.security import (
    DUMMY_HASH,
    hash_password,
    new_session_token,
    verify_password,
)


def test_hash_then_verify_roundtrip():
    h = hash_password("correct horse")
    assert h != "correct horse"  # not plaintext
    assert verify_password(h, "correct horse") is True
    assert verify_password(h, "wrong") is False


def test_verify_on_malformed_hash_returns_false_not_raises():
    assert verify_password("not-a-real-argon2-hash", "anything") is False


def test_dummy_hash_is_usable_for_constant_time_path():
    # DUMMY_HASH must be a valid argon2 hash so the unknown-email path can spend
    # a real verify; it should never match a real password by luck.
    assert verify_password(DUMMY_HASH, "") is False
    assert verify_password(DUMMY_HASH, "x") is False


def test_session_token_is_long_and_unique():
    a, b = new_session_token(), new_session_token()
    assert a != b and len(a) >= 43


def test_hash_password_uses_a_fresh_salt_each_call():
    # argon2id embeds a random salt, so the same password hashes differently each time.
    assert hash_password("same-password") != hash_password("same-password")
