# Design Spec — `ken-web` v0.1: cognitive-debt repayment web walking skeleton

- **Date:** 2026-06-23
- **Status:** Design (brainstorming output) — pending spec review + user approval
- **Builds on:** ken v0/v1 (merged to master) — the deterministic substrate.
- **Decisions locked (this session):** milestone = **B (self-host single team)**; first sub-project = **vertical-slice web walking skeleton**; **React + Vite SPA**; **reuse ken file storage** (Postgres deferred to a later slice, S2); **new module in the khala monorepo**.
- **Context:** ken's CLI/agent loop is not viable for a real service. This is the first slice of productizing ken (v2~v3) — a web app whose **core value is an optimized debt-*repayment* UX**, on a thin backend over the existing ken substrate.

---

## 1. Goal & scope

Stand up the **thinnest end-to-end web slice** that proves the repayment loop in a browser:
**register an artifact → server generates grounded questions → user answers in the web →
server grades + returns remediation → coverage updates** — across all three layers
(React → FastAPI → ken-core → LLM). Everything else (auth, Postgres, full dashboard,
multi-tenant) is explicitly deferred.

This is a **walking skeleton**: narrow in features, complete in depth (one artifact, one
implicit user, the whole stack wired and tested).

## 2. Architecture (3 layers, new module `ken-web/`)

```
ken (existing library)  ←  ken-web/api (FastAPI)  ←  ken-web/web (React + Vite SPA)
   substrate                server-side LLM (AnthropicLLM)     repayment UX
```

- **ken-core reuse + light extraction (S1):** the orchestration currently inline in
  `ken/src/ken/cli.py` (the due → generate-questions → grade → record flow) is extracted
  into a **`ken` service module** so both the CLI and the API call the same logic (DRY). The
  pure logic (`schedule`, `vouch`, `coverage`) and `probe`/`judge`/`llm` are reused
  unchanged.
- **Storage:** ken's file storage (manifest / questions JSON / attempt JSONL) on a single
  server instance. Kept behind ken-core's existing storage functions so a later slice (S2)
  swaps to Postgres without touching the API/UI contracts.
- **LLM:** server-side `AnthropicLLM` via `ANTHROPIC_API_KEY` on the server (web cannot use
  the keyless local-Claude-Code path — confirmed in prior analysis). Question generation,
  grading, and remediation explanations run server-side.

### Module layout
```
ken-web/
├── api/                      # FastAPI service (Python)
│   ├── pyproject.toml        # depends on `ken` (path dep) + fastapi, uvicorn
│   ├── src/ken_web_api/
│   │   ├── app.py            # FastAPI app + routes
│   │   ├── deps.py           # LLM/storage wiring (FakeLLM seam for tests)
│   │   └── schemas.py        # pydantic request/response DTOs
│   └── tests/                # TestClient + FakeLLM
└── web/                      # React + Vite SPA (TypeScript)
    ├── package.json
    ├── src/
    │   ├── api/client.ts     # typed fetch wrapper
    │   ├── pages/Home.tsx    # coverage + start-review
    │   ├── pages/Review.tsx  # the repayment session (core UX)
    │   └── components/...     # QuestionCard, RemediationPanel, ProgressBar, etc.
    └── tests/                # vitest + React Testing Library
```

## 3. ken-core change (S1 extraction)

Add `ken/src/ken/service.py` (orchestration; LLM injected). Two kinds of functions, flagged
honestly:

**Extraction (existing CLI behavior, unchanged — `cli.py` refactored to call these, its 8
tests stay green):**
- `ensure_questions(artifact_id, *, llm, ...) -> (hash, list[Question])` — load, or if
  **missing OR stale** (`store_hash != registry.current_hash`) **regenerate + save** via
  `probe.make_questions` (mirrors `cli.due`/`cli.review` staleness handling).
- `due_questions(...) -> list[DueItem]` — registry → `schedule.rebuild` → `due(states,
  all_qids)`, with question text. **Not person-scoped** (`rebuild`/`due` aggregate all
  attempts regardless of `person`, exactly as the CLI; `person` is informational only).
- `grade_set(artifact_id, qa_pairs, *, llm, ...)` — the existing whole-set `judge.grade`
  path that `cli.review` uses (one verdict applied to the set). **Keep `cli.review` on this
  path** so its tests don't change.
- `coverage_report(...) -> CoverageReport` — reuse `compute_coverage_v1`.

**NEW (API-only cognition — not in the CLI today; new code + tests):**
- `grade_answer(artifact_id, question_id, answer, *, person, llm, ...) -> AttemptResult` — a
  **single-question** grade: calls `judge.grade(text, [(q_text, answer)], llm)`, records the
  attempt (append-only, **fail-loud**; LLM grade error → **fail-closed** `passed=False`), and
  **on fail** calls a NEW `remediate(...)`.
- `remediate(artifact_text, question, answer, *, llm) -> str` — **NEW LLM call with a new
  grounded-explanation prompt** (its own `FakeLLM` script entry in tests). **Fail behavior:**
  if the remediation LLM call fails, return the fail verdict with `remediation=None` —
  **never block recording the attempt** on a remediation failure.

## 4. API (FastAPI, single-team, no auth)

| Method · path | Body / query | Returns |
|---|---|---|
| `GET /api/artifacts` | — | list of `{artifact_id, path, status, weak_count}` — `status` (vouched/orphan) from `CoverageReport.orphans`, `weak_count` from its `weakness` map (no new derivation) |
| `POST /api/artifacts` | `{path}` | registered `ArtifactRef` |
| `GET /api/artifacts/{id}/due` | `?person=` (informational) | `{questions: [{question_id, text}]}` — generates+saves if **missing OR stale**. **Non-idempotent GET** (LLM call + write); same fail-closed/fail-loud rules as `/attempts` |
| `POST /api/attempts` | `{artifact_id, question_id, person, answer}` | `{passed, score, remediation}` — single-question grade + records attempt |
| `GET /api/coverage` | `?person=` (informational) | `{total, covered, ratio, orphans[], weakness[]}` |

DTOs in `schemas.py` (pydantic v2). `person` is informational throughout (single implicit
user this slice; not used in derivation). Errors: 4xx for bad input; **grade LLM failure →
fail-closed** (`passed:false`, never auto-pass); **storage write failure → 5xx** (fail-loud,
never silently drop an attempt); **remediation LLM failure → return the verdict with
`remediation:null`** (never blocks recording the attempt).

**Click-path / artifact selection (closes the "which artifact" gap):** the SPA Home calls
`GET /api/artifacts`; selecting an item (or the **Start review** CTA = first orphan) routes
to `/review?artifact={id}`, which then calls `GET /api/artifacts/{id}/due`. There is no
server-side "current artifact" state — selection lives in the client route.

## 5. Repayment UX (the core value)

- **Home** (`/`): coverage headline ("3 / 10 vouched"), a **Start review** CTA, and a short
  attention list (orphans / weak items). Minimal but polished. Selecting an item (or
  **Start review** = first orphan) routes to `/review?artifact={id}`.
- **Review session** (`/review`, one question at a time — optimized for flow):
  1. Header: artifact name + progress ("Question 2 / 3").
  2. Question card + answer textarea + Submit.
  3. On submit → grading state → result:
     - **Pass:** green confirmation, auto-advance.
     - **Fail:** inline **RemediationPanel** — the grounded explanation (why, referencing the
       artifact) → "I've reviewed this" → re-queued.
  4. Session end: summary (vouched this session / re-study queue / updated coverage).
- Principles: one question at a time, immediate feedback, inline remediation, visible
  progress — make paying down the debt feel doable, not punitive.

## 6. Walking-skeleton acceptance (end-to-end, one artifact)

A user can, in the browser: register an artifact → see 3 generated questions → answer →
get pass/fail with remediation on fail → see coverage move. The request path traverses
React → FastAPI → ken-core → LLM and back. That is the whole slice.

## 7. Testing

- **API:** FastAPI `TestClient` with the **`FakeLLM`** seam (reuse ken's) — deterministic
  tests for each endpoint (register, due generates questions, attempt grades+records+fail-
  closed, coverage). No live API key in tests.
- **Web:** `vitest` + React Testing Library — the Review flow (renders questions, submits,
  shows pass vs remediation, advances) with the API client mocked.
- **ken-core:** existing tests cover pure logic; add `service.py` tests (LLM mocked),
  **including the new single-question `grade_answer` + `remediate` path** — `FakeLLM` scripted
  with two responses (verdict JSON, then remediation text) for the fail case, and a test that
  a remediation LLM failure still records the attempt with `remediation=None`.
- Manual run: `uvicorn` (API) + `vite dev` (web), or FastAPI serves the built SPA.

## 8. Non-goals (this slice; later sub-projects)

Auth/login; Postgres (S2); full management/tracking dashboard with trends (S5);
multi-tenancy (S6); git-repo scan registration (S7); run-time agent eval; spaced-repetition
*scheduling UI* beyond reflecting "re-queued"; deployment/hosting automation.

## 9. Risks / notes

- **API key handling:** server reads `ANTHROPIC_API_KEY` from env; never sent to the client.
- **Single instance / file storage:** fine for one self-hosted team; concurrent writes are
  out of scope until Postgres (S2). Document this limit.
- **Frontend quality is the point:** implementation MUST use the **frontend-design** skill
  (distinctive, production-grade, avoid generic AI aesthetics) — captured for the plan.
- **CORS/serving:** dev = Vite proxy to FastAPI; prod = FastAPI serves the built SPA (single
  origin, no CORS). Pick one in the plan (lean: FastAPI serves built static + Vite proxy in
  dev).

## 10. Success criteria

- Browser-driven: register → answer → pass/fail+remediation → coverage updates, end to end.
- API tests green with FakeLLM (no key); web Review-flow test green.
- `cli.py` still passes after the `service.py` extraction (no behavior change).
- No auth/Postgres/dashboard introduced; key never reaches the client.

---

## Implementation outline (for writing-plans)

1. `ken/src/ken/service.py` — extract orchestration; refactor `cli.py` to use it; keep CLI tests green.
2. `ken-web/api` — FastAPI app, schemas, deps (LLM seam), the 5 endpoints; TestClient + FakeLLM tests.
3. `ken-web/web` — Vite+React scaffold, typed API client, Home + Review pages/components (frontend-design skill); vitest flow test.
4. Wire dev (Vite proxy) + prod (FastAPI serves built SPA); a README run guide.
5. Manual e2e walkthrough on one khala artifact (server key required) → capture.
