# ken-web

A browser-driven vertical slice of ken's **repayment loop**: register an artifact →
the server generates grounded comprehension questions → you answer them in a React SPA
→ the server grades each answer and returns remediation on a miss → coverage updates.
It spans React → FastAPI → ken-core → LLM. Storage is dual-backend: ken's file
storage by default, or Postgres when `KEN_DATABASE_URL` is set. Auth is **off by
default** (open); set `KEN_AUTH=1` to gate the instance behind login (see
[Authentication](#authentication-optional)). The point is to make ken's "vouch for
what you own" loop tangible in a UI.

Two parts:

- **`api/`** — FastAPI over `ken.service`, with the server-side `AnthropicLLM`. The API
  key lives only on the server; it is never sent to the browser.
- **`web/`** — React + Vite + TypeScript SPA (the repayment UX).

## Install

From the monorepo root:

```bash
# Python: ken (path dep) + the API, both editable
pip install -e ken -e ken-web/api

# Web deps
cd ken-web/web && npm install
```

## Develop (two processes)

Run the API and the Vite dev server side by side. Vite proxies `/api` → the API
(`http://localhost:8000`), so the SPA calls same-origin `/api/...` in dev too.

```bash
# Terminal 1 — API
uvicorn ken_web_api.app:app --reload          # http://localhost:8000

# Terminal 2 — web (Vite dev server, proxies /api)
cd ken-web/web && npm run dev                  # http://localhost:5173
```

Open http://localhost:5173.

## Production (single origin)

Build the SPA, then let the API serve it. With `web/dist` present, the API mounts the
built SPA at `/` and keeps the API under `/api` — one origin, no CORS.

```bash
cd ken-web/web && npm run build                # emits ken-web/web/dist
uvicorn ken_web_api.app:app                    # serves dist at / and the API at /api
```

The static mount is guarded: if `web/dist` is absent (dev, or automated tests), the
mount is skipped and the API runs API-only — it never crashes on a missing build.

## LLM key

Real question generation, grading, and remediation use Anthropic via ken's
`AnthropicLLM`. Set `ANTHROPIC_API_KEY` **on the server process** before running
`uvicorn`:

```bash
export ANTHROPIC_API_KEY=sk-ant-...
```

The automated tests (both `api/` pytest and `web/` vitest) use ken's `FakeLLM` seam
and require **no** API key.

## Storage backend

The backend is selected at request time by `KEN_DATABASE_URL`:

- **unset (default) — file storage.** ken's file stores default under the current
  directory. Override per process via env: `KEN_DATA_DIR` (base dir), or the
  individual `KEN_MANIFEST`, `KEN_QUESTIONS`, `KEN_LEDGER`. The CLI/local workflow
  is unchanged.
- **set — Postgres.** Point the API at any Postgres:

  ```bash
  export KEN_DATABASE_URL=postgresql://ken:ken@localhost:5434/ken
  ```

  Apply the schema once before first use (no migration tool; YAGNI):

  ```bash
  psql "$KEN_DATABASE_URL" -f ken/db/init.sql
  ```

  For a local Postgres, `ken/docker-compose.yml` brings up a single `postgres:16`
  on port 5434 with the schema auto-applied:

  ```bash
  cd ken && docker compose up -d
  ```

`KEN_N_QUESTIONS` sets how many questions are generated per artifact (both backends).

## Authentication (optional)

Auth is **off by default** — the API is open and attempts are recorded under the
identity `local` (today's behavior). To gate a deployment behind email + password
login, set **`KEN_AUTH=1`**. Auth is **Postgres-only**: it requires `KEN_DATABASE_URL`
(the server fails loud at startup otherwise), and the file backend stays unauthenticated
for local/dev. The `ken` CLI is unaffected.

```bash
export KEN_DATABASE_URL=postgresql://ken:ken@localhost:5434/ken
psql "$KEN_DATABASE_URL" -f ken/db/init.sql   # creates users + sessions too
export KEN_AUTH=1
export KEN_COOKIE_SECURE=1                     # set behind HTTPS (omit for local http)
```

There is **no public signup** — an operator seeds users from the server with the
bundled CLI:

```bash
ken-web-admin add-user alice@example.com      # prompts for a password (argon2-hashed)
```

Once enabled, the SPA redirects unauthenticated visitors to `/login`; a session cookie
(`ken_session`, httpOnly, SameSite=Lax) gates every `/api/*` data call, and each graded
attempt records the **logged-in email** as its `person`. Log out from the masthead.
Multi-tenancy (per-tenant data isolation) is a separate, future slice — today all
authenticated users share one dataset.

## Test

```bash
cd ken-web/api && python -m pytest -q          # FakeLLM + FakeAuthStore, no key/DB
cd ken-web/web && npm run test -- --run        # vitest, client mocked
```

ken's storage backends share one contract test (`ken/tests/test_store_contract.py`).
FileStore runs always; the PostgresStore params run only when `KEN_TEST_DATABASE_URL`
is set (gated, skipped otherwise) — CI runs both via a `postgres:16` service job.
