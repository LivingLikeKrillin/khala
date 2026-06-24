# ken-web Tenancy (per-tenant data isolation) Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Isolate ken-web data per tenant — each user belongs to one tenant (org), and every artifact/question/attempt is scoped to it, so a user only ever sees their own tenant's data.

**Architecture:** App-enforced row-level isolation with the **tenant-bound `PostgresStore` as the single boundary**. Tenant key = a **slug** (`tenants.slug` PK; `DEFAULT_TENANT="default"`). Composite PKs `(tenant_slug, artifact_id[, question_id])` + `tenant_slug` on attempts. The `KenStore` Protocol and `service.*` are unchanged (tenant bound at construction). `require_user` returns a `Principal{email, tenant_slug}`; `make_store(tenant_slug)`. Layered on S6 auth; Postgres-only; file backend stays single-tenant; the `ken` engine/CLI are untouched.

**Tech Stack:** Postgres (psycopg3), FastAPI, React (unchanged this slice), pytest.

**Spec:** `docs/superpowers/specs/2026-06-24-ken-web-tenancy-isolation-design.md`

**Sequencing note (green at every commit):** signature changes ripple, so transitional **defaults** keep each commit green: `make_store(tenant_slug="default")` and `create_user(..., tenant_slug="default")` default so un-migrated callers still work, while the **security read field `User.tenant_slug` is REQUIRED** (no default) so a forgotten set fails fast. The api isolation tests (Chunk 4) verify the real tenant actually flows end-to-end.

---

## File Structure

- `ken/db/init.sql` — **rewrite**: `tenants` + seed `default`; `users.tenant_slug`; composite-key `artifacts`/`questions` + `tenant_slug` on `attempts`.
- `ken/db/migrate-tenancy.sql` — **create**: run-once migration for an existing S6 DB.
- `ken/src/ken/stores/postgres_store.py` — **modify**: `PostgresStore(dsn, tenant_slug)`; thread `tenant_slug` through all 6 methods.
- `ken/tests/test_store_contract.py` — **modify**: tenant-bound PG factory; `TRUNCATE … CASCADE` + seed; add a 2-tenant isolation PG test.
- `ken-web/api/src/ken_web_api/deps.py` — **modify**: `make_store(tenant_slug="default")`; `DEFAULT_TENANT`.
- `ken-web/api/src/ken_web_api/auth_store.py` — **modify**: `User.tenant_slug`; `create_user(…, tenant_slug)`; `create_tenant`; return slug from lookups.
- `ken-web/api/tests/test_auth_store.py` — **modify**: tenant round-trip + `create_tenant` tests.
- `ken-web/api/src/ken_web_api/app.py` — **modify**: `Principal`; `require_user -> Principal`; 5 routes + `me` + `post_attempt` use it; `make_store(principal.tenant_slug)`.
- `ken-web/api/tests/test_auth_api.py` — **modify**: fix the `make_store` monkeypatch; add tenant-isolation tests.
- `ken-web/api/src/ken_web_api/admin.py` — **modify**: `create-tenant`; `add-user --tenant` (required); `add_user_to_store(…, tenant_slug)`.
- `ken-web/api/tests/test_admin.py` — **modify**: pass `tenant_slug`; `create-tenant` test.
- `ken-web/README.md` — **modify**: tenancy section.

---

## Chunk 1: schema

### Task 1: Rewrite `init.sql` + add `migrate-tenancy.sql`

**Files:** Modify `ken/db/init.sql`; Create `ken/db/migrate-tenancy.sql`

- [ ] **Step 1: Rewrite `ken/db/init.sql`.** Replace the `artifacts`/`questions`/`attempts` block (lines ~10-35) with the tenant-scoped version, add `tenants` (seeded) at the top of the data section, and give `users` a `tenant_slug`. Final schema:

```sql
-- ken Postgres schema. Tenant-isolated (one tenant per user); tenant key = slug.
-- The DB is an INDEX, not the artifact archive (content_hash is read live from disk).
-- Apply with:  psql "$KEN_DATABASE_URL" -f db/init.sql

CREATE TABLE tenants (
    slug       TEXT PRIMARY KEY,
    name       TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
INSERT INTO tenants (slug, name) VALUES ('default', 'Default');

CREATE TABLE artifacts (
    tenant_slug TEXT NOT NULL REFERENCES tenants(slug),
    artifact_id TEXT NOT NULL,
    path        TEXT NOT NULL,
    PRIMARY KEY (tenant_slug, artifact_id),
    UNIQUE (tenant_slug, path)
);

CREATE TABLE questions (
    tenant_slug  TEXT NOT NULL REFERENCES tenants(slug),
    artifact_id  TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    question_id  TEXT NOT NULL,
    idx          INTEGER NOT NULL,
    text         TEXT NOT NULL,
    PRIMARY KEY (tenant_slug, artifact_id, question_id)
);
CREATE INDEX idx_questions_tenant_artifact ON questions (tenant_slug, artifact_id);

CREATE TABLE attempts (
    id           BIGSERIAL PRIMARY KEY,
    tenant_slug  TEXT NOT NULL REFERENCES tenants(slug),
    person       TEXT NOT NULL,
    artifact_id  TEXT NOT NULL,
    question_id  TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    passed       BOOLEAN NOT NULL,
    score        DOUBLE PRECISION NOT NULL,
    ts           TIMESTAMPTZ NOT NULL
);
CREATE INDEX idx_attempts_tenant_question ON attempts (tenant_slug, question_id);

-- S6 auth (Postgres-only gating).
CREATE TABLE users (
    id            BIGSERIAL PRIMARY KEY,
    email         TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    tenant_slug   TEXT NOT NULL REFERENCES tenants(slug),
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE sessions (
    token      TEXT PRIMARY KEY,
    user_id    BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    expires_at TIMESTAMPTZ NOT NULL
);
CREATE INDEX idx_sessions_user ON sessions (user_id);
```

- [ ] **Step 2: Create `ken/db/migrate-tenancy.sql`** (run-once, on a DB already at the S6 schema):

```sql
-- Run ONCE on an existing S6 database to add tenant isolation. NOT idempotent
-- (re-running fails on the existing tenants table / columns).
-- Verify the constraint names against the live DB (\d artifacts / \d questions) first;
-- artifacts_pkey / artifacts_path_key / questions_pkey are the Postgres defaults.
BEGIN;

CREATE TABLE tenants (slug TEXT PRIMARY KEY, name TEXT NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT now());
INSERT INTO tenants (slug, name) VALUES ('default', 'Default');

ALTER TABLE users     ADD COLUMN tenant_slug TEXT NOT NULL DEFAULT 'default' REFERENCES tenants(slug);
ALTER TABLE artifacts ADD COLUMN tenant_slug TEXT NOT NULL DEFAULT 'default' REFERENCES tenants(slug);
ALTER TABLE questions ADD COLUMN tenant_slug TEXT NOT NULL DEFAULT 'default' REFERENCES tenants(slug);
ALTER TABLE attempts  ADD COLUMN tenant_slug TEXT NOT NULL DEFAULT 'default' REFERENCES tenants(slug);

ALTER TABLE artifacts DROP CONSTRAINT artifacts_pkey,     ADD PRIMARY KEY (tenant_slug, artifact_id);
ALTER TABLE artifacts DROP CONSTRAINT artifacts_path_key, ADD UNIQUE (tenant_slug, path);
ALTER TABLE questions DROP CONSTRAINT questions_pkey,     ADD PRIMARY KEY (tenant_slug, artifact_id, question_id);

CREATE INDEX idx_questions_tenant_artifact ON questions (tenant_slug, artifact_id);
CREATE INDEX idx_attempts_tenant_question  ON attempts  (tenant_slug, question_id);

COMMIT;
```

- [ ] **Step 3: Commit**

```bash
git add ken/db/init.sql ken/db/migrate-tenancy.sql
git commit -m "feat(ken): tenant-scoped schema (tenants + composite keys) + migration"
```

---

## Chunk 2: tenant-bound PostgresStore + make_store(tenant_slug)

### Task 2: Thread `tenant_slug` through `PostgresStore`

**Files:** Modify `ken/src/ken/stores/postgres_store.py`, `ken-web/api/src/ken_web_api/deps.py`, `ken/tests/test_store_contract.py`

- [ ] **Step 1: Bind the tenant in the constructor.** In `postgres_store.py`, change `__init__` to take the tenant and update EVERY method to filter/insert `tenant_slug = self._tenant`:

```python
class PostgresStore:
    def __init__(self, dsn: str, tenant_slug: str):
        self._dsn = dsn
        self._tenant = tenant_slug

    def _conn(self):
        import psycopg
        return psycopg.connect(self._dsn)

    def load_manifest(self) -> list[ArtifactRef]:
        with self._conn() as c, c.cursor() as cur:
            cur.execute(
                "SELECT artifact_id, path FROM artifacts WHERE tenant_slug = %s ORDER BY path",
                (self._tenant,),
            )
            return [ArtifactRef(aid, path, current_hash(path)) for aid, path in cur.fetchall()]

    def register(self, path: str) -> ArtifactRef:
        aid = _artifact_id(path)
        with self._conn() as c, c.cursor() as cur:
            cur.execute(
                "INSERT INTO artifacts (tenant_slug, artifact_id, path) VALUES (%s, %s, %s) "
                "ON CONFLICT (tenant_slug, path) DO NOTHING",
                (self._tenant, aid, path),
            )
            cur.execute(
                "SELECT artifact_id FROM artifacts WHERE tenant_slug = %s AND path = %s",
                (self._tenant, path),
            )
            aid = cur.fetchone()[0]
        return ArtifactRef(aid, path, current_hash(path))

    def load_questions(self, artifact_id: str) -> tuple[str | None, list[Question]]:
        with self._conn() as c, c.cursor() as cur:
            cur.execute(
                "SELECT content_hash, question_id, text FROM questions "
                "WHERE tenant_slug = %s AND artifact_id = %s ORDER BY idx",
                (self._tenant, artifact_id),
            )
            rows = cur.fetchall()
        if not rows:
            return None, []
        return rows[0][0], [Question(id=qid, text=text) for _, qid, text in rows]

    def save_questions(self, artifact_id: str, content_hash: str, questions: list[Question]) -> None:
        with self._conn() as c, c.cursor() as cur:
            cur.execute(
                "DELETE FROM questions WHERE tenant_slug = %s AND artifact_id = %s",
                (self._tenant, artifact_id),
            )
            for i, q in enumerate(questions):
                qid = q.id or make_question_id(artifact_id, content_hash, i)
                cur.execute(
                    "INSERT INTO questions (tenant_slug, artifact_id, content_hash, question_id, idx, text) "
                    "VALUES (%s, %s, %s, %s, %s, %s)",
                    (self._tenant, artifact_id, content_hash, qid, i, q.text),
                )

    def append_attempt(self, attempt: Attempt) -> None:
        with self._conn() as c, c.cursor() as cur:
            cur.execute(
                "INSERT INTO attempts "
                "(tenant_slug, person, artifact_id, question_id, content_hash, passed, score, ts) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                (self._tenant, attempt.person, attempt.artifact_id, attempt.question_id,
                 attempt.content_hash, attempt.passed, attempt.score, attempt.ts),
            )

    def load_attempts(self) -> list[Attempt]:
        with self._conn() as c, c.cursor() as cur:
            cur.execute(
                "SELECT person, artifact_id, question_id, content_hash, passed, score, ts "
                "FROM attempts WHERE tenant_slug = %s ORDER BY id",
                (self._tenant,),
            )
            return [
                Attempt(person, artifact_id, question_id, content_hash, passed, score,
                        ts.isoformat() if hasattr(ts, "isoformat") else ts)
                for person, artifact_id, question_id, content_hash, passed, score, ts in cur.fetchall()
            ]
```

Update the module docstring's "Contract parity" note to mention the tenant binding.

- [ ] **Step 2: `deps.make_store(tenant_slug)`.** In `deps.py`, add `DEFAULT_TENANT` and thread the slug (default keeps app.py green until Chunk 4):

```python
DEFAULT_TENANT = "default"

def make_store(tenant_slug: str = DEFAULT_TENANT) -> KenStore:
    """Storage factory. Postgres -> tenant-bound PostgresStore; file -> single-tenant FileStore."""
    dsn = os.getenv("KEN_DATABASE_URL")
    if dsn:
        from ken.stores.postgres_store import PostgresStore
        return PostgresStore(dsn, tenant_slug)
    from ken.stores.file_store import FileStore
    return FileStore(manifest=manifest_path(), questions=questions_path(), ledger=ledger_path())
```

(Place `DEFAULT_TENANT` near `DEFAULT_PERSON`.)

- [ ] **Step 3: Update the contract-test PG factory.** In `ken/tests/test_store_contract.py` the PG factory is `_postgres_store(tmp_path)` (returns `PostgresStore(_PG_DSN)` after a TRUNCATE). Update it to TRUNCATE with CASCADE (tenants is now the FK parent), seed the tenants, and bind the store:

```python
def _postgres_store(tmp_path):
    # Clean backend per test; tenants is the FK parent so TRUNCATE needs CASCADE.
    import psycopg

    from ken.stores.postgres_store import PostgresStore

    with psycopg.connect(_PG_DSN) as c, c.cursor() as cur:
        cur.execute("TRUNCATE artifacts, questions, attempts, users, sessions, tenants CASCADE")
        cur.execute("INSERT INTO tenants (slug, name) VALUES ('default', 'Default'), ('contract', 'Contract')")
    return PostgresStore(_PG_DSN, "contract")
```

(`Attempt`/`Question` are already imported at the top of this file.)

- [ ] **Step 4: Run the contract test** (FileStore always; PG skips locally)

Run: `python -m pytest ken/tests/test_store_contract.py -v`
Expected: FileStore params PASS; PG params SKIP (no `KEN_TEST_DATABASE_URL`).

- [ ] **Step 5: Add the 2-tenant isolation PG test.** Append to `ken/tests/test_store_contract.py`:

```python
@pytest.mark.skipif(_PG_DSN is None, reason="KEN_TEST_DATABASE_URL unset")
def test_postgres_two_tenant_isolation(tmp_path):
    import psycopg
    from ken.stores.postgres_store import PostgresStore
    art = tmp_path / "a.md"
    art.write_text("Payment service publishes orders.\n", encoding="utf-8")
    with psycopg.connect(_PG_DSN) as c, c.cursor() as cur:
        cur.execute("TRUNCATE artifacts, questions, attempts, users, sessions, tenants CASCADE")
        cur.execute("INSERT INTO tenants (slug, name) VALUES ('a', 'A'), ('b', 'B')")
    a, b = PostgresStore(_PG_DSN, "a"), PostgresStore(_PG_DSN, "b")
    ra = a.register(str(art))                     # same path under both tenants
    rb = b.register(str(art))
    assert ra.artifact_id == rb.artifact_id       # path-only id; tenant is the discriminator
    assert [r.path for r in a.load_manifest()] == [str(art)]
    assert len(b.load_manifest()) == 1
    # an attempt under A is invisible to B
    from ken.models import Attempt
    a.append_attempt(Attempt("u", ra.artifact_id, "q1", "h", True, 1.0, "2026-06-24T00:00:00+00:00"))
    assert len(a.load_attempts()) == 1 and b.load_attempts() == []
    # B's questions don't leak into A
    b.save_questions(rb.artifact_id, "h", [Question(text="Q?")])
    assert a.load_questions(ra.artifact_id) == (None, [])
```

(Import `Question` at the top if not already.)

- [ ] **Step 6: Run** (PG skips locally; CI postgres job runs it)

Run: `python -m pytest ken/tests/test_store_contract.py -v`
Expected: FileStore PASS; PG tests SKIP locally.

- [ ] **Step 7: Confirm the api suite still green** (make_store default keeps handlers working)

Run: `python -m pytest ken-web/api/tests/ -q`
Expected: PASS (handlers still call `make_store()` → default; test_auth_api's `lambda: store` still matches the zero-arg calls).

- [ ] **Step 8: Commit**

```bash
git add ken/src/ken/stores/postgres_store.py ken-web/api/src/ken_web_api/deps.py ken/tests/test_store_contract.py
git commit -m "feat(ken): tenant-bound PostgresStore + make_store(tenant_slug); 2-tenant isolation test"
```

---

## Chunk 3: auth_store tenancy

### Task 3: `User.tenant_slug`, `create_user(tenant_slug)`, `create_tenant`

**Files:** Modify `ken-web/api/src/ken_web_api/auth_store.py`, `ken-web/api/tests/test_auth_store.py`

- [ ] **Step 1: Write the failing tests** (append to `test_auth_store.py`):

```python
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
    import pytest
    with pytest.raises(Exception):
        s.create_tenant("acme", "Acme2")


def test_create_user_defaults_tenant_to_default():
    s = FakeAuthStore()  # back-compat: 2-arg create_user lands in 'default'
    u = s.create_user("a@x.com", "h")
    assert u.tenant_slug == "default"
```

Move the top-level `import pytest` if the file already has one. Add a PG-gated variant asserting `PostgresAuthStore` round-trips `tenant_slug` (create_tenant → create_user(tenant_slug) → user_for_session.tenant_slug) — mirror the existing `pg_only` mark.

- [ ] **Step 2: Run to verify they fail**

Run: `python -m pytest ken-web/api/tests/test_auth_store.py -k "tenant" -v`
Expected: FAIL (`create_tenant` missing; `User` has no `tenant_slug`).

- [ ] **Step 3: Implement.** In `auth_store.py`:
  - `User` gains a **required** `tenant_slug` (no default — forces every read path to set it):
    ```python
    @dataclass(frozen=True)
    class User:
        id: int
        email: str
        tenant_slug: str
    ```
  - Add to the `AuthStore` Protocol: `def create_tenant(self, slug: str, name: str) -> None: ...` and change `create_user` to `def create_user(self, email: str, password_hash: str, tenant_slug: str = "default") -> User: ...`.
  - **FakeAuthStore**: store a `set` of tenant slugs; `create_tenant` raises on duplicate; `create_user` records `tenant_slug` and builds `User(id, email, tenant_slug)`; `user_for_session` returns the stored `User` (which now carries the slug — keep a `_by_id` of full `User`s). Update the existing `User(id=self._seq, email=e)` construction to include `tenant_slug`.
  - **PostgresAuthStore**:
    - `create_tenant`: `INSERT INTO tenants (slug, name) VALUES (%s, %s)` (duplicate → `UniqueViolation`).
    - `create_user`: `INSERT INTO users (email, password_hash, tenant_slug) VALUES (%s,%s,%s) RETURNING id, email, tenant_slug` → `User(uid, email, tslug)`.
    - `get_user_by_email`: `SELECT id, email, password_hash, tenant_slug …` → `User(id, email, tenant_slug), hash`.
    - `user_for_session`: `SELECT u.id, u.email, u.tenant_slug FROM sessions s JOIN users u … ` → `User(id, email, tenant_slug)`.

- [ ] **Step 4: Run to verify they pass**

Run: `python -m pytest ken-web/api/tests/test_auth_store.py -v`
Expected: PASS (new + existing; the existing 2-arg `create_user` tests still pass via the default).

- [ ] **Step 5: Commit**

```bash
git add ken-web/api/src/ken_web_api/auth_store.py ken-web/api/tests/test_auth_store.py
git commit -m "feat(ken-web): auth_store tenancy — User.tenant_slug, create_tenant, create_user(tenant_slug)"
```

---

## Chunk 4: API — Principal + tenant wiring

### Task 4: `Principal`, `require_user -> Principal`, route + handler wiring

**Files:** Modify `ken-web/api/src/ken_web_api/app.py`, `ken-web/api/tests/test_auth_api.py`

- [ ] **Step 1: Write the failing tests** (append to `test_auth_api.py`). First **fix the existing monkeypatch** (`_auth_client`, ~line 26): change `monkeypatch.setattr(deps, "make_store", lambda: store)` → `monkeypatch.setattr(deps, "make_store", lambda _slug=None: store)`. (This is the **only** `make_store` monkeypatch — `test_api.py` uses the real file backend and patches nothing, so don't hunt for one there.) Then add:

```python
def test_two_users_distinct_tenants_see_disjoint_data(tmp_path, monkeypatch):
    # Capture the tenant_slug make_store is called with, per request.
    calls = []
    c, auth, store = _auth_client(tmp_path, monkeypatch)
    monkeypatch.setattr(deps, "make_store", lambda slug=None: (calls.append(slug), store)[1])
    auth.create_tenant("a", "A"); auth.create_tenant("b", "B")
    auth.create_user("alice@x.com", hash_password("password1"), tenant_slug="a")
    c.post("/api/auth/login", json={"email": "alice@x.com", "password": "password1"})
    c.get("/api/coverage")
    assert calls[-1] == "a"   # store bound to Alice's tenant


def test_attempt_records_caller_tenant(tmp_path, monkeypatch):
    c, auth, store = _auth_client(
        tmp_path, monkeypatch,
        responses=["Q1?", '{"passed": true, "score": 0.9, "rationale":"ok"}'],
    )
    auth.create_tenant("a", "A")
    auth.create_user("a@x.com", hash_password("password1"), tenant_slug="a")
    c.post("/api/auth/login", json={"email": "a@x.com", "password": "password1"})
    art = tmp_path / "a.md"
    art.write_text("Payment service publishes orders.\n", encoding="utf-8")
    aid = c.post("/api/artifacts", json={"path": str(art)}).json()["artifact_id"]
    qid = c.get(f"/api/artifacts/{aid}/due").json()["questions"][0]["question_id"]
    c.post("/api/attempts", json={"artifact_id": aid, "question_id": qid, "answer": "x"})
    assert store.load_attempts()[0].person == "a@x.com"   # person still server-derived
```

> The auth-OFF `test_auth_off_endpoints_open_and_person_local` must still pass — its handlers now call `make_store(DEFAULT_TENANT)` → real `make_store` → FileStore (slug ignored). No change needed beyond it already not monkeypatching make_store.

- [ ] **Step 2: Run to verify they fail**

Run: `python -m pytest ken-web/api/tests/test_auth_api.py -k "tenant" -v`
Expected: FAIL (`make_store` not called with a tenant yet — `calls[-1]` is `None`/unset, or `create_tenant` missing on the path).

- [ ] **Step 3: Implement in `app.py`.** Add `Principal` and make `require_user` return it:

```python
from dataclasses import dataclass

@dataclass(frozen=True)
class Principal:
    email: str
    tenant_slug: str


def require_user(request: Request) -> Principal:
    if not deps.auth_enabled():
        return Principal(deps.DEFAULT_PERSON, deps.DEFAULT_TENANT)
    token = request.cookies.get(deps.SESSION_COOKIE)
    user = deps.make_auth_store().user_for_session(token, now=service.now_iso()) if token else None
    if user is None:
        raise HTTPException(status_code=401, detail="authentication required")
    return Principal(user.email, user.tenant_slug)
```

Then update the consumers:
- `me`: `def me(principal: Principal = Depends(require_user)) -> MeOut: return MeOut(email=principal.email)`.
- The **five data routes**: change `dependencies=[Depends(require_user)]` → a `principal: Principal = Depends(require_user)` parameter, and `store = deps.make_store()` → `store = deps.make_store(principal.tenant_slug)`. (`list_artifacts`, `register_artifact`, `get_due`, `get_detail`, `get_coverage`.)
- `post_attempt`: `def post_attempt(req: AttemptReq, principal: Principal = Depends(require_user))` → `store = deps.make_store(principal.tenant_slug)` and `person=principal.email`.

- [ ] **Step 4: Run to verify they pass + no regression**

Run: `python -m pytest ken-web/api/tests/ -v`
Expected: PASS (new tenant tests + all existing auth + auth-off tests).

- [ ] **Step 5: Commit**

```bash
git add ken-web/api/src/ken_web_api/app.py ken-web/api/tests/test_auth_api.py
git commit -m "feat(ken-web): require_user -> Principal{email,tenant_slug}; store bound to caller tenant"
```

---

## Chunk 5: admin CLI — create-tenant + add-user --tenant

### Task 5: tenant provisioning commands

**Files:** Modify `ken-web/api/src/ken_web_api/admin.py`, `ken-web/api/tests/test_admin.py`

- [ ] **Step 1: Write the failing tests** (modify `test_admin.py` — existing `add_user_to_store(s, email, pw)` callers must now pass a tenant and seed it):

```python
def test_add_user_to_store_assigns_tenant():
    s = FakeAuthStore()
    s.create_tenant("acme", "Acme")
    add_user_to_store(s, "a@x.com", "password1", tenant_slug="acme")
    got = s.get_user_by_email("a@x.com")
    assert got is not None and got[0].tenant_slug == "acme"


def test_create_tenant_to_store():
    from ken_web_api.admin import create_tenant_in_store
    s = FakeAuthStore()
    create_tenant_in_store(s, "acme", "Acme")
    # creating a user there now works
    add_user_to_store(s, "a@x.com", "password1", tenant_slug="acme")
    assert s.get_user_by_email("a@x.com") is not None
```

Update the EXISTING `add_user_to_store` tests (`test_add_user_stores_verifiable_hash`, `_rejects_weak_password`, `_duplicate_email_errors`) to seed a tenant and pass `tenant_slug="default"` (or `"acme"`) so they keep working with the new signature.

- [ ] **Step 2: Run to verify they fail**

Run: `python -m pytest ken-web/api/tests/test_admin.py -v`
Expected: FAIL (`add_user_to_store` has no `tenant_slug`; `create_tenant_in_store` missing).

- [ ] **Step 3: Implement in `admin.py`:**
  - `add_user_to_store(store, email, password, tenant_slug)` — add the param (keep the length guard first), `return store.create_user(email, hash_password(password), tenant_slug=tenant_slug)`.
  - `create_tenant_in_store(store, slug, name)` — `store.create_tenant(slug, name)`.
  - `add-user` subcommand: add a **required** `--tenant` arg; `_add_user_cli(email, tenant)` passes it through (the CLI does not pre-validate tenant existence beyond the FK — a bad slug surfaces as the store's FK error, caught and printed).
  - New `create-tenant` subcommand: `ken-web-admin create-tenant <slug> [--name NAME]` → `_create_tenant_cli` reads `KEN_DATABASE_URL`, calls `create_tenant_in_store(PostgresAuthStore(dsn), slug, name or slug)`, prints/exits like `add-user`.
  - Wire both subcommands in `main`'s argparse.

- [ ] **Step 4: Run to verify they pass**

Run: `python -m pytest ken-web/api/tests/test_admin.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add ken-web/api/src/ken_web_api/admin.py ken-web/api/tests/test_admin.py
git commit -m "feat(ken-web): ken-web-admin create-tenant + add-user --tenant"
```

---

## Final verification

- [ ] **Run all suites + ruff**

```bash
python -m pytest ken/tests/ ken-web/api/tests/ -q
python -m ruff check ken ken-web/api
cd ken-web/web && npx vitest run && npm run build
```
Expected: all green (PG-gated tests SKIP locally / run in CI's postgres job); web unchanged but still green; ruff clean.

- [ ] **README:** add a "Tenancy" subsection under Authentication — create a tenant with `ken-web-admin create-tenant <slug>`, assign users with `add-user <email> --tenant <slug>`, and the `migrate-tenancy.sql` step for existing DBs; note one tenant per user and that file/auth-off is a single `default` tenant. Commit.

- [ ] **Push branch + PR** (`feat/ken-web-tenancy`), wait for CI 9 jobs green (the postgres job applies the new `init.sql` and runs the 2-tenant isolation test), then merge.
