"""Password hashing (argon2) + opaque session tokens. No secrets are logged."""

from __future__ import annotations

import secrets

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

_ph = PasswordHasher()


def hash_password(plain: str) -> str:
    """argon2 hash (random per-hash salt built in)."""
    return _ph.hash(plain)


def verify_password(hash_: str, plain: str) -> bool:
    """Constant-time verify. False on mismatch OR malformed hash; never raises.

    Catches argon2's VerificationError base (covers VerifyMismatchError) and
    InvalidHashError. Does NOT catch bare Exception — real bugs must surface.
    """
    try:
        return _ph.verify(hash_, plain)
    except (VerificationError, InvalidHashError):
        return False


def new_session_token() -> str:
    """256-bit opaque session token."""
    return secrets.token_urlsafe(32)


# A valid argon2 hash of a random secret, used to spend a constant-time verify on
# the unknown-email login path so timing doesn't reveal which emails exist.
DUMMY_HASH = _ph.hash(secrets.token_urlsafe(16))
