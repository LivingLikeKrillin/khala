# Design Spec — ken-web S6: authentication gating (single-team login)

**Date:** 2026-06-24
**Status:** approved design → spec
**Milestone:** B→C bridge (gate the self-host instance; multi-tenancy is the NEXT slice)
**Depends on:** ken-web v0 (#35), S2 Postgres graduation (#37)

## 1. Goal & scope

ken-web today is **open** — README states "Postgres … (no auth)". S6 adds a **login gate** so a
self-hosted instance is not wide open: only authenticated users reach the app, and the
attempt ledger's `person` becomes the **logged-in user** instead of the hardcoded `"kr"`.

This slice is **authentication only**. **Multi-tenancy** (per-tenant data isolation,
`tenant_id` on every row, org/membership) is explicitly a **separate follow-on slice** — the
data stays single-team/shared among authenticated users here.

Settled in brainstorming:
- **Method:** email + password, **local user store**, argon2 hashing, httpOnly cookie session.
- **Backend:** **Postgres-only auth.** The file backend stays local/dev and **unauthenticated**
  (consistent with "keyless = local-only"). The `ken` CLI is unchanged.
- **Provisioning:** **CLI-seeded users**, no public signup. Login page only.

## 2. Approaches (chosen)

- **Session:** **server-side `sessions` table + opaque random token** (revocable, no signing
  secret). Rejected: stateless signed cookie/JWT (needs `SECRET_KEY`, not revocable).
- **Enablement:** explicit **`KEN_AUTH=1`** flag (requires Postgres; fail-loud at startup if the
  file backend is active). Rejected: auto-on when Postgres present (couples "I use Postgres" with
  "I want auth"). When `KEN_AUTH` is unset/`0`, behavior is exactly today's (no auth).

Everything is **additive**: no change to the `ken` engine, the file store, or the `ken` CLI.

## 3. Schema (`ken/db/init.sql`, two new tables)

Append to the existing schema file (applied via `psql -f db/init.sql`):

```sql
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

The PG-test reset (`test_store_contract.py` TRUNCATE) and any new auth PG test must include
`users, sessions` (CASCADE-safe order). `email` is stored **lowercased** (normalize on write and
lookup) so login is case-insensitive and the UNIQUE constraint is meaningful.

## 4. Units

### 4.1 Password hashing — `ken_web_api.security` (new)

Thin wrapper over **argon2-cffi** (new dependency on `ken-web-api`):
- `hash_password(plain: str) -> str` — argon2 hash (a fresh per-hash salt is built in).
- `verify_password(hash: str, plain: str) -> bool` — constant-time verify; returns False on
  mismatch or malformed hash. It catches the **argon2 exception base**
  `argon2.exceptions.VerificationError` (covers `VerifyMismatchError`) **and**
  `argon2.exceptions.InvalidHashError` → False; it does **not** catch bare `Exception` (real bugs
  must surface).
- `DUMMY_HASH` — a precomputed argon2 hash of a random string, used to spend a constant-time
  verify on the unknown-email login path (see §4.5) so login timing doesn't leak which emails
  exist.
- `new_session_token() -> str` — `secrets.token_urlsafe(32)` (256-bit opaque token).

No password is ever logged. Minimal policy: reject empty/whitespace and `< 8` chars **at the
CLI** (creation time); the API never creates users.

### 4.2 `AuthStore` Protocol + two implementations — `ken_web_api.auth_store` (new)

The seam that makes auth testable without a DB (mirrors the `make_llm`/`make_store` pattern):

```python
@dataclass(frozen=True)
class User:
    id: int
    email: str

class AuthStore(Protocol):
    def get_user_by_email(self, email: str) -> tuple[User, str] | None: ...  # (User, password_hash)
    def create_user(self, email: str, password_hash: str) -> User: ...        # raises on duplicate email
    def create_session(self, user_id: int, token: str, expires_at: str) -> None: ...
    def user_for_session(self, token: str, *, now: str) -> User | None: ...    # None if missing/expired
    def delete_session(self, token: str) -> None: ...
```

- **`PostgresAuthStore(dsn)`** — psycopg3, sync, per-request connection, parameterized, fail-loud
  (same shape as `PostgresStore`). `user_for_session` filters `expires_at > %(now)s` in SQL
  (psycopg binds the ISO `now` string; Postgres casts it to `timestamptz` — sound for
  offset-aware ISO-8601).
- **`FakeAuthStore`** — in-memory dicts, for tests. Same contract.

**Canonical timestamp rule (both stores).** All timestamps (`expires_at`, the `now` arg) are
offset-aware ISO-8601 produced the same way as `service.now_iso()` (UTC, `+00:00`, microsecond
precision — the same convention `PostgresStore.load_attempts` already renders via `.isoformat()`).
`create_session` computes `expires_at = (now_dt + SESSION_TTL).isoformat()`. `FakeAuthStore`
compares by **parsing** both to datetimes (reuse `schedule._parse_ts` / `datetime.fromisoformat`),
**not** lexicographically, so format drift can't mis-order the boundary.

`deps.make_auth_store()` returns `PostgresAuthStore(KEN_DATABASE_URL)`; tests monkeypatch it to a
`FakeAuthStore`. `deps.auth_enabled()` returns `os.getenv("KEN_AUTH") == "1"` — **exact string
`"1"` only** (a typo like `KEN_AUTH=true` resolves to OFF; the startup log in §4.3 makes the
resolved mode visible so a misconfiguration is caught by eye).

### 4.3 Startup guard

At **true startup** (FastAPI `lifespan` / `@app.on_event("startup")`, not first-request), if
`auth_enabled()` is true and `KEN_DATABASE_URL` is **unset**, fail loud (`RuntimeError`:
"KEN_AUTH=1 requires KEN_DATABASE_URL (Postgres)") so a misconfigured instance never reports ready.
Auth must never silently run against the file backend. The startup hook also emits one log line with
the **resolved auth mode** — `auth: ENABLED` or `auth: OFF` — so an operator can eyeball that a typo
(`KEN_AUTH=true` → OFF) didn't silently leave the instance open.

### 4.4 `require_user` dependency + identity binding

A FastAPI dependency used by every data endpoint:

```python
def require_user(request: Request) -> str:   # returns the person identifier (email)
    if not deps.auth_enabled():
        return DEFAULT_PERSON            # "local" — auth-off keeps today's open behavior
    token = request.cookies.get(SESSION_COOKIE)   # "ken_session"
    user = token and deps.make_auth_store().user_for_session(token, now=service.now_iso())
    if not user:
        raise HTTPException(status_code=401, detail="authentication required")
    return user.email
```

Applied to `GET/POST /api/artifacts`, `/api/artifacts/{id}/due`, `/api/artifacts/{id}/detail`,
`/api/attempts`, `/api/coverage`. The `/api/auth/*` routes do **not** use it (except `/me`, which
returns 401 itself when unauthenticated).

**`person` becomes server-derived (contract change).** `AttemptReq.person` is **removed**;
`post_attempt` sets `person = require_user(...)`. The client no longer sends `person`. This removes
the hardcoded `"kr"` and prevents a client from claiming an arbitrary identity. When auth is off,
`person` is `DEFAULT_PERSON` ("local").

### 4.5 Auth endpoints — `ken_web_api.app`

- `POST /api/auth/login` (body `LoginReq {email: str, password: str}`) → look up user (lowercased
  email), `verify_password`; on success create a session (fresh token + `expires_at = now +
  SESSION_TTL`, e.g. 14 days — a new token per login, no pre-auth session, so no fixation), set
  cookie `ken_session` (**httpOnly, SameSite=Lax, Path=/**, `Secure` when `KEN_COOKIE_SECURE=1`),
  return `{email}`. On failure → **401 with a generic detail** ("invalid email or password") — no
  user enumeration, identical response for unknown email vs wrong password. **Constant-time across
  branches:** on the unknown-email path, still run one `verify_password(DUMMY_HASH, password)` so
  the response timing doesn't reveal whether the email exists.
- `POST /api/auth/logout` → read the cookie; if a token is present `delete_session(token)`; always
  clear the cookie and return `204`. **Idempotent** — missing/unknown token is a no-op `204`, never
  an error.
- `GET /api/auth/me` → `{email}` for a valid session, else `401`.

DTOs added to `schemas.py`: `LoginReq {email, password}`, `MeOut {email}`.

When `auth_enabled()` is false, `/login` and `/logout` are inert (login returns 400 "auth
disabled"); `/me` returns `{email: DEFAULT_PERSON}` so the SPA renders a stable identity.

### 4.6 CLI admin — `ken_web_api.admin` (new console script)

Registered in `ken-web/api/pyproject.toml` `[project.scripts]` as `ken-web-admin`:
- `ken-web-admin add-user <email>` → prompt for a password (twice, hidden via `getpass`), validate
  policy, `hash_password`, `create_user`. Requires `KEN_DATABASE_URL`; prints a clear error if
  unset or if the email already exists. (Only `add-user` this slice; password reset / remove-user
  are deferred.)

### 4.7 Frontend — `ken-web/web`

- **`/login` page** (`pages/Login.tsx`): email + password form → `POST /api/auth/login`; on success
  navigate to `/`; on 401 show the generic error.
- **Auth guard**: an `AuthProvider`/guard that on mount calls `GET /api/auth/me`; while pending shows
  a spinner; on 401 redirects to `/login`. The `api/client.ts` `request` wrapper, on a `401` from any
  data call, redirects to `/login` (session expired mid-use).
- **Masthead**: replace the static "self-host · single team" eyebrow with the logged-in email + a
  **Logout** button (`POST /api/auth/logout` → redirect to `/login`). When `me` returns the
  `DEFAULT_PERSON` (auth off), render today's static eyebrow (no logout).
- `types.ts`: add `Me { email: string }`. `client.ts`: add `login`, `logout`, `getMe`. The web
  `Review.tsx` stops sending `person` in the attempt body.

## 5. Data flow

```
Browser → GET /api/auth/me
  401 → /login → POST /api/auth/login {email,password}
       → verify (argon2) → create session row → Set-Cookie ken_session (httpOnly)
       → SPA loads; every /api/* call carries the cookie → require_user → person=email
  Logout → POST /api/auth/logout → delete session row + clear cookie → /login
Operator (server shell) → ken-web-admin add-user alice@x.com → argon2 hash → users insert
```

## 6. Non-goals (S6)

Multi-tenancy / `tenant_id` isolation / org / membership / invites; public signup; password reset;
email sending; OAuth/SSO; “remember me”/refresh tokens; rate-limiting login (note as a fast-follow);
file-backend auth (file stays unauthenticated local/dev). The `ken` engine and CLI are untouched.

## 7. Error handling & integrity

- Login failures are **generic 401** (no enumeration); wrong password and unknown email are
  indistinguishable.
- `KEN_AUTH=1` without Postgres → **fail-loud at startup** (never run auth on the file backend).
- Session lookup filters `expires_at > now`; expired sessions behave as logged-out (401).
- `verify_password` never raises (malformed hash → False).
- Writes (create_user/create_session) are fail-loud (psycopg `with` rolls back).
- `person` is **never** client-trusted when auth is on; always the session's user email.
- Cookie is httpOnly (no JS access) + SameSite=Lax; `Secure` in prod via `KEN_COOKIE_SECURE=1`.
- **CSRF / same-origin.** Auth is **same-origin only** (the SPA uses relative `/api/...` paths; prod
  serves the built SPA from the API origin, dev uses the Vite proxy). SameSite=Lax blocks the
  cross-site POST CSRF vector (`/api/attempts`, `/api/auth/*`). The existing dev CORS block
  (`app.py`, `allow_origins=["http://localhost:5173"]`) is **non-credentialed dev-only**; a future
  reader must **not** add `allow_credentials=True` / cross-origin cookie sharing without
  re-evaluating CSRF (it would require an explicit anti-CSRF token). No cross-origin auth is in
  scope.
- **Auth mode is explicit and logged** (§4.3): `auth_enabled()` accepts only `"1"`; the resolved
  mode is logged at startup so a typo can't silently leave the instance open.

## 8. Testing

- **api (no DB, `FakeAuthStore` + `monkeypatch deps.make_auth_store`, `KEN_AUTH=1`):** login success
  sets cookie + returns email; login wrong-password and unknown-email both → 401 with the SAME
  generic detail; `/me` without cookie → 401, with valid session → email; a protected endpoint
  (e.g. `/api/coverage`) → 401 without session, 200 with; logout clears the session (subsequent
  `/me` → 401); **expired session → 401**; **`person` is server-derived** — POST an attempt with a
  session, assert the stored attempt's `person` equals the session email (not any client value).
- **api auth-OFF (`KEN_AUTH` unset):** all data endpoints open (200, today's behavior); `/me` →
  `{email: "local"}`; attempts stored with `person="local"`.
- **api startup guard:** `KEN_AUTH=1` + no `KEN_DATABASE_URL` → fail-loud.
- **Expiry boundary (Fake, no DB):** a session expiring at `T` is valid at `now < T` and rejected
  (401 / `user_for_session → None`) at `now >= T`, asserted with `now` values straddling `T` by a
  microsecond — proving the comparison parses datetimes and isn't lexicographic. (Mirror the
  `next_due_at` boundary-test discipline.)
- **PG-gated (`KEN_TEST_DATABASE_URL`, like store_contract):** `PostgresAuthStore` round-trip —
  create_user (and duplicate-email raises), create_session, `user_for_session` honors expiry
  (valid before / None after), delete_session. TRUNCATE includes `users, sessions` (CASCADE order).
- **CLI:** `add-user` against a Fake/PG store stores a hash that `verify_password` accepts and a wrong
  password rejects; duplicate email errors; weak/empty password rejected.
- **web (vitest, client mocked):** Login submits → on success navigates to `/`; on 401 shows the
  generic error; guard redirects to `/login` when `getMe` 401s; masthead shows the email + Logout
  when authenticated; Review no longer sends `person`.

## 9. Success criteria

- With `KEN_AUTH=1` + Postgres, an unauthenticated browser is redirected to `/login`; only a user
  created via `ken-web-admin add-user` can log in; the session cookie gates every `/api/*` data call;
  the attempt ledger records the logged-in email as `person`; logout ends the session.
- With `KEN_AUTH` unset, ken-web behaves exactly as today (open, `person="local"`).
- The file backend and the `ken` CLI are unchanged; CI stays green (the PG job applies the extended
  `init.sql`; DB-free tests cover the bulk via `FakeAuthStore`).
- No multi-tenancy surface introduced (single shared dataset).

## Implementation outline (for writing-plans)

1. `init.sql`: add `users` + `sessions`; extend PG-test TRUNCATE.
2. `ken_web_api.security`: argon2 hash/verify + session token (+ unit tests). Add `argon2-cffi` dep.
3. `ken_web_api.auth_store`: `User`, `AuthStore` Protocol, `FakeAuthStore`, `PostgresAuthStore`;
   `deps.make_auth_store` / `deps.auth_enabled` (+ Fake-based tests; PG-gated contract test).
4. `app`: `require_user` dep + startup guard; `/api/auth/login|logout|me`; apply guard to data
   routes; make `person` server-derived (remove `AttemptReq.person`).
5. `ken_web_api.admin`: `add-user` console script; register in pyproject `[project.scripts]`.
6. web: `Login.tsx`, auth guard + 401 redirect in `client.ts`, masthead user/logout, `getMe/login/
   logout` client + `Me` type, Review drops `person`.
7. Verify CI green; update `ken-web/README.md` (auth section: enable with `KEN_AUTH=1` + Postgres +
   `ken-web-admin add-user`).
