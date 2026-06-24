# Design Spec — ken-web tenancy: core per-tenant data isolation

**Date:** 2026-06-24
**Status:** approved design → spec
**Milestone:** C (SaaS) — first slice
**Depends on:** S6 auth gating (PR #43): `users`/`sessions`, `require_user`, Postgres-only auth.

## 1. Goal & scope

Today every authenticated user shares **one** dataset. This slice makes data **tenant-isolated**:
each user belongs to exactly one tenant (org), and every artifact / question / attempt is scoped to
that tenant. A user only ever sees and writes their own tenant's data.

Settled in brainstorming:
- **Membership: one tenant per user** (`users.tenant_slug`). Multi-org, org-switcher, invites,
  roles/admin are a **deferred follow-on**.
- **Isolation: app-enforced row-level**, with the **tenant-bound store as the single enforcement
  boundary**. (Not Postgres RLS — that's a deferred defense-in-depth option.)
- Tenancy is **Postgres-only**, layered on S6 auth (`KEN_AUTH=1`). The file backend stays a
  single-tenant local/dev store; auth-OFF is a single implicit tenant. The `ken` engine and CLI
  are untouched.

## 2. Tenant key: slug (not a surrogate id)

A tenant is identified by a **slug** (`TEXT`, e.g. `acme`), used as the tenant key everywhere:
`tenants.slug` is the PK, `users.tenant_slug` and the three data tables carry `tenant_slug`, and the
store binds to a slug. This gives a **stable, human-meaningful** key and a fixed `DEFAULT_TENANT =
"default"` for the auth-OFF / migration path, without resolving a surrogate id at runtime.

## 3. Schema (`ken/db/init.sql` for fresh installs + `ken/db/migrate-tenancy.sql` for existing)

`artifact_id` stays `sha256(path)[:12]` (path-only); **`tenant_slug` is the discriminator**, so the
same path in two tenants is two isolated rows under a composite key.

Fresh schema (`init.sql`):

```sql
CREATE TABLE tenants (
    slug       TEXT PRIMARY KEY,
    name       TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
INSERT INTO tenants (slug, name) VALUES ('default', 'Default');

-- users (S6) gains tenant_slug
ALTER TABLE users ADD COLUMN tenant_slug TEXT NOT NULL DEFAULT 'default' REFERENCES tenants(slug);
-- (on a fresh build, define users with the column inline instead of ALTER)

-- artifacts: composite PK (tenant_slug, artifact_id); path unique PER TENANT
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
```

> **`init.sql` rewrite note:** the existing `artifacts`/`questions`/`attempts` definitions are
> replaced by the above (the S6 `users`/`sessions` block stays, with `users` gaining `tenant_slug`).
> Keep `idx_sessions_user`. The `default` tenant row must exist before any FK insert.

Migration (`ken/db/migrate-tenancy.sql`, for a DB already on the S6 schema; run once):

```sql
BEGIN;
CREATE TABLE tenants (slug TEXT PRIMARY KEY, name TEXT NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT now());
INSERT INTO tenants (slug, name) VALUES ('default', 'Default');

ALTER TABLE users    ADD COLUMN tenant_slug TEXT NOT NULL DEFAULT 'default' REFERENCES tenants(slug);
ALTER TABLE artifacts ADD COLUMN tenant_slug TEXT NOT NULL DEFAULT 'default' REFERENCES tenants(slug);
ALTER TABLE questions ADD COLUMN tenant_slug TEXT NOT NULL DEFAULT 'default' REFERENCES tenants(slug);
ALTER TABLE attempts  ADD COLUMN tenant_slug TEXT NOT NULL DEFAULT 'default' REFERENCES tenants(slug);

-- repoint keys to composite (existing rows already backfilled to 'default' by the DEFAULT)
ALTER TABLE artifacts DROP CONSTRAINT artifacts_pkey, ADD PRIMARY KEY (tenant_slug, artifact_id);
ALTER TABLE artifacts DROP CONSTRAINT artifacts_path_key, ADD UNIQUE (tenant_slug, path);
ALTER TABLE questions DROP CONSTRAINT questions_pkey, ADD PRIMARY KEY (tenant_slug, artifact_id, question_id);
CREATE INDEX idx_questions_tenant_artifact ON questions (tenant_slug, artifact_id);
CREATE INDEX idx_attempts_tenant_question ON attempts (tenant_slug, question_id);
COMMIT;
```

> Constraint names (`artifacts_pkey`, `artifacts_path_key`, `questions_pkey`) are Postgres defaults
> for the S6 schema; the implementer must verify them against the live DB (or `\d artifacts`) and
> adjust. The migration is **run-once** (not idempotent); document that.

## 4. Tenant-bound store

`PostgresStore` gains a tenant binding; the `KenStore` Protocol and the service layer are **unchanged**
(the tenant is bound at construction, not threaded through method signatures):

- `PostgresStore(dsn: str, tenant_slug: str)`. **Every** query adds `tenant_slug = %s`:
  - `load_manifest` → `... WHERE tenant_slug = %s`
  - `register` → `INSERT (tenant_slug, artifact_id, path) ... ON CONFLICT (tenant_slug, path) DO NOTHING`, then `SELECT ... WHERE tenant_slug = %s AND path = %s`
  - `load_questions` / `save_questions` (delete-then-insert) / `append_attempt` / `load_attempts` all carry `tenant_slug`.
- `deps.make_store(tenant_slug: str) -> KenStore`:
  - Postgres → `PostgresStore(KEN_DATABASE_URL, tenant_slug)`.
  - File → `FileStore(...)` (**single-tenant**; ignores `tenant_slug` — local/dev).
- `FileStore` is unchanged (one set of files = one implicit tenant).

The store is the **only** place tenant scoping is applied; `service.*` stays tenant-agnostic and is
not modified.

## 5. Tenant resolution (layered on S6 auth)

- `User` (in `auth_store.py`) gains `tenant_slug: str`. `AuthStore.user_for_session` and
  `get_user_by_email` return it (the Postgres query selects `users.tenant_slug`; the Fake stores it).
- A `Principal` value replaces the bare email returned by `require_user`:
  ```python
  @dataclass(frozen=True)
  class Principal:
      email: str
      tenant_slug: str
  ```
  `require_user(request) -> Principal`. Auth-OFF → `Principal(DEFAULT_PERSON, DEFAULT_TENANT)`
  (`"local"`, `"default"`). Auth-ON → from the session's user.
- Handlers change from `store = deps.make_store()` + `person = <email>` to:
  ```python
  store = deps.make_store(principal.tenant_slug)
  # post_attempt: person = principal.email
  ```
  The five data routes take `principal: Principal = Depends(require_user)` (replacing the
  `dependencies=[...]` form so they can read the tenant); `post_attempt` uses both fields.
- **`/api/auth/me` is the 6th `require_user` consumer** (today `person: str = Depends(require_user)`
  → `MeOut(email=person)`). It must migrate to `principal: Principal = Depends(require_user)` →
  `MeOut(email=principal.email)`, or it hands a `Principal` where a string is expected. (`login`/
  `logout` do not consume `require_user`, so they're unaffected.)
- `deps`: add `DEFAULT_TENANT = "default"`.

## 6. Provisioning (CLI extension)

Extend `ken-web-admin`:
- `create-tenant <slug> [--name NAME]` → insert a tenant (error if slug exists). New
  `auth_store` method `create_tenant(slug, name)` (Postgres + Fake).
- `add-user <email> --tenant <slug>` → the existing `add-user` gains a **required** `--tenant`;
  it validates the tenant exists, then creates the user with that `tenant_slug`. `create_user`
  gains a `tenant_slug` parameter (Postgres + Fake + `add_user_to_store`). **Existing `test_admin.py`
  callers** of `add_user_to_store(store, email, pw)` must pass the new `tenant_slug` arg (after
  seeding the tenant in the Fake).

## 7. Error handling & integrity (the isolation invariants)

- **Cross-tenant access is structurally impossible through the store**: a handler can only ever
  construct a store bound to the caller's `principal.tenant_slug`, and every query filters on it.
  Requesting another tenant's `artifact_id` directly (e.g. `GET /api/artifacts/{id}/detail`) yields
  **no rows for this tenant** → `KeyError`/`[]` → 404/empty, never the other tenant's data.
- `person` and `tenant_slug` are **both server-derived** from the session; never client-supplied.
- FK to `tenants(slug)` on every tenant-scoped table; the `default` tenant is seeded so auth-OFF /
  migrated writes satisfy the FK.
- Writes stay fail-loud (psycopg `with` rolls back). The migration is wrapped in a transaction.
- File backend: single-tenant; `make_store` ignores the slug, behavior identical to today.

## 8. Testing

- **Store contract (`test_store_contract.py`):** PostgresStore is now `PostgresStore(dsn, tenant)`;
  the shared contract runs under one fixed test tenant. Use `TRUNCATE artifacts, questions, attempts,
  users, sessions, tenants CASCADE` (tenants is now the FK parent — without CASCADE the truncate
  fails), then **re-seed** the test tenant + `default` **before** the first `register` (FK).
- **Fix existing zero-arg `make_store` monkeypatches** (the single most likely CI breakage): both
  `test_api.py` and `test_auth_api.py` patch `deps.make_store` with `lambda: store` — after the
  signature becomes `make_store(tenant_slug)` these raise `TypeError`. Change them to
  `lambda _slug: store` (or `lambda *_: store`).
- **PG-gated 2-tenant isolation test:** register artifact P under tenant A and (same path) under
  tenant B; assert A's `load_manifest`/`coverage` show only A's row; B sees only B's; an attempt
  written under A is invisible to B's `load_attempts`. Prove the composite key separates same-path
  artifacts.
- **auth_store:** `User.tenant_slug` round-trips (Fake + PG); `user_for_session` returns it;
  `create_tenant` (+ duplicate-slug error); `create_user(tenant_slug=...)`.
- **api (FakeAuthStore, KEN_AUTH=1):** a logged-in user's requests hit only their tenant (monkeypatch
  `make_store` to assert it's called with the session's `tenant_slug`); a second user in a different
  tenant sees a disjoint dataset; directly requesting another tenant's `artifact_id` → 404/empty;
  the stored attempt carries the caller's `tenant_slug` + `person`. auth-OFF → `DEFAULT_TENANT`.
- **CLI:** `create-tenant` (+ duplicate); `add-user --tenant` validates tenant exists and stores the
  user under it; missing `--tenant` errors.
- **Migration (PG-gated):** apply S6 schema + seed rows → run `migrate-tenancy.sql` → existing rows
  are under `default`, composite PKs/uniques in place, default tenant present.

## 9. Non-goals (this slice)

Multi-org-per-user, org switcher, invites, roles/admin; **filesystem-level artifact isolation**
(the same `path` resolves to the same on-disk file across tenants — only the DB rows are isolated;
true per-tenant artifact storage/namespacing is a later concern); billing; self-serve signup;
Postgres RLS; renaming a tenant slug.

## 10. Success criteria

- With `KEN_AUTH=1` + Postgres, two users in different tenants have fully disjoint
  artifacts/questions/attempts/coverage; neither can reach the other's data by any API path.
- `ken-web-admin create-tenant` + `add-user --tenant` provision an isolated tenant.
- Existing single-team data migrates cleanly into the `default` tenant; those users keep their data.
- File backend + auth-OFF behave exactly as today (single implicit `default` tenant).
- `ken` engine, `ken` CLI, `KenStore` Protocol, and `service.*` are unchanged; CI green.

## Implementation outline (for writing-plans)

1. `init.sql` rewrite (composite keys + tenants + users.tenant_slug + seed default) and
   `migrate-tenancy.sql`; extend the contract-test TRUNCATE/seed.
2. `PostgresStore(dsn, tenant_slug)` — thread `tenant_slug` through all six methods; `deps.make_store(tenant_slug)` + `DEFAULT_TENANT`. (Contract test under one tenant + the 2-tenant isolation test.)
3. `auth_store`: `User.tenant_slug`; `create_tenant`; `create_user(tenant_slug=...)`;
   `user_for_session`/`get_user_by_email` return the slug (Fake + Postgres).
4. `app`: `Principal{email, tenant_slug}`; `require_user -> Principal`; the five data routes **and
   `/api/auth/me`** take `principal: Principal`; handlers use `make_store(principal.tenant_slug)` and
   `person=principal.email`. Fix the existing zero-arg `make_store` monkeypatches in `test_api.py`/
   `test_auth_api.py` (→ `lambda _slug: store`).
5. `admin`: `create-tenant`; `add-user --tenant` (required).
6. Verify CI green; README tenancy section (create-tenant, add-user --tenant, the migration step).
