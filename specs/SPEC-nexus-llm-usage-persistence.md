---
id: SPEC-nexus-llm-usage-persistence
type: spec
title: Persist LLM token usage + cost to search_log and v_search_health (Unit B)
status: approved
linked_adrs: []
tags:
- nexus
- llm
- llmops
approved_by: LivingLikeKrillin
reviewed_at: '2026-07-14T02:55:26Z'
content_hash: sha256:e3cd33682bb4dd2bec88d3886420ac224098ceb6ae1d411ffbca83f55d08f578
---

## 1. Goal

Unit A (SPEC-nexus-llm-usage-capture, #140) captures per-call token usage + cost onto `AnswerResult.usage`
and the API responses but **persists nothing**. Cost is still invisible over time. Unit B records
`prompt_tokens` / `completion_tokens` / `cost_usd` into `search_log` and exposes **per-query and total
cost** in `v_search_health` — mirroring exactly how #134 (capture) was followed by #136 (persist the
citation fabrication signal).

## 2. What exists

- `search/signals.py`: `SearchSignals` (frozen dataclass), `extract_signals(result, answer=None, *, …,
  n_citations, unverified_citations, llm_failed)` — explicit args win, else derived from `AnswerResult`,
  else `None`. `_persist` INSERTs 16 columns; `record_search` logs + best-effort fire-and-forget insert.
- `AnswerResult.usage` (Unit A) = `{input_tokens, output_tokens, cost_usd, model} | None`.
- Schema lives in **three** locations that must stay in sync (the #136 trap): `nexus/db.py`
  `SEARCH_LOG_DDL` (startup idempotent — `CREATE TABLE IF NOT EXISTS` + `ALTER … ADD COLUMN IF NOT
  EXISTS` + **`DROP VIEW` + `CREATE VIEW`**), `nexus/init.sql` (fresh-DB DDL + `CREATE OR REPLACE VIEW`),
  and `nexus/migrations/00N_*.sql`. Next number = **006**.
- Call sites: sync `/search/answer` already passes `answer_result` to `extract_signals` (`api.py:419`) →
  usage will derive automatically; the stream path passes signals explicitly (no `AnswerResult`) and
  holds the usage in its `usage_out` list (Unit A).

## 3. Design

- **Columns** — `search_log` gains `prompt_tokens INTEGER`, `completion_tokens INTEGER`,
  `cost_usd DOUBLE PRECISION`, **all nullable**. `NULL = unmeasured/unknown` (no LLM call; or a priced
  gap — an unpriced model yields `cost_usd NULL` even when the token counts are set) — **`NULL ≠ 0`**,
  the #136 discipline. **Invariant (I-008):** `cost_usd` non-null ⇒ both token counts non-null, because
  `compute_cost` returns `None` unless both are present; the inverse (cost set, tokens null) cannot arise
  through this path. `cost_usd` is a **monitoring estimate, not an accounting/billing figure**, so
  `DOUBLE PRECISION` (with its float-sum rounding) is acceptable here — authoritative billing would use
  `NUMERIC`, which is out of scope (I-009).
- **Three-location sync (006)** — apply identically in all three: `db.py SEARCH_LOG_DDL` (add the 3 cols
  to `CREATE TABLE` **and** three `ALTER … ADD COLUMN IF NOT EXISTS`, then extend the `DROP VIEW`+
  `CREATE VIEW`), `init.sql` (add the 3 cols to `CREATE TABLE` and extend the view), and new
  `migrations/006_search_log_usage.sql` (idempotent `ALTER … ADD COLUMN IF NOT EXISTS` ×3 +
  `DROP VIEW` + `CREATE VIEW`). db.py's `DROP VIEW`+`CREATE` is the authoritative one that must not be
  left behind (the #136 startup-revert trap).
- **`SearchSignals`** gains `prompt_tokens: int | None = None`, `completion_tokens: int | None = None`,
  `cost_usd: float | None = None`.
- **`extract_signals`** gains explicit override args `prompt_tokens` / `completion_tokens` / `cost_usd`
  (default `None`). Each of the three is resolved **independently** (as the citation args are): explicit
  arg if not `None`, else derived from `answer.usage` when an `AnswerResult` is present, else `None`
  (I-004). Derivation uses **`.get()`**, not subscripting (I-003):
  `prompt_tokens ← usage.get("input_tokens")`, `completion_tokens ← usage.get("output_tokens")`,
  `cost_usd ← usage.get("cost_usd")` (the search_log↔usage name map). `answer.usage is None` (no LLM
  call) ⇒ all three `None`.
- **`_persist`** INSERT extends to 19 columns; **`record_search`** structlog adds the 3 fields.
- **`v_search_health`** gains `avg_cost_priced_usd` (= `avg(cost_usd)`) and `total_cost_usd`
  (= `sum(cost_usd)`), over the same 7-day window as the view's other metrics. **Both aggregate only
  over rows with a non-null `cost_usd` (priced calls)** — the name makes that explicit (I-005); both are
  `NULL` when no priced rows exist (no fabricated zero). The **raw `search_log` rows persist with no TTL,
  so full cost history is directly queryable**; the view is a rolling 7-day *health snapshot*, exactly
  like `p95_latency_ms`/`citation_fabrication_rate` already are — not the historical archive (I-006).
- **Wiring** — sync path is automatic (already passes `answer_result` → derives). Stream path: after the
  loop, `u = usage_out[0] if usage_out else None`; `usage_out` holds a `Usage` on **any successful**
  stream completion (its token fields may be `None` for claude-code/unpriced) and is **empty on a
  mid-stream failure** (I-002). Pass `prompt_tokens=u.input_tokens if u else None` (and the same for
  the other two) explicitly into `extract_signals`, alongside the existing citation/number args.

## 4. Non-goals

- **Unit A** (capture) — already merged; unchanged.
- **Unit C** — claude-code bridge usage (still yields `None` tokens → `NULL` rows; correct, not
  fabricated).
- **Per-tenant budgets / alerting / a cost dashboard UI** — later; this SPEC lands the columns +
  aggregate view only.
- **Backfill** of historical rows — new columns are `NULL` for pre-existing rows (unmeasured), never
  back-computed.

## 5. Testing

- **Pure** (`extract_signals`): derives `prompt_tokens`/`completion_tokens`/`cost_usd` from an
  `AnswerResult` whose `usage` is set; explicit args override; `usage=None` ⇒ all three `None`; an
  answer with tokens but `cost_usd=None` (unpriced model) ⇒ token fields set, `cost_usd None` (NULL ≠ 0).
- **Integration** (`pytest.mark.integration`, disposable test DB 5433): after `ensure_search_log`,
  insert two `SearchSignals` via `_persist` — one priced (cost set), one with `cost_usd=None`; assert the
  priced row stores the three values; query `v_search_health` and assert `avg_cost_priced_usd` equals the
  priced row's cost (the `NULL` row does **not** drag it toward 0) and `total_cost_usd` equals the sum of
  priced rows.
- **Three-location coverage (I-001):** the integration test runs against the CI `nexus-postgres` DB,
  which is built from **`init.sql` + all `migrations/*`** (per that job) — so a mistake in `init.sql` or
  `006` surfaces as a failing column/aggregate assertion there; `ensure_search_log()` in the same test
  exercises the **`db.py SEARCH_LOG_DDL`** path. The three locations are thus each exercised; keeping
  their text identical is a reviewer checklist item (the #136 lesson), not an automated equality proof.

## 6. Acceptance

Every recorded search that ran a priced LLM call carries `prompt_tokens`/`completion_tokens`/`cost_usd`
in `search_log`, on both the sync and streaming answer paths; unmeasured/unpriced calls store `NULL`
(never 0), and `cost_usd` non-null implies both token counts non-null. `v_search_health` reports
`avg_cost_priced_usd` and `total_cost_usd` over the 7-day window, aggregating only priced rows (raw rows
remain the full history). The three schema locations are each exercised by the tests per §5. The
existing best-effort persistence contract is **unchanged** — Unit B adds columns/derivation only and
introduces no new failure path into the request (I-007).
