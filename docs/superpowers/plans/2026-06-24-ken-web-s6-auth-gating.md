# ken-web S6 Authentication Gating Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Gate ken-web behind email+password login (Postgres-only), so only CLI-seeded users reach the app and the attempt ledger records the logged-in user as `person`.

**Architecture:** Additive. `KEN_AUTH=1` enables auth (requires Postgres; fail-loud at startup otherwise). argon2 password hashing; opaque session tokens in a Postgres `sessions` table; httpOnly SameSite=Lax cookie. An `AuthStore` Protocol with a `FakeAuthStore` keeps the bulk of tests DB-free. `person` becomes server-derived from the session. The `ken` engine, the file backend, and the `ken` CLI are untouched; auth-OFF preserves today's open behavior.

**Tech Stack:** Python 3.13 (FastAPI, psycopg3, argon2-cffi), React + Vite + TS, pytest + vitest.

**Spec:** `docs/superpowers/specs/2026-06-24-ken-web-s6-auth-gating-design.md`

---

## File Structure

- `ken/db/init.sql` — **modify**: append `users` + `sessions` tables.
- `ken/tests/test_store_contract.py` — **modify**: TRUNCATE adds `users, sessions`.
- `ken-web/api/pyproject.toml` — **modify**: add `argon2-cffi` dep; add `ken-web-admin` console script.
- `ken-web/api/src/ken_web_api/security.py` — **create**: hash/verify/token + DUMMY_HASH.
- `ken-web/api/src/ken_web_api/auth_store.py` — **create**: `User`, `AuthStore` Protocol, `FakeAuthStore`, `PostgresAuthStore`.
- `ken-web/api/src/ken_web_api/deps.py` — **modify**: `make_auth_store`, `auth_enabled`, auth constants.
- `ken-web/api/src/ken_web_api/schemas.py` — **modify**: add `LoginReq`, `MeOut`; remove `AttemptReq.person`.
- `ken-web/api/src/ken_web_api/app.py` — **modify**: startup guard, `require_user`, `/api/auth/*`, guard data routes, server-derived person.
- `ken-web/api/src/ken_web_api/admin.py` — **create**: `add-user` CLI.
- `ken-web/api/tests/test_security.py` — **create**.
- `ken-web/api/tests/test_auth_store.py` — **create** (Fake + PG-gated).
- `ken-web/api/tests/test_auth_api.py` — **create**.
- `ken-web/api/tests/test_admin.py` — **create**.
- `ken-web/web/src/types.ts` — **modify**: add `Me`.
- `ken-web/web/src/api/client.ts` — **modify**: `getMe`/`login`/`logout` + 401 redirect.
- `ken-web/web/src/pages/Login.tsx` — **create**.
- `ken-web/web/src/components/AuthGuard.tsx` — **create**.
- `ken-web/web/src/App.tsx` — **modify**: `/login` route, wrap app in `AuthGuard`, masthead user/logout.
- `ken-web/web/src/pages/Review.tsx` — **modify**: stop sending `person`.
- `ken-web/web/tests/login.test.tsx`, `tests/auth-guard.test.tsx` — **create**.

---

## Chunk 1: schema + password security primitives

### Task 1: Schema — `users` + `sessions`

**Files:** Modify `ken/db/init.sql`, `ken/tests/test_store_contract.py`

- [ ] **Step 1: Append tables to `ken/db/init.sql`** (after the `attempts` block):

```sql

-- S6 auth (Postgres-only gating). Separate from the 3 core tables.
CREATE TABLE users (
    id            BIGSERIAL PRIMARY KEY,
    email         TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE sessions (
    token      TEXT PRIMARY KEY,
    user_id    BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    expires_at TIMESTAMPTZ NOT NULL
);
CREATE INDEX idx_sessions_user ON sessions (user_id);
```

- [ ] **Step 2: Extend the TRUNCATE reset** in `ken/tests/test_store_contract.py` (the `cur.execute("TRUNCATE artifacts, questions, attempts")` line) to:

```python
        cur.execute("TRUNCATE artifacts, questions, attempts, users, sessions")
```

- [ ] **Step 3: Commit**

```bash
git add ken/db/init.sql ken/tests/test_store_contract.py
git commit -m "feat(ken): add users + sessions tables (S6 auth schema)"
```

### Task 2: `security.py` — argon2 hash/verify + token

**Files:** Create `ken-web/api/src/ken_web_api/security.py`, `ken-web/api/tests/test_security.py`; modify `ken-web/api/pyproject.toml`

- [ ] **Step 1: Add the dependency.** In `ken-web/api/pyproject.toml`, change the `dependencies` line to include argon2:

```toml
dependencies = ["ken", "fastapi>=0.115", "uvicorn>=0.30", "argon2-cffi>=23.1"]
```

Then install: `pip install -e ken-web/api` (from repo root) so `argon2` imports.

- [ ] **Step 2: Write the failing test** `ken-web/api/tests/test_security.py`:

```python
from ken_web_api.security import (
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
    assert a != b and len(a) >= 32
```

- [ ] **Step 3: Run to verify it fails**

Run: `python -m pytest ken-web/api/tests/test_security.py -v`
Expected: FAIL with `ModuleNotFoundError: ken_web_api.security`.

- [ ] **Step 4: Implement** `ken-web/api/src/ken_web_api/security.py`:

```python
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
```

- [ ] **Step 5: Run to verify it passes**

Run: `python -m pytest ken-web/api/tests/test_security.py -v`
Expected: PASS (4 tests).

- [ ] **Step 6: Commit**

```bash
git add ken-web/api/pyproject.toml ken-web/api/src/ken_web_api/security.py ken-web/api/tests/test_security.py
git commit -m "feat(ken-web): argon2 password hashing + session token (security.py)"
```

---

## Chunk 2: AuthStore (Fake + Postgres)

### Task 3: `User` + `AuthStore` Protocol + `FakeAuthStore`

**Files:** Create `ken-web/api/src/ken_web_api/auth_store.py`, `ken-web/api/tests/test_auth_store.py`

- [ ] **Step 1: Write the failing test** `ken-web/api/tests/test_auth_store.py` (Fake portion):

```python
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
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest ken-web/api/tests/test_auth_store.py -v`
Expected: FAIL with `ModuleNotFoundError: ken_web_api.auth_store`.

- [ ] **Step 3: Implement** `ken-web/api/src/ken_web_api/auth_store.py`:

```python
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
```

- [ ] **Step 4: Run to verify it passes**

Run: `python -m pytest ken-web/api/tests/test_auth_store.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add ken-web/api/src/ken_web_api/auth_store.py ken-web/api/tests/test_auth_store.py
git commit -m "feat(ken-web): AuthStore protocol + FakeAuthStore (parsed expiry)"
```

### Task 4: `PostgresAuthStore` (PG-gated test)

**Files:** Modify `ken-web/api/src/ken_web_api/auth_store.py`, `ken-web/api/tests/test_auth_store.py`

- [ ] **Step 1: Add the PG-gated test** to `ken-web/api/tests/test_auth_store.py` (mirrors `test_store_contract`'s gating; assumes `db/init.sql` applied to the test DB):

```python
import os

_PG_DSN = os.getenv("KEN_TEST_DATABASE_URL")
pg_only = pytest.mark.skipif(_PG_DSN is None, reason="KEN_TEST_DATABASE_URL unset")


@pg_only
def test_postgres_auth_store_roundtrip():
    import psycopg

    from ken_web_api.auth_store import PostgresAuthStore

    with psycopg.connect(_PG_DSN) as c, c.cursor() as cur:
        cur.execute("TRUNCATE users, sessions")
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
```

- [ ] **Step 2: Run to verify it fails** (only when a test DB is configured; otherwise it skips)

Run: `python -m pytest ken-web/api/tests/test_auth_store.py -k postgres -v`
Expected: FAIL with `ImportError: cannot import name 'PostgresAuthStore'` (or SKIP if `KEN_TEST_DATABASE_URL` unset — then rely on CI's PG job).

- [ ] **Step 3: Implement `PostgresAuthStore`** in `auth_store.py` (append; mirror `PostgresStore`'s per-request fail-loud pattern):

```python
class PostgresAuthStore:
    def __init__(self, dsn: str):
        self._dsn = dsn

    def _conn(self):
        import psycopg
        return psycopg.connect(self._dsn)

    def get_user_by_email(self, email: str) -> tuple[User, str] | None:
        with self._conn() as c, c.cursor() as cur:
            cur.execute(
                "SELECT id, email, password_hash FROM users WHERE email = %s", (_norm(email),)
            )
            row = cur.fetchone()
        if row is None:
            return None
        return User(id=row[0], email=row[1]), row[2]

    def create_user(self, email: str, password_hash: str) -> User:
        with self._conn() as c, c.cursor() as cur:
            cur.execute(
                "INSERT INTO users (email, password_hash) VALUES (%s, %s) RETURNING id, email",
                (_norm(email), password_hash),
            )
            uid, e = cur.fetchone()
        return User(id=uid, email=e)

    def create_session(self, user_id: int, token: str, expires_at: str) -> None:
        with self._conn() as c, c.cursor() as cur:
            cur.execute(
                "INSERT INTO sessions (token, user_id, expires_at) VALUES (%s, %s, %s)",
                (token, user_id, expires_at),
            )

    def user_for_session(self, token: str, *, now: str) -> User | None:
        with self._conn() as c, c.cursor() as cur:
            cur.execute(
                "SELECT u.id, u.email FROM sessions s JOIN users u ON u.id = s.user_id "
                "WHERE s.token = %s AND s.expires_at > %s",
                (token, now),
            )
            row = cur.fetchone()
        return User(id=row[0], email=row[1]) if row else None

    def delete_session(self, token: str) -> None:
        with self._conn() as c, c.cursor() as cur:
            cur.execute("DELETE FROM sessions WHERE token = %s", (token,))
```

> `create_user` duplicate-email raises `psycopg.errors.UniqueViolation` (a subclass of Exception) — the test's `pytest.raises(Exception)` covers it. The `expires_at > %s` bind sends the ISO `now` string; Postgres casts it to `timestamptz` for the comparison.

- [ ] **Step 4: Run to verify it passes** (if a test DB is configured)

Run: `python -m pytest ken-web/api/tests/test_auth_store.py -v`
Expected: PASS (Fake tests always; PG test passes when `KEN_TEST_DATABASE_URL` set, else SKIP).

- [ ] **Step 5: Commit**

```bash
git add ken-web/api/src/ken_web_api/auth_store.py ken-web/api/tests/test_auth_store.py
git commit -m "feat(ken-web): PostgresAuthStore (PG-gated contract test)"
```

---

## Chunk 3: API auth — deps, guard, endpoints, server-derived person

### Task 5: deps wiring + constants

**Files:** Modify `ken-web/api/src/ken_web_api/deps.py`

- [ ] **Step 1: Add to `deps.py`** (after the existing functions; add `from ken_web_api.auth_store import AuthStore, PostgresAuthStore` import):

```python
SESSION_COOKIE = "ken_session"
DEFAULT_PERSON = "local"           # the identity when auth is OFF
SESSION_TTL_DAYS = 14


def auth_enabled() -> bool:
    """True only for the exact env value KEN_AUTH=1 (a typo resolves to OFF)."""
    return os.getenv("KEN_AUTH") == "1"


def make_auth_store() -> AuthStore:
    """Postgres-only auth store (request-time seam; tests monkeypatch to a Fake)."""
    return PostgresAuthStore(os.environ["KEN_DATABASE_URL"])
```

- [ ] **Step 2: Commit** (no test yet — exercised via the API tests in Task 6)

```bash
git add ken-web/api/src/ken_web_api/deps.py
git commit -m "feat(ken-web): deps.auth_enabled + make_auth_store seam"
```

### Task 6: schemas + startup guard + require_user + auth endpoints + server-derived person

**Files:** Modify `ken-web/api/src/ken_web_api/schemas.py`, `app.py`; create `ken-web/api/tests/test_auth_api.py`

- [ ] **Step 1: Update schemas.** In `schemas.py`: remove `person: str` from `AttemptReq`; add:

```python
class LoginReq(BaseModel):
    email: str
    password: str


class MeOut(BaseModel):
    email: str
```

- [ ] **Step 2: Write the failing tests** `ken-web/api/tests/test_auth_api.py`:

```python
from __future__ import annotations

from fastapi.testclient import TestClient

from ken.llm import FakeLLM
from ken.schedule import _parse_ts
from ken_web_api import deps
from ken_web_api.app import app
from ken_web_api.auth_store import FakeAuthStore
from ken_web_api.security import hash_password


def _auth_client(tmp_path, monkeypatch, *, auth_store=None, responses=()):
    """Auth-ON client: file data backend (monkeypatched) + Fake auth store.
    A dummy KEN_DATABASE_URL satisfies the startup guard; make_store is patched
    to the file backend so data calls never touch Postgres."""
    monkeypatch.setenv("KEN_AUTH", "1")
    monkeypatch.setenv("KEN_DATABASE_URL", "postgresql://dummy")  # guard only
    monkeypatch.setenv("KEN_DATA_DIR", str(tmp_path))
    from ken.stores.file_store import FileStore
    store = FileStore(
        manifest=str(tmp_path / "m.yaml"),
        questions=str(tmp_path / "q.json"),
        ledger=str(tmp_path / "l.jsonl"),
    )
    monkeypatch.setattr(deps, "make_store", lambda: store)
    auth = auth_store or FakeAuthStore()
    monkeypatch.setattr(deps, "make_auth_store", lambda: auth)
    monkeypatch.setattr(deps, "make_llm", lambda: FakeLLM(responses=list(responses)))
    return TestClient(app), auth, store


def _login(c, auth, email="a@x.com", password="password1"):
    auth.create_user(email, hash_password(password))
    return c.post("/api/auth/login", json={"email": email, "password": password})


def test_login_success_sets_cookie_and_returns_email(tmp_path, monkeypatch):
    c, auth, _ = _auth_client(tmp_path, monkeypatch)
    r = _login(c, auth)
    assert r.status_code == 200 and r.json() == {"email": "a@x.com"}
    assert deps.SESSION_COOKIE in r.cookies


def test_login_wrong_password_and_unknown_email_same_generic_401(tmp_path, monkeypatch):
    c, auth, _ = _auth_client(tmp_path, monkeypatch)
    auth.create_user("a@x.com", hash_password("password1"))
    wrong = c.post("/api/auth/login", json={"email": "a@x.com", "password": "nope"})
    unknown = c.post("/api/auth/login", json={"email": "ghost@x.com", "password": "nope"})
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json()["detail"] == unknown.json()["detail"]  # identical generic message


def test_me_requires_session(tmp_path, monkeypatch):
    c, auth, _ = _auth_client(tmp_path, monkeypatch)
    assert c.get("/api/auth/me").status_code == 401
    _login(c, auth)
    assert c.get("/api/auth/me").json() == {"email": "a@x.com"}


def test_protected_endpoint_401_without_session_200_with(tmp_path, monkeypatch):
    c, auth, _ = _auth_client(tmp_path, monkeypatch)
    assert c.get("/api/coverage").status_code == 401
    _login(c, auth)
    assert c.get("/api/coverage").status_code == 200


def test_logout_clears_session(tmp_path, monkeypatch):
    c, auth, _ = _auth_client(tmp_path, monkeypatch)
    _login(c, auth)
    assert c.post("/api/auth/logout").status_code == 204
    assert c.get("/api/auth/me").status_code == 401


def test_expired_session_is_401(tmp_path, monkeypatch):
    c, auth, _ = _auth_client(tmp_path, monkeypatch)
    u = auth.create_user("a@x.com", hash_password("password1"))
    past = (_parse_ts("2000-01-01T00:00:00+00:00")).isoformat()
    auth.create_session(u.id, "tok", past)
    c.cookies.set(deps.SESSION_COOKIE, "tok")
    assert c.get("/api/auth/me").status_code == 401


def test_person_is_server_derived_from_session(tmp_path, monkeypatch):
    c, auth, store = _auth_client(
        tmp_path, monkeypatch,
        responses=["Q1?", '{"passed": true, "score": 0.9, "rationale":"ok"}'],
    )
    _login(c, auth)
    art = tmp_path / "a.md"
    art.write_text("Payment service publishes orders.\n", encoding="utf-8")
    aid = c.post("/api/artifacts", json={"path": str(art)}).json()["artifact_id"]
    qid = c.get(f"/api/artifacts/{aid}/due").json()["questions"][0]["question_id"]
    # NOTE: no "person" in the body — server derives it from the session.
    r = c.post("/api/attempts", json={"artifact_id": aid, "question_id": qid, "answer": "..."})
    assert r.status_code == 200
    assert store.load_attempts()[0].person == "a@x.com"


def test_startup_guard_fails_when_auth_on_without_db(monkeypatch):
    monkeypatch.setenv("KEN_AUTH", "1")
    monkeypatch.delenv("KEN_DATABASE_URL", raising=False)
    import pytest
    with pytest.raises(RuntimeError):
        with TestClient(app):  # entering context triggers startup (lifespan)
            pass


def test_auth_off_endpoints_open_and_person_local(tmp_path, monkeypatch):
    monkeypatch.delenv("KEN_AUTH", raising=False)
    monkeypatch.setenv("KEN_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(deps, "make_llm", lambda: FakeLLM(responses=["Q1?", '{"passed": true, "score": 0.9, "rationale":"ok"}']))
    c = TestClient(app)
    assert c.get("/api/coverage").status_code == 200       # open
    assert c.get("/api/auth/me").json() == {"email": deps.DEFAULT_PERSON}
    art = tmp_path / "a.md"; art.write_text("Payment service publishes orders.\n", encoding="utf-8")
    aid = c.post("/api/artifacts", json={"path": str(art)}).json()["artifact_id"]
    qid = c.get(f"/api/artifacts/{aid}/due").json()["questions"][0]["question_id"]
    c.post("/api/attempts", json={"artifact_id": aid, "question_id": qid, "answer": "x"})
    # person defaulted to "local" — read it back via a FileStore over the app's
    # DEFAULT KEN_DATA_DIR paths (deps defaults: ken.manifest.yaml / .questions.json
    # / .attempts.jsonl — NOT the m.yaml/q.json/l.jsonl used by the auth-ON helper).
    from ken.stores.file_store import FileStore
    store = FileStore(
        manifest=str(tmp_path / "ken.manifest.yaml"),
        questions=str(tmp_path / "ken.questions.json"),
        ledger=str(tmp_path / "ken.attempts.jsonl"),
    )
    assert store.load_attempts()[0].person == deps.DEFAULT_PERSON  # "local"
```

- [ ] **Step 3: Run to verify they fail**

Run: `python -m pytest ken-web/api/tests/test_auth_api.py -v`
Expected: FAIL (routes/guard not present; `AttemptReq` still requires person, etc.).

- [ ] **Step 4: Implement in `app.py`.** First add the new module-level imports below to the top of `app.py` (it currently imports **neither** `os` nor `logging` — both are required by the guard/login). Then add the wiring:

```python
import logging
import os
from datetime import timedelta

from fastapi import Depends, FastAPI, HTTPException, Request, Response

from ken.schedule import _parse_ts

from .schemas import (..., LoginReq, MeOut)  # add LoginReq, MeOut to the existing import block
from .security import DUMMY_HASH, new_session_token, verify_password

logger = logging.getLogger("ken_web_api")


@app.on_event("startup")
def _auth_startup_guard() -> None:
    if deps.auth_enabled() and not os.getenv("KEN_DATABASE_URL"):
        raise RuntimeError("KEN_AUTH=1 requires KEN_DATABASE_URL (Postgres)")
    logger.info("auth: %s", "ENABLED" if deps.auth_enabled() else "OFF")


def require_user(request: Request) -> str:
    """Return the person identifier (email). 401 when auth is on and no valid session."""
    if not deps.auth_enabled():
        return deps.DEFAULT_PERSON
    token = request.cookies.get(deps.SESSION_COOKIE)
    user = deps.make_auth_store().user_for_session(token, now=service.now_iso()) if token else None
    if user is None:
        raise HTTPException(status_code=401, detail="authentication required")
    return user.email


@app.post("/api/auth/login", response_model=MeOut)
def login(req: LoginReq, response: Response) -> MeOut:
    if not deps.auth_enabled():
        raise HTTPException(status_code=400, detail="auth disabled")
    store = deps.make_auth_store()
    found = store.get_user_by_email(req.email)
    # Constant-time across branches: always run one verify (DUMMY_HASH if unknown).
    ok = verify_password(found[1] if found else DUMMY_HASH, req.password)
    if not found or not ok:
        raise HTTPException(status_code=401, detail="invalid email or password")
    token = new_session_token()
    expires = (_parse_ts(service.now_iso()) + timedelta(days=deps.SESSION_TTL_DAYS)).isoformat()
    store.create_session(found[0].id, token, expires)
    response.set_cookie(
        deps.SESSION_COOKIE, token, httponly=True, samesite="lax", path="/",
        secure=os.getenv("KEN_COOKIE_SECURE") == "1",
        max_age=deps.SESSION_TTL_DAYS * 86400,
    )
    return MeOut(email=found[0].email)


@app.post("/api/auth/logout", status_code=204)
def logout(request: Request, response: Response) -> None:
    # Apply cookie-deletion to the INJECTED response (returning a new Response
    # would drop the Set-Cookie). Returning None → FastAPI sends 204 with this
    # response's headers. delete_cookie uses the same path the cookie was set with.
    token = request.cookies.get(deps.SESSION_COOKIE)
    if token:
        deps.make_auth_store().delete_session(token)
    response.delete_cookie(deps.SESSION_COOKIE, path="/")
    return None


@app.get("/api/auth/me", response_model=MeOut)
def me(request: Request) -> MeOut:
    return MeOut(email=require_user(request))
```

> **`expires` timestamp:** the plan needs `now + TTL` as an offset-aware ISO string. `service.now_iso()` returns the string; add a tiny helper `service.now_iso()` is enough if you parse it, OR compute via `from ken.schedule import _parse_ts; (_parse_ts(service.now_iso()) + timedelta(...)).isoformat()`. Use that form (no new service function): `expires = (_parse_ts(service.now_iso()) + timedelta(days=deps.SESSION_TTL_DAYS)).isoformat()` and `from ken.schedule import _parse_ts`. (Do NOT invent `service._dt_now`.)

- [ ] **Step 5: Guard the data routes + server-derive person.** For each data route decorator, add `dependencies=[Depends(require_user)]`:
  - `@app.get("/api/artifacts", ..., dependencies=[Depends(require_user)])`
  - `@app.post("/api/artifacts", ..., status_code=201, dependencies=[Depends(require_user)])`
  - `@app.get("/api/artifacts/{artifact_id}/due", ..., dependencies=[Depends(require_user)])`
  - `@app.get("/api/artifacts/{artifact_id}/detail", ..., dependencies=[Depends(require_user)])`
  - `@app.get("/api/coverage", ..., dependencies=[Depends(require_user)])`

  For `post_attempt`, derive `person` from the session instead of the body — change its signature and body:

```python
@app.post("/api/attempts", response_model=AttemptOut)
def post_attempt(req: AttemptReq, person: str = Depends(require_user)) -> AttemptOut:
    store = deps.make_store()
    try:
        result = service.grade_answer(
            req.artifact_id, req.question_id, req.answer,
            person=person,                       # server-derived, not client-supplied
            store=store, llm=deps.make_llm(), now=service.now_iso(),
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"unknown id: {exc.args[0]}") from exc
    except OSError as exc:
        raise HTTPException(status_code=500, detail="storage write failed") from exc
    return AttemptOut(passed=result.passed, score=result.score, remediation=result.remediation)
```

- [ ] **Step 6: Run to verify they pass**

Run: `python -m pytest ken-web/api/tests/test_auth_api.py ken-web/api/tests/test_api.py -v`
Expected: PASS. (Existing `test_api.py` runs auth-OFF — `KEN_AUTH` unset — so its calls stay open. If any existing test sent `person` in the attempt body, drop that key; the body no longer accepts it but FastAPI ignores unknown keys, so likely no change needed — verify.)

- [ ] **Step 7: Commit**

```bash
git add ken-web/api/src/ken_web_api/schemas.py ken-web/api/src/ken_web_api/app.py ken-web/api/tests/test_auth_api.py
git commit -m "feat(ken-web): auth endpoints + require_user guard + server-derived person"
```

---

## Chunk 4: CLI admin — `ken-web-admin add-user`

### Task 7: admin console script

**Files:** Create `ken-web-api/.../admin.py`, `ken-web/api/tests/test_admin.py`; modify `ken-web/api/pyproject.toml`

- [ ] **Step 1: Write the failing test** `ken-web/api/tests/test_admin.py` (drives the core via a Fake store + injected password, no prompt/DB):

```python
import pytest

from ken_web_api.admin import add_user_to_store
from ken_web_api.auth_store import FakeAuthStore
from ken_web_api.security import verify_password


def test_add_user_stores_verifiable_hash():
    s = FakeAuthStore()
    add_user_to_store(s, "Alice@X.com", "password1")
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
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest ken-web/api/tests/test_admin.py -v`
Expected: FAIL `ModuleNotFoundError: ken_web_api.admin`.

- [ ] **Step 3: Implement** `ken-web/api/src/ken_web_api/admin.py`:

```python
"""ken-web-admin — operator CLI for the auth user store (Postgres). No public signup."""

from __future__ import annotations

import argparse
import getpass
import os
import sys

from ken_web_api.auth_store import AuthStore, PostgresAuthStore
from ken_web_api.security import hash_password

MIN_PASSWORD_LEN = 8


def add_user_to_store(store: AuthStore, email: str, password: str) -> None:
    """Core (store-injected, testable): validate + hash + create. Raises on weak
    password or duplicate email."""
    if len(password.strip()) < MIN_PASSWORD_LEN:
        raise ValueError(f"password must be at least {MIN_PASSWORD_LEN} characters")
    store.create_user(email, hash_password(password))


def _add_user_cli(email: str) -> int:
    dsn = os.getenv("KEN_DATABASE_URL")
    if not dsn:
        print("error: KEN_DATABASE_URL is required (auth is Postgres-only)", file=sys.stderr)
        return 1
    pw1 = getpass.getpass("password: ")
    pw2 = getpass.getpass("confirm:  ")
    if pw1 != pw2:
        print("error: passwords do not match", file=sys.stderr)
        return 1
    try:
        add_user_to_store(PostgresAuthStore(dsn), email, pw1)
    except Exception as exc:  # weak password / duplicate / DB error
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(f"created user {email.strip().lower()}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ken-web-admin")
    sub = parser.add_subparsers(dest="cmd", required=True)
    add = sub.add_parser("add-user", help="create a user (prompts for password)")
    add.add_argument("email")
    args = parser.parse_args(argv)
    if args.cmd == "add-user":
        return _add_user_cli(args.email)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Register the console script.** In `ken-web/api/pyproject.toml`, add after `dependencies` (top-level `[project]` table needs a scripts table):

```toml
[project.scripts]
ken-web-admin = "ken_web_api.admin:main"
```

- [ ] **Step 5: Run to verify it passes**

Run: `python -m pytest ken-web/api/tests/test_admin.py -v`
Expected: PASS (3 tests).

- [ ] **Step 6: Commit**

```bash
git add ken-web/api/src/ken_web_api/admin.py ken-web/api/tests/test_admin.py ken-web/api/pyproject.toml
git commit -m "feat(ken-web): ken-web-admin add-user CLI (Postgres)"
```

---

## Chunk 5: Frontend — login, guard, masthead, person drop

### Task 8: types + client (getMe/login/logout + 401 redirect)

**Files:** Modify `ken-web/web/src/types.ts`, `ken-web/web/src/api/client.ts`

- [ ] **Step 1: Add the `Me` type** to `types.ts`:

```typescript
/** MeOut — the current session identity. */
export interface Me {
  email: string;
}
```

- [ ] **Step 2: Add 401 handling + auth fns to `client.ts`.** In the `request` wrapper, when a non-auth call gets 401, redirect to `/login` (session expired). Add inside the `if (!res.ok)` block, BEFORE throwing:

```typescript
    if (res.status === 401 && !path.startsWith("/api/auth/")) {
      window.location.assign("/login");
    }
```

Then add the auth client fns (import `Me`):

```typescript
/** GET /api/auth/me — current identity, or throws ApiError(401). */
export function getMe(): Promise<Me> {
  return request<Me>("/api/auth/me");
}

/** POST /api/auth/login — sets the session cookie on success. */
export function login(email: string, password: string): Promise<Me> {
  return request<Me>("/api/auth/login", {
    method: "POST",
    headers: JSON_HEADERS,
    body: JSON.stringify({ email, password }),
  });
}

/** POST /api/auth/logout — clears the session. */
export function logout(): Promise<void> {
  return request<void>("/api/auth/logout", { method: "POST" });
}
```

Also update `postAttempt` / `AttemptRequest` usage: the attempt body no longer carries `person`. In `types.ts`, remove `person` from `AttemptRequest`.

- [ ] **Step 3: Commit**

```bash
git add ken-web/web/src/types.ts ken-web/web/src/api/client.ts
git commit -m "feat(ken-web): web auth client (getMe/login/logout) + 401 redirect"
```

### Task 9: Login page

**Files:** Create `ken-web/web/src/pages/Login.tsx`, `ken-web/web/tests/login.test.tsx`

- [ ] **Step 1: Write the failing test** `ken-web/web/tests/login.test.tsx`:

```tsx
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Routes, Route, useLocation } from "react-router-dom";

vi.mock("../src/api/client", () => ({ login: vi.fn(), ApiError: class extends Error {} }));
import * as client from "../src/api/client";
import Login from "../src/pages/Login";

const login = client.login as unknown as ReturnType<typeof vi.fn>;

function HomeStub() {
  const loc = useLocation();
  return <div>home: {loc.pathname}</div>;
}
function renderLogin() {
  return render(
    <MemoryRouter initialEntries={["/login"]}>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="/" element={<HomeStub />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("Login", () => {
  beforeEach(() => vi.clearAllMocks());

  it("submits credentials and navigates home on success", async () => {
    login.mockResolvedValue({ email: "a@x.com" });
    const user = userEvent.setup();
    renderLogin();
    await user.type(screen.getByLabelText(/email/i), "a@x.com");
    await user.type(screen.getByLabelText(/password/i), "password1");
    await user.click(screen.getByRole("button", { name: /sign in|log in/i }));
    expect(login).toHaveBeenCalledWith("a@x.com", "password1");
    expect(await screen.findByText("home: /")).toBeInTheDocument();
  });

  it("shows a generic error on 401", async () => {
    login.mockRejectedValue(Object.assign(new Error("invalid email or password"), { status: 401 }));
    const user = userEvent.setup();
    renderLogin();
    await user.type(screen.getByLabelText(/email/i), "a@x.com");
    await user.type(screen.getByLabelText(/password/i), "bad");
    await user.click(screen.getByRole("button", { name: /sign in|log in/i }));
    expect(await screen.findByText(/invalid email or password/i)).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd ken-web/web && npx vitest run tests/login.test.tsx`
Expected: FAIL (module `../src/pages/Login` not found).

- [ ] **Step 3: Implement** `ken-web/web/src/pages/Login.tsx` — a small controlled form: email + password inputs (with `<label htmlFor>` so `getByLabelText` works), a submit button "Sign in"; on submit call `login(email, password)`, on success `navigate("/")`, on failure set an error string (use `err.message`). Use existing classes (`field`, `btn btn--primary`, `state`) for consistency. Keep it focused (~50 lines).

- [ ] **Step 4: Run to verify it passes**

Run: `cd ken-web/web && npx vitest run tests/login.test.tsx`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add ken-web/web/src/pages/Login.tsx ken-web/web/tests/login.test.tsx
git commit -m "feat(ken-web): Login page"
```

### Task 10: AuthGuard + routing + masthead

**Files:** Create `ken-web/web/src/components/AuthGuard.tsx` (exports `AuthGuard`, `AuthContext`, `useAuth`), `ken-web/web/src/components/MastheadUser.tsx`, `ken-web/web/tests/auth-guard.test.tsx`, `ken-web/web/tests/masthead-user.test.tsx`; modify `ken-web/web/src/App.tsx`, `ken-web/web/src/pages/Review.tsx`

- [ ] **Step 1: Write the failing test** `ken-web/web/tests/auth-guard.test.tsx`:

```tsx
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router-dom";

vi.mock("../src/api/client", () => ({ getMe: vi.fn(), logout: vi.fn(), ApiError: class extends Error {} }));
import * as client from "../src/api/client";
import AuthGuard from "../src/components/AuthGuard";

const getMe = client.getMe as unknown as ReturnType<typeof vi.fn>;

function renderGuard() {
  return render(
    <MemoryRouter initialEntries={["/"]}>
      <Routes>
        <Route path="/" element={<AuthGuard><div>secret content</div></AuthGuard>} />
        <Route path="/login" element={<div>login page</div>} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("AuthGuard", () => {
  beforeEach(() => vi.clearAllMocks());

  it("renders children when authenticated", async () => {
    getMe.mockResolvedValue({ email: "a@x.com" });
    renderGuard();
    expect(await screen.findByText("secret content")).toBeInTheDocument();
  });

  it("redirects to /login when getMe rejects (401)", async () => {
    getMe.mockRejectedValue(Object.assign(new Error("authentication required"), { status: 401 }));
    renderGuard();
    expect(await screen.findByText("login page")).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd ken-web/web && npx vitest run tests/auth-guard.test.tsx`
Expected: FAIL (module not found).

- [ ] **Step 3: Implement** `ken-web/web/src/components/AuthGuard.tsx` with a **pinned context mechanism** (so the masthead has one well-defined way to read identity):

```tsx
import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { Navigate } from "react-router-dom";
import { getMe } from "../api/client";

interface AuthValue { email: string; }
export const AuthContext = createContext<AuthValue>({ email: "" });
export const useAuth = () => useContext(AuthContext);

type Status = "loading" | "authed" | "anon";

export default function AuthGuard({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<Status>("loading");
  const [email, setEmail] = useState("");
  useEffect(() => {
    let alive = true;
    getMe()
      .then((m) => { if (alive) { setEmail(m.email); setStatus("authed"); } })
      .catch(() => { if (alive) setStatus("anon"); });
    return () => { alive = false; };
  }, []);
  if (status === "loading") return <div className="skeleton" style={{ height: 80, margin: 40 }} />;
  if (status === "anon") return <Navigate to="/login" replace />;
  return <AuthContext.Provider value={{ email }}>{children}</AuthContext.Provider>;
}
```

- [ ] **Step 4: Write the failing masthead test** `ken-web/web/tests/masthead-user.test.tsx`:

```tsx
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

vi.mock("../src/api/client", () => ({ logout: vi.fn().mockResolvedValue(undefined) }));
import * as client from "../src/api/client";
import MastheadUser from "../src/components/MastheadUser";
import { AuthContext } from "../src/components/AuthGuard";

const logout = client.logout as unknown as ReturnType<typeof vi.fn>;

function renderWith(email: string) {
  return render(
    <AuthContext.Provider value={{ email }}>
      <MastheadUser />
    </AuthContext.Provider>,
  );
}

describe("MastheadUser", () => {
  beforeEach(() => vi.clearAllMocks());

  it("shows the email + a Log out button when authenticated", async () => {
    renderWith("a@x.com");
    expect(screen.getByText("a@x.com")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /log ?out/i }));
    expect(logout).toHaveBeenCalled();
  });

  it("renders the static eyebrow (no logout) when auth is off (email=local)", () => {
    renderWith("local");
    expect(screen.queryByRole("button", { name: /log ?out/i })).toBeNull();
    expect(screen.getByText(/self-host/i)).toBeInTheDocument();
  });
});
```

- [ ] **Step 5: Implement** `ken-web/web/src/components/MastheadUser.tsx`:

```tsx
import { logout } from "../api/client";
import { useAuth } from "./AuthGuard";

export default function MastheadUser() {
  const { email } = useAuth();
  if (email === "local") return <span className="eyebrow">self-host · single team</span>;
  async function doLogout() {
    await logout();
    window.location.assign("/login");
  }
  return (
    <span className="eyebrow" style={{ display: "inline-flex", gap: 12, alignItems: "center" }}>
      <span>{email}</span>
      <button type="button" className="btn btn--ghost" onClick={doLogout}>Log out</button>
    </span>
  );
}
```

- [ ] **Step 6: Run the new tests to pass**

Run: `cd ken-web/web && npx vitest run tests/auth-guard.test.tsx tests/masthead-user.test.tsx`
Expected: PASS.

- [ ] **Step 7: Wire routing + masthead in `App.tsx`.** Add a `/login` route OUTSIDE the guard; wrap the rest of the app in `AuthGuard`; replace the static masthead eyebrow `<span className="eyebrow">self-host · single team</span>` with `<MastheadUser/>`. Concretely, structure as:

```tsx
<Routes>
  <Route path="/login" element={<Login />} />
  <Route path="/*" element={
    <AuthGuard>
      <Shell>{/* masthead with <MastheadUser/> + the existing <Routes> for / /review /artifact/:id */}</Shell>
    </AuthGuard>
  } />
</Routes>
```

Keep the existing `/`, `/review`, `/artifact/:id` routes (now nested under the guarded element). Import `Login`, `AuthGuard`, `MastheadUser`. (The masthead currently lives in `App`'s top-level shell — move the `<MastheadUser/>` into the guarded subtree so `useAuth()` has a provider; the `/login` page renders without the masthead.)

- [ ] **Step 8: Drop `person` from Review.** In `ken-web/web/src/pages/Review.tsx`, remove the `person: "kr",` line from the `postAttempt({...})` call (the server now derives it). Confirm `AttemptRequest` no longer has `person` (removed in Task 8).

- [ ] **Step 9: Run all web tests + build**

Run: `cd ken-web/web && npx vitest run && npm run build`
Expected: PASS (login + auth-guard + masthead-user + home + review + artifact-detail) and a clean build. Existing `home.test.tsx` / `review.test.tsx` / `artifact-detail.test.tsx` render their pages **directly** (not through `App`), so wrapping `App` in `AuthGuard` does not affect them — confirm none import `App`; if any did, mock `getMe` to resolve.

- [ ] **Step 10: Commit**

```bash
git add ken-web/web/src/components/AuthGuard.tsx ken-web/web/src/components/MastheadUser.tsx ken-web/web/tests/auth-guard.test.tsx ken-web/web/tests/masthead-user.test.tsx ken-web/web/src/App.tsx ken-web/web/src/pages/Review.tsx
git commit -m "feat(ken-web): AuthGuard + /login route + masthead user/logout; Review drops person"
```

---

## Final verification

- [ ] **Run all suites**

```bash
python -m pytest ken/tests/ ken-web/api/tests/ -q
cd ken-web/web && npx vitest run && npm run build
```
Expected: all green (PG-gated auth_store test runs in CI's Postgres job; DB-free auth tests cover the rest); SPA builds.

- [ ] **Lint/type (match CI):** ruff over the api/ken changes; the web typecheck/lint the CI uses. Expected: clean.

- [ ] **README:** update `ken-web/README.md` — an "Authentication (optional)" section: enable with `KEN_AUTH=1` + `KEN_DATABASE_URL` (Postgres) + apply `db/init.sql`; create users with `ken-web-admin add-user <email>`; note file backend stays unauthenticated/local. Commit.

- [ ] **Push branch + PR** (`feat/ken-web-s6-auth`), wait for CI 9 jobs green, then merge (per project workflow).
