# ken-web S2 — Postgres Graduation (sync, dual-backend) — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** ken-web persists to Postgres for multi-user use without breaking the file/CLI workflow — via a `KenStore` Protocol (FileStore + PostgresStore), sync psycopg3, backend selected by `KEN_DATABASE_URL`.

**Architecture:** Introduce `ken.store.KenStore` (Protocol) + two impls. The pure derivations (`schedule`/`vouch`/`coverage`) already work on rows and don't change. `service.*` is refactored to take a `store` instead of path strings; CLI builds a `FileStore` (behavior unchanged); the API builds the store from env. PostgresStore is a sync psycopg3 backend with a per-request connection; its tests are gated on `KEN_TEST_DATABASE_URL` (nexus pattern).

**Tech Stack:** Python 3.13, psycopg3 (sync, optional `ken[postgres]` extra), Postgres 16; pytest; FastAPI (sync handlers in threadpool).

**Spec:** `docs/superpowers/specs/2026-06-23-ken-web-s2-postgres-graduation-design.md`

**Invariants (both backends):** `save_questions`/`append_attempt` **fail-loud** (raise); attempts **append-only**; derivations **pure** (unchanged); **no git**; **parameterized SQL only**. `current_hash` reads the artifact file from disk (NOT in the store).

---

## File structure

```
ken/src/ken/store.py                 # NEW: KenStore Protocol
ken/src/ken/stores/__init__.py       # NEW
ken/src/ken/stores/file_store.py     # NEW: FileStore (wraps registry/questions/attempt fns)
ken/src/ken/stores/postgres_store.py # NEW: PostgresStore (psycopg3, lazy import)
ken/src/ken/service.py               # MODIFY: path args -> store: KenStore
ken/src/ken/cli.py                   # MODIFY: build FileStore from --manifest/--questions/--ledger
ken/db/init.sql                      # NEW: 3 tables
ken/docker-compose.yml               # NEW: one Postgres for local self-host
ken/pyproject.toml                   # MODIFY: [postgres] optional extra (psycopg[binary])
ken/tests/test_store_contract.py     # NEW: parametrized contract (FileStore always; PG gated)
ken/tests/test_service.py            # MODIFY: inject FileStore
ken-web/api/.../deps.py              # MODIFY: make_store() (env-selected)
ken-web/api/.../app.py               # MODIFY: handlers pass store to service.*
.github/workflows/ci.yml             # MODIFY: add ken (pytest, postgres) job
ken-web/README.md                    # MODIFY: KEN_DATABASE_URL run note
```

---

## Chunk 1: abstraction + FileStore + service/cli refactor (all green on file)

### Task 1: `KenStore` Protocol

**Files:** Create `ken/src/ken/store.py`; (no test — it's a Protocol, exercised by Task 2's contract test)

- [ ] **Step 1: implement**
```python
from __future__ import annotations
from typing import Protocol, runtime_checkable
from ken.models import ArtifactRef, Attempt, Question

@runtime_checkable
class KenStore(Protocol):
    def load_manifest(self) -> list[ArtifactRef]: ...
    def register(self, path: str) -> ArtifactRef: ...
    def load_questions(self, artifact_id: str) -> tuple[str | None, list[Question]]: ...
    def save_questions(self, artifact_id: str, content_hash: str, questions: list[Question]) -> None: ...
    def append_attempt(self, attempt: Attempt) -> None: ...
    def load_attempts(self) -> list[Attempt]: ...
```
*(`current_hash(path)` is intentionally NOT on the store — it reads the artifact file from disk via `registry.current_hash`; both backends and `service` call it directly.)*
- [ ] **Step 2: commit** `feat(ken): KenStore storage Protocol`

### Task 2: FileStore + contract test (FileStore param)

**Files:** Create `ken/src/ken/stores/__init__.py`, `ken/src/ken/stores/file_store.py`; Test `ken/tests/test_store_contract.py`

- [ ] **Step 1: failing contract test** (parametrized; only FileStore for now)
```python
import pytest
from ken.models import Question, Attempt

def _file_store(tmp_path):
    from ken.stores.file_store import FileStore
    return FileStore(manifest=str(tmp_path/"m.yaml"),
                     questions=str(tmp_path/"q.json"),
                     ledger=str(tmp_path/"l.jsonl"))

STORE_FACTORIES = [("file", _file_store)]   # PG param added in Task 6 (gated)

@pytest.fixture(params=[f for _, f in STORE_FACTORIES], ids=[n for n, _ in STORE_FACTORIES])
def store(request, tmp_path):
    return request.param(tmp_path)

def test_register_roundtrip_and_idempotent(store, tmp_path):
    art = tmp_path/"a.md"; art.write_text("hello\n", encoding="utf-8")
    r1 = store.register(str(art))
    r2 = store.register(str(art))                      # idempotent on path
    assert r1.artifact_id == r2.artifact_id
    man = store.load_manifest()
    assert len(man) == 1 and man[0].path == str(art) and man[0].content_hash  # hash live

def test_save_questions_replace_hash_ids_order(store):
    store.save_questions("a1", "sha256:h1", [Question(id="", text="Q1"), Question(id="", text="Q2")])
    h, qs = store.load_questions("a1")
    assert h == "sha256:h1" and [q.text for q in qs] == ["Q1", "Q2"]   # order preserved
    from ken.questions import make_question_id
    assert qs[0].id == make_question_id("a1", "sha256:h1", 0)           # stable id scheme
    store.save_questions("a1", "sha256:h2", [Question(id="", text="NEW")])  # replace
    h2, qs2 = store.load_questions("a1")
    assert h2 == "sha256:h2" and [q.text for q in qs2] == ["NEW"]

def test_attempts_append_only_in_order(store):
    a = lambda p, ts: Attempt("kr","a1","q1","sha256:h",p,1.0,ts)
    store.append_attempt(a(True,  "2026-06-20T00:00:00Z"))
    store.append_attempt(a(False, "2026-06-20T01:00:00Z"))
    got = store.load_attempts()
    assert [x.passed for x in got] == [True, False]

def test_load_absent_is_empty(store):
    assert store.load_manifest() == [] and store.load_questions("nope") == (None, []) and store.load_attempts() == []

def test_append_attempt_fail_loud(tmp_path):
    from ken.stores.file_store import FileStore
    s = FileStore(manifest="x", questions="x",
                  ledger=str(tmp_path/"nope"/"x.jsonl"), make_parents=False)
    with pytest.raises(OSError):  # missing parent dir -> FileNotFoundError (subclass of OSError)
        s.append_attempt(Attempt("k","a","q","h",True,1.0,"2026-06-20T00:00:00Z"))
```
- [ ] **Step 2:** run → FAIL.
- [ ] **Step 3: implement** `file_store.py` — wrap existing functions, paths held on the instance:
```python
from __future__ import annotations
from ken.models import ArtifactRef, Attempt, Question
from ken.registry import load_manifest as _load_manifest, register as _register
from ken.questions import load_questions as _load_questions, save_questions as _save_questions
from ken.attempt import append_attempt as _append_attempt, load_attempts as _load_attempts

class FileStore:
    def __init__(self, *, manifest: str, questions: str, ledger: str, make_parents: bool = True):
        self._manifest, self._questions, self._ledger, self._mp = manifest, questions, ledger, make_parents
    def load_manifest(self) -> list[ArtifactRef]:
        return _load_manifest(self._manifest)
    def register(self, path: str) -> ArtifactRef:
        return _register(path, manifest_path=self._manifest)
    def load_questions(self, artifact_id: str) -> tuple[str | None, list[Question]]:
        return _load_questions(artifact_id, store_path=self._questions)
    def save_questions(self, artifact_id: str, content_hash: str, questions: list[Question]) -> None:
        _save_questions(artifact_id, content_hash, questions, store_path=self._questions, make_parents=self._mp)
    def append_attempt(self, attempt: Attempt) -> None:
        _append_attempt(attempt, ledger_path=self._ledger, make_parents=self._mp)
    def load_attempts(self) -> list[Attempt]:
        return _load_attempts(self._ledger)
```
- [ ] **Step 4:** run → PASS; `cd ken && python -m ruff check src tests`. **Step 5:** commit `feat(ken): FileStore + KenStore contract test`.

### Task 3: refactor `service.py` to take a `store`

**Files:** Modify `ken/src/ken/service.py`; Modify `ken/tests/test_service.py`

- [ ] **Step 1:** Capture baseline: `cd ken && python -m pytest -q` (record count). 
- [ ] **Step 2:** Change every `service` function from path-string params (`manifest`, `questions_store`, `ledger`) to a single `store: KenStore`. Internals call `store.load_manifest()/register()/load_questions()/save_questions()/append_attempt()/load_attempts()` instead of the module functions. **Keep** `registry.current_hash(path)` and `Path(ref.path).read_text(...)` direct (filesystem). `find_ref` becomes `next(r for r in store.load_manifest() if r.artifact_id == aid)`. Signatures e.g.:
  - `register_artifact(path, *, store)`, `ensure_questions(artifact_id, *, store, llm, n)`, `due_items(*, store, now)`, `grade_set(text, qa_pairs, *, llm)` (unchanged — no storage), `coverage_report(*, store)`, `list_artifacts(*, store)`, `grade_answer(artifact_id, question_id, answer, *, person, store, llm, now)`, `remediate(...)` (unchanged).
- [ ] **Step 3:** Update `ken/tests/test_service.py` — replace the `_seed`/path args with a `FileStore` built on tmp paths, inject `store=...` into every service call. (Pure assertions unchanged.)
- [ ] **Step 4:** Refactor `ken/src/ken/cli.py` — each command builds `store = FileStore(manifest=manifest, questions=questions, ledger=ledger)` from its existing options and passes `store=store` to `service.*`. **Output/behavior unchanged.** `register` → `service.register_artifact(path, store=store)`. **`cli._find_ref` currently calls `service.find_ref(manifest, artifact_id)`** — update it to the new store-based form (e.g. `next((r for r in store.load_manifest() if r.artifact_id == aid), None)`); the `save-questions`, `record-attempt`, and `review` commands use `_find_ref`, so thread the store through them (build the store in each, pass it). Confirm `cli.py` imports/compiles after the signature change.
- [ ] **Step 5:** Run `cd ken && python -m pytest -q` → **same passing count as Step 1 baseline**; `test_cli_v1.py` green; ruff clean. **Step 6:** commit `refactor(ken): service/cli take a KenStore (file default; behavior unchanged)`.

---

## Chunk 2: PostgresStore + wiring + CI

### Task 4: schema + Postgres optional dep + docker-compose

**Files:** Create `ken/db/init.sql`, `ken/docker-compose.yml`; Modify `ken/pyproject.toml`

- [ ] **Step 1:** `ken/db/init.sql` — the 3 tables exactly as the spec §4 (artifacts/questions/attempts + indexes; no view).
- [ ] **Step 2:** `ken/docker-compose.yml` — one `postgres:16` service (db `ken`, user/pw `ken`, port e.g. 5434 to avoid nexus's), a healthcheck, and a note that `init.sql` is applied via `psql -f` (or mount it to `/docker-entrypoint-initdb.d`).
- [ ] **Step 3:** `ken/pyproject.toml` — add `[project.optional-dependencies] postgres = ["psycopg[binary]>=3.2"]` (so the default file-backend install stays light). Keep `dev` as-is.
- [ ] **Step 4: commit** `feat(ken): postgres schema, optional extra, docker-compose`.

### Task 5: `PostgresStore`

**Files:** Create `ken/src/ken/stores/postgres_store.py`

- [ ] **Step 1:** Implement (psycopg3 sync, **lazy import** so file-only installs don't need it; per-request connection; parameterized SQL only):
```python
from __future__ import annotations
from ken.models import ArtifactRef, Attempt, Question
from ken.registry import current_hash, _artifact_id
from ken.questions import make_question_id

class PostgresStore:
    def __init__(self, dsn: str):
        self._dsn = dsn
    def _conn(self):
        import psycopg  # lazy
        return psycopg.connect(self._dsn)
    def load_manifest(self) -> list[ArtifactRef]:
        with self._conn() as c, c.cursor() as cur:
            cur.execute("SELECT artifact_id, path FROM artifacts ORDER BY path")
            return [ArtifactRef(aid, path, current_hash(path)) for aid, path in cur.fetchall()]
    def register(self, path: str) -> ArtifactRef:
        aid = _artifact_id(path)
        with self._conn() as c, c.cursor() as cur:
            cur.execute("INSERT INTO artifacts (artifact_id, path) VALUES (%s,%s) "
                        "ON CONFLICT (path) DO NOTHING", (aid, path))
            cur.execute("SELECT artifact_id FROM artifacts WHERE path=%s", (path,))
            aid = cur.fetchone()[0]
        return ArtifactRef(aid, path, current_hash(path))
    def load_questions(self, artifact_id):
        with self._conn() as c, c.cursor() as cur:
            cur.execute("SELECT content_hash, question_id, text FROM questions "
                        "WHERE artifact_id=%s ORDER BY idx", (artifact_id,))
            rows = cur.fetchall()
        if not rows:
            return None, []
        return rows[0][0], [Question(id=qid, text=text) for _, qid, text in rows]
    def save_questions(self, artifact_id, content_hash, questions):
        with self._conn() as c, c.cursor() as cur:           # transaction; raises on failure (fail-loud)
            cur.execute("DELETE FROM questions WHERE artifact_id=%s", (artifact_id,))
            for i, q in enumerate(questions):
                qid = q.id or make_question_id(artifact_id, content_hash, i)
                cur.execute("INSERT INTO questions (artifact_id, content_hash, question_id, idx, text) "
                            "VALUES (%s,%s,%s,%s,%s)", (artifact_id, content_hash, qid, i, q.text))
    def append_attempt(self, a: Attempt):
        with self._conn() as c, c.cursor() as cur:
            cur.execute("INSERT INTO attempts (person, artifact_id, question_id, content_hash, passed, score, ts) "
                        "VALUES (%s,%s,%s,%s,%s,%s,%s)",
                        (a.person, a.artifact_id, a.question_id, a.content_hash, a.passed, a.score, a.ts))
    def load_attempts(self) -> list[Attempt]:
        with self._conn() as c, c.cursor() as cur:
            cur.execute("SELECT person, artifact_id, question_id, content_hash, passed, score, ts FROM attempts ORDER BY id")
            return [Attempt(p, aid, qid, h, passed, score, ts.isoformat() if hasattr(ts,'isoformat') else ts)
                    for p, aid, qid, h, passed, score, ts in cur.fetchall()]
```
*(Note: `ts` round-trips as ISO string in `Attempt` — store as TIMESTAMPTZ, read back and `.isoformat()` to match the file backend's string ts so `schedule._parse_ts` is happy. Confirm `registry._artifact_id` is importable, or replicate its 1-line sha logic.)*
- [ ] **Step 2: commit** `feat(ken): PostgresStore (psycopg3 sync, fail-loud, parameterized)`.

### Task 6: PG-gated contract param

**Files:** Modify `ken/tests/test_store_contract.py`

- [ ] **Step 1:** Add a PostgresStore factory to `STORE_FACTORIES`, **gated**: when `KEN_TEST_DATABASE_URL` is unset, the PG param is `pytest.param(..., marks=pytest.mark.skip(reason="KEN_TEST_DATABASE_URL unset"))`. The factory connects and **`TRUNCATE artifacts, questions, attempts`** (the contract tests assume an empty store at start; re-running `init.sql` would error on existing tables), then returns a `PostgresStore`. The same contract tests then run against PG when the env var is set.
- [ ] **Step 2:** Run locally without the env var → PG params **skipped**, FileStore params pass. (If a local Postgres is available via docker-compose, set the env var and confirm PG params pass too.)
- [ ] **Step 3: commit** `test(ken): PostgresStore contract param (gated on KEN_TEST_DATABASE_URL)`.

### Task 7: API backend selection

**Files:** Modify `ken-web/api/src/ken_web_api/deps.py`, `app.py`; Modify `ken-web/api/tests/test_api.py` (no behavior change — still file backend)

- [ ] **Step 1:** `deps.make_store()` — `if os.getenv("KEN_DATABASE_URL"): return PostgresStore(dsn)` else `return FileStore(manifest=_manifest_path(), questions=_questions_path(), ledger=_ledger_path())` (paths from KEN_DATA_DIR as today). Called at request time (seam).
- [ ] **Step 2:** Each handler builds `store = deps.make_store()` and passes `store=store` to `service.*` (replacing the old path args). The `register_artifact` handler makes **two** service calls (`register_artifact` then `list_artifacts`) — build ONE `store` and pass the same object to both. The existing api tests (file backend, FakeLLM, tmp KEN_DATA_DIR) stay **unchanged and green** — they never set KEN_DATABASE_URL.
- [ ] **Step 3:** Run `cd ken-web/api && python -m pytest -q` → **5 passed**; ruff clean. **Step 4:** commit `feat(ken-web/api): make_store() selects Postgres via KEN_DATABASE_URL (file default)`.

### Task 8: CI Postgres job + README

**Files:** Modify `.github/workflows/ci.yml`, `ken-web/README.md`

- [ ] **Step 1:** Add a job `ken (pytest, postgres)`: a `postgres:16` **service container** (health-checked), Python 3.13, `pip install -e ".[dev,postgres]"` in `ken`, apply `psql -f ken/db/init.sql`, set `KEN_TEST_DATABASE_URL`, run `python -m pytest -q tests/test_store_contract.py` (so the PG contract params run). The default `ken (pytest)` job stays DB-free (file backend). Validate YAML indentation against existing jobs.
- [ ] **Step 2:** `ken-web/README.md` — add: set `KEN_DATABASE_URL=postgresql://...` to use Postgres (apply `ken/db/init.sql` first; `ken/docker-compose.yml` for local); unset → file storage (default). Tests use FakeLLM/no key; PG tests gated on `KEN_TEST_DATABASE_URL`.
- [ ] **Step 3: commit** `ci+docs(ken-web): postgres contract job + KEN_DATABASE_URL run guide`.

---

## Notes / discipline
- **Order de-risks:** FileStore + contract test + service/cli refactor land green on file FIRST (Chunk 1); PostgresStore is added behind the same contract (Chunk 2). The default install/CI path never needs Postgres.
- Both backends satisfy ONE contract test → behavioral parity is enforced, not assumed.
- fail-loud (save/append) and append-only (attempts) hold on both; parameterized SQL only; `current_hash` filesystem-only; pure derivations untouched.
- ken's existing suite stays at the same passing count after the Chunk-1 refactor (the gate).
