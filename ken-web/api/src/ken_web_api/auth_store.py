"""AuthStore — the seam for users + sessions. A Protocol with a Postgres impl and
an in-memory Fake so the bulk of auth tests run without a database.

Timestamps are offset-aware ISO-8601 strings (now_iso() convention). The Fake
compares expiry by PARSING datetimes (never lexicographically).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from ken.schedule import _parse_ts


@dataclass(frozen=True)
class User:
    id: int
    email: str


class AuthStore(Protocol):
    def get_user_by_email(self, email: str) -> tuple[User, str] | None: ...
    def create_user(self, email: str, password_hash: str) -> User: ...
    def create_session(self, user_id: int, token: str, expires_at: str) -> None: ...
    def user_for_session(self, token: str, *, now: str) -> User | None: ...
    def delete_session(self, token: str) -> None: ...


def _norm(email: str) -> str:
    return email.strip().lower()


class FakeAuthStore:
    """In-memory AuthStore for tests."""

    def __init__(self) -> None:
        self._users: dict[str, tuple[User, str]] = {}   # email -> (User, hash)
        self._by_id: dict[int, User] = {}
        self._sessions: dict[str, tuple[int, str]] = {}  # token -> (user_id, expires_at)
        self._seq = 0

    def get_user_by_email(self, email: str) -> tuple[User, str] | None:
        return self._users.get(_norm(email))

    def create_user(self, email: str, password_hash: str) -> User:
        e = _norm(email)
        if e in self._users:
            raise ValueError(f"email already exists: {e}")
        self._seq += 1
        u = User(id=self._seq, email=e)
        self._users[e] = (u, password_hash)
        self._by_id[u.id] = u
        return u

    def create_session(self, user_id: int, token: str, expires_at: str) -> None:
        self._sessions[token] = (user_id, expires_at)

    def user_for_session(self, token: str, *, now: str) -> User | None:
        row = self._sessions.get(token)
        if row is None:
            return None
        user_id, expires_at = row
        if _parse_ts(now) >= _parse_ts(expires_at):
            return None
        return self._by_id.get(user_id)

    def delete_session(self, token: str) -> None:
        self._sessions.pop(token, None)
