# Design Spec — ken-web S2: Postgres graduation (sync, dual-backend)

- **Date:** 2026-06-23
- **Status:** Design (brainstorming output) — pending spec review + user approval
- **Builds on:** ken v0/v1 + ken-web v0.1 (all merged). The deferred S2 from the productization decomposition.
- **Decisions locked:** **sync driver (psycopg3)** — ken-core/service/CLI stay synchronous; FastAPI runs sync handlers in its threadpool. **Dual backend:** `KEN_DATABASE_URL` set → Postgres, unset → existing file storage (CLI/local stays file-based, unbroken). New module placement: code in the existing `ken/` (storage layer) + `ken-web/api` (wiring).

---

## 1. Goal

Let ken-web persist to **Postgres** for multi-user robustness, **without breaking the CLI/local file workflow**. Introduce a storage abstraction so the same orchestration runs over either backend, selected by env.

## 2. Key insight (why this is small)

The pure derivations — `schedule.rebuild`/`due`, `vouch.is_vouched`, `coverage.compute_coverage_v1` — **already operate on plain rows** (lists of `Question`/`Attempt`/`ArtifactRef`), independent of where they came from. So the only thing that changes is the **read/write boundary**. No derivation logic changes; no view is needed.

## 3. Storage abstraction (ken-core)

Introduce a single `KenStore` Protocol (`ken/src/ken/store.py`) covering exactly the persistence operations the service uses:

```python
class KenStore(Protocol):
    def load_manifest(self) -> list[ArtifactRef]: ...
    def register(self, path: str) -> ArtifactRef: ...
    def load_questions(self, artifact_id: str) -> tuple[str | None, list[Question]]: ...
    def save_questions(self, artifact_id: str, content_hash: str, qs: list[Question]) -> None: ...   # replace, fail-loud
    def append_attempt(self, attempt: Attempt) -> None: ...   # append-only, fail-loud
    def load_attempts(self) -> list[Attempt]: ...
```

- **`current_hash(path)` stays OUT of the store** — it reads the artifact file from disk (artifacts live in git/the filesystem; the DB is an index, not the archive — mirrors Nexus principle #5). Both backends share `registry.current_hash`.
- `ArtifactRef.content_hash` is still computed live via `current_hash` when a manifest row is loaded (so freshness always compares against current content), in both backends.

Two implementations:
- **`FileStore`** (`ken/src/ken/stores/file_store.py`) — thin wrapper over the existing `registry`/`questions`/`attempt` module functions (file paths injected at construction). **Behavior identical to today.**
- **`PostgresStore`** (`ken/src/ken/stores/postgres_store.py`) — psycopg3 (sync), parameterized SQL only, the 3 tables below. `save_questions` = delete-then-insert for the artifact (replace), **reusing `questions.make_question_id`** for id assignment when `q.id` is falsy, and storing `idx` so `load_questions` returns `ORDER BY idx` — making ids and order **contract-equivalent to FileStore**. `register` is **idempotent on `path`** (`INSERT ... ON CONFLICT (path) DO NOTHING` then `SELECT`). `append_attempt` = INSERT (append-only). All writes **raise on failure** (**fail-loud**, no swallow).

**`service.*` is refactored to take a `store: KenStore`** instead of path-string args. `current_hash` is still called directly (filesystem). CLI builds a `FileStore` from its `--manifest/--questions/--ledger` options (unchanged behavior/output). The API builds the store from env (below).

## 4. Schema (`ken/db/init.sql`, 3 tables — no view)

```sql
CREATE TABLE artifacts (
    artifact_id TEXT PRIMARY KEY,
    path        TEXT NOT NULL UNIQUE
);
CREATE TABLE questions (
    artifact_id  TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    question_id  TEXT NOT NULL,
    idx          INTEGER NOT NULL,
    text         TEXT NOT NULL,
    PRIMARY KEY (artifact_id, question_id)
);
CREATE INDEX idx_questions_artifact ON questions (artifact_id);
CREATE TABLE attempts (
    id           BIGSERIAL PRIMARY KEY,
    person       TEXT NOT NULL,
    artifact_id  TEXT NOT NULL,
    question_id  TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    passed       BOOLEAN NOT NULL,
    score        DOUBLE PRECISION NOT NULL,
    ts           TIMESTAMPTZ NOT NULL
);
CREATE INDEX idx_attempts_question ON attempts (question_id);
```

- `artifacts` = the registry mapping only (hash computed live, never stored — matches `registry.load_manifest`).
- `questions` per artifact; `save_questions` replaces the artifact's whole set (delete by `artifact_id`, insert new) bound to `content_hash`.
- `attempts` append-only; `load_attempts` returns all (the derivations recompute state by replay). At single-team scale this full scan is fine; an `artifact_id`/`ts` index is present for later.
- **No `vouch`/`coverage` table or view** — derived in Python from rows (storage-agnostic; reuses v1 logic unchanged).

## 5. Backend selection & config (`ken-web/api`)

`deps.make_store()` (new): if `KEN_DATABASE_URL` is set → `PostgresStore(dsn)`; else `FileStore(paths from KEN_DATA_DIR/...)`. Handlers obtain the store via `deps.make_store()` at request time (same seam style as `deps.make_llm`). The API’s 5 endpoints call `service.*(store=..., llm=...)`.

- Schema applied via a documented `psql "$KEN_DATABASE_URL" -f ken/db/init.sql` (no new CLI subcommand — YAGNI). Provide a minimal `ken/docker-compose.yml` (one Postgres) for local self-host; otherwise any Postgres via `KEN_DATABASE_URL`.

## 6. Migration

**Fresh start (walking skeleton).** Switching to Postgres begins empty; file remains the default so existing local data is untouched. A one-shot file→Postgres importer is **deferred** (non-goal).

## 7. Error handling & invariants (preserved)

- `save_questions`/`append_attempt` **fail-loud** in BOTH backends (raise on IO/DB error; never silently drop). `append_attempt` is append-only.
- Derivations stay pure with explicit `now`; **no git** dependency.
- Postgres: parameterized SQL only (no string interpolation); **connection per request** — `make_store()` constructs it, no shared pool (simplest; pool tuning is a non-goal).
- API key never reaches client (unchanged); `person` informational (unchanged).

## 8. Testing

- **Shared contract test** (`ken/tests/test_store_contract.py`): one parametrized suite asserting the `KenStore` contract — register/load_manifest round-trip **AND re-register idempotent on path**; save_questions replace + hash + **stable question ids (`make_question_id`) and load order (`idx`)**; append_attempt/load_attempts order; fail-loud — run against **FileStore always**, and against **PostgresStore only when `KEN_TEST_DATABASE_URL` is set** (mirrors nexus's `NEXUS_TEST_DB_URL` integration gate; skipped otherwise). This proves both backends satisfy the same contract.
- **No regression:** the existing ken suite, `test_service.py` (updated to inject a `FileStore`), and the `ken-web/api` tests (file backend, FakeLLM) stay green. CLI output unchanged.
- **CI:** add a Postgres service container to a `ken (pytest, integration)` job (or extend the api job) that sets `KEN_TEST_DATABASE_URL` so the PostgresStore contract runs in CI. The default `ken (pytest)` job stays DB-free (file backend).

## 9. Non-goals (this slice)

File→Postgres data migration tool; connection-pool tuning / advanced concurrency; multi-tenancy (S6); materialized views / DB-side derivation; auth. Single team, single database.

## 10. Success criteria

- With `KEN_DATABASE_URL` set, the full ken-web flow (register → due → attempt → coverage) persists to and reads from Postgres; with it unset, everything still uses files and all existing tests pass unchanged.
- FileStore and PostgresStore both pass the same `KenStore` contract test (PG gated on `KEN_TEST_DATABASE_URL`).
- CLI behavior/output unchanged; `service.*` now store-injected.
- fail-loud + append-only + pure-derivation + no-git invariants hold on both backends.

---

## Implementation outline (for writing-plans)

1. `ken/src/ken/store.py` — `KenStore` Protocol.
2. `ken/src/ken/stores/file_store.py` — wraps existing registry/questions/attempt functions; `ken/tests/test_store_contract.py` (FileStore param).
3. Refactor `ken/src/ken/service.py` to take `store: KenStore` (keep `current_hash` direct); refactor `cli.py` to build a `FileStore`; update `test_service.py`. **All existing tests green.**
4. `ken/db/init.sql` + `ken/src/ken/stores/postgres_store.py` (psycopg3, per-request connection, `make_question_id`/`idx` parity, `register` idempotent on path); extend the contract test with the PG-gated param; `ken/docker-compose.yml` + documented `psql -f` schema apply (no new CLI).
5. `ken-web/api` `deps.make_store()` + handlers use it; api tests stay file-based green.
6. CI: Postgres-service integration job exporting `KEN_TEST_DATABASE_URL`; README/run-guide update (set `KEN_DATABASE_URL` for Postgres).
