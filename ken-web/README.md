# ken-web

A browser-driven vertical slice of ken's **repayment loop**: register an artifact →
the server generates grounded comprehension questions → you answer them in a React SPA
→ the server grades each answer and returns remediation on a miss → coverage updates.
It spans React → FastAPI → ken-core → LLM, reusing ken's file storage (no Postgres,
no auth). The point is to make ken's "vouch for what you own" loop tangible in a UI.

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

## Storage paths (optional)

ken's file stores default under the current directory. Override per process via env:
`KEN_DATA_DIR` (base dir), or the individual `KEN_MANIFEST`, `KEN_QUESTIONS`,
`KEN_LEDGER`. `KEN_N_QUESTIONS` sets how many questions are generated per artifact.

## Test

```bash
cd ken-web/api && python -m pytest -q          # 5 tests, FakeLLM, no key
cd ken-web/web && npm run test -- --run        # vitest, FakeLLM via mocked client
```
