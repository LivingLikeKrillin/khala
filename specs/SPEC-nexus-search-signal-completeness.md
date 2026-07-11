---
id: SPEC-nexus-search-signal-completeness
type: spec
title: Search signals — record the streaming path, and measure citation fabrication
status: approved
linked_adrs:
- ADR-0004
- ADR-0006
tags:
- nexus
- search
- signals
- measurement
- faithfulness
approved_by: LivingLikeKrillin
reviewed_at: '2026-07-11T19:10:43Z'
content_hash: sha256:eab3ac79525c88d1ab7bfb4dbcb197d08e29625d27e62f234038a1f7ac3d6f54
---

## 1. Goal

Close two measurement gaps the query-quality review found:

1. **The streaming answer path records no signals.** `record_search` runs on `/search` and
   `/search/answer`, but the SSE stream (`/search/answer/stream`) — the path the **web chat** uses —
   records nothing. The flagship surface is invisible to `search_log` / `v_search_health`.
2. **There is no faithfulness metric.** `#134` now computes `unverified_citations` per answer but does
   not persist it (it named this as a follow-up). Add it to the search signal so the **citation
   fabrication rate** becomes measurable over time — the first faithfulness metric.

Measurement is foundational to the project's demand-pull posture: deferred improvements (a reranker,
graph ranking) are built when signals show they are needed, so having the signals is what makes those
decisions evidence-based rather than speculative. (This is the project's stated stance, not an ADR
guarantee — I-008.)

## 2. Non-goals

- **Using signals to re-rank (learning-to-rank).** This SPEC records; it does not feed signals back
  into ranking.
- **Deciding the reranker.** Recording the demand signal is not the same as building on it.
- **Backfilling historical rows.** The new column defaults to 0 for existing rows; only new searches
  carry the real value.

## 3. What exists

- `search/signals.py`: `SearchSignals` (frozen dataclass), `extract_signals(result, answer, …)`
  (pure), `record_search` (structlog + best-effort fire-and-forget `_persist` INSERT into
  `search_log`). The INSERT column list is fixed (14 columns).
- `search_log` (`init.sql`) — 14 columns; no `unverified_citations`. `v_search_health` aggregates a
  7-day window per `(path, route)`.
- Non-stream `/search/answer` (`api.py:416`) already calls `extract_signals(search_result,
  answer_result, …)` then `record_search` — it passes the `AnswerResult`, so a new
  `answer`-derived field flows without a call-site change.
- The SSE stream (`api.py`, `event_stream`) holds `search_result`, `entity_rids`, and (since #134)
  the validated citation report for its `done` event — but has **no** `record_search` call and builds
  **no** `AnswerResult`.

## 4. Design

### 4.1 Schema

`migration 005_search_log_citations.sql` (idempotent) + `init.sql` add **two nullable** columns:
```
ALTER TABLE search_log ADD COLUMN IF NOT EXISTS n_citations          INTEGER;
ALTER TABLE search_log ADD COLUMN IF NOT EXISTS unverified_citations INTEGER;
```
Two columns, not one, because a **rate** needs a denominator (I-001): the fabrication rate is
`unverified_citations / n_citations`, so both the total and the unverified count are stored.
**Nullable (no `DEFAULT 0`)** on purpose (I-006): pre-migration rows and any search that didn't
produce an answer (empty evidence, `/search` with no narration) are `NULL` = *unmeasured*, which the
metric excludes — otherwise "not measured" would be indistinguishable from "measured, zero
fabrications". A search that produced an answer with no citations records `n_citations = 0`,
`unverified_citations = 0` (measured zero, distinct from NULL).

### 4.2 Signal carries the field

- `SearchSignals` gains `n_citations: int | None = None` and `unverified_citations: int | None =
  None` (None = unmeasured).
- `extract_signals` derives both from the `AnswerResult` when present: `n_citations =
  len(answer.citations)`, `unverified_citations = answer.unverified_citations`. It also accepts
  **explicit** `n_citations`, `unverified_citations`, and `llm_failed` overrides — for the stream,
  which has the citation report and its own failure flag but no `AnswerResult`. Explicit wins; else
  answer-derived; else `None` (n/unverified) / `False` (llm_failed). A path with no answer at all
  (e.g. `/search`) leaves both `None`.
- `_persist` INSERT and the `record_search` structlog line add the two columns/fields.

### 4.3 The stream records a signal

The stream stamps `t0 = time.time()` at handler entry and sets a local `llm_failed = False`, flipped
to `True` in the LLM-streaming `except` branch (there is no such flag today — this SPEC adds it,
I-002). The citation report is computed for the `done` event (#134). **The signal is built and
`record_search` is called *before* yielding the terminal `done` event** (I-003/I-004) — not after —
because an async generator may never resume past its final `yield` if the client disconnects, so
"after the last yield" would silently drop the signal. `record_search` is fire-and-forget (a task),
so ordering it before the yield adds no latency to the stream.

The signal: `extract_signals(search_result, None, path="search_answer_stream", tenant=…, clearance=…,
query=…, n_entities=len(entity_rids), latency_ms=int((time.time()-t0)*1000),
n_citations=len(report.citations), unverified_citations=report.unverified_count,
llm_failed=llm_failed)`. `latency_ms` is measured from **handler entry to done-signal build**
(I-007). The distinct `path` (`search_answer_stream`) keeps the stream separable in
`v_search_health`.

### 4.4 The metric

`v_search_health` gains a real **fabrication rate**:
`SUM(unverified_citations) / NULLIF(SUM(n_citations), 0)` over the rows where `n_citations IS NOT
NULL` (measured answers only, I-001/I-006). An operator watches it per `(path, route)` and alerts on
a rise. The view is changed by **`DROP VIEW IF EXISTS v_search_health; CREATE VIEW …`** — not
`CREATE OR REPLACE`, which in PostgreSQL fails when the column set changes anywhere but the tail
(I-009). The migration and `init.sql` both do the drop-and-create.

## 5. Error handling

- `record_search` already never raises (best-effort `_persist`, swallowed). Unchanged.
- The stream's `record_search` is fire-and-forget after the `done` event is yielded, so it never
  delays or breaks the stream. If the LLM errored mid-stream, `llm_failed=True` is recorded and the
  citation count is whatever validated (typically 0 on the fallback text).
- Migration is idempotent (`ADD COLUMN IF NOT EXISTS`); the view is `CREATE OR REPLACE`.

## 6. Testing

- `extract_signals` with an `AnswerResult` (2 citations, 1 unverified) → signal `n_citations=2`,
  `unverified_citations=1` (answer-derived).
- `extract_signals` with **no** answer but explicit `n_citations=3, unverified_citations=2,
  llm_failed=True` → the signal carries exactly those (the stream path's signal shape — this **is**
  the unit coverage for the stream's signal, I-005; the fire-and-forget call-site is live-verified).
- Explicit override beats answer-derived when both present; a path with no answer leaves both `None`.
- DB-backed: `_persist` of a signal with `(n_citations=N, unverified_citations=M)` writes a
  `search_log` row whose columns equal N and M; a signal with both `None` writes SQL `NULL`
  (unmeasured ≠ zero).
- `v_search_health` exposes the fabrication rate; a DB read after seeding a measured row (2 total, 1
  unverified) and an unmeasured row (NULLs) yields rate `0.5` — the NULL row is excluded.
- Existing signal tests still pass (the new fields default to `None`, back-compatible).
- Stream wiring is verified live (a streamed answer lands a `search_answer_stream` row with the
  citation columns) — the SSE generator is exercised end-to-end.

## 7. Acceptance

`/search/answer` and the streamed answer both record a `search_log` row on the normal path (the
stream was silent before) — best-effort and recorded **before** the terminal event, so a client
disconnect after the answer doesn't silently drop it. Each answer-bearing row carries `n_citations`
and `unverified_citations` (NULL where no answer was produced), and `v_search_health` exposes the
fabrication **rate** over measured rows. The flagship UI path is no longer a measurement blind spot,
and the faithfulness metric #134 named now exists — as a rate, with unmeasured distinguished from
zero.
