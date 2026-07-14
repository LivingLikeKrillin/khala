---
id: SPEC-nexus-llm-usage-capture
type: spec
title: Capture per-call LLM token usage and cost (Unit A of cost tracking)
status: approved
linked_adrs: []
tags:
- nexus
- llm
- llmops
approved_by: LivingLikeKrillin
reviewed_at: '2026-07-14T02:20:22Z'
content_hash: sha256:a12f54e7fd9487fce9aa593a0b63ccb1d812d2e61ff228eb11a9eca18dc86ce2
---

## 1. Goal

Anthropic responses carry token usage that khala **discards** (`_AnthropicBackend.generate` returns
`resp.content[0].text`, dropping `resp.usage`); the claude-code dev backend returns text only. Cost is a
total blind spot. Unit A makes usage capturable: surface per-call **input/output tokens + computed cost**
from the provider layer onto `AnswerResult` and the `/search/answer` responses, **without breaking
existing callers**. Persistence to `search_log` + `v_search_health` aggregates is **Unit B** (separate
SPEC); this SPEC stops at capture + API surfacing.

## 2. What exists

- `providers/llm.py`: `LLMService.generate(...) -> str` and `stream(...) -> AsyncIterator[str]`, over two
  backends. `_AnthropicBackend.generate` has `resp.usage.input_tokens/output_tokens` available but
  discards it; `.stream` yields `stream.text_stream` (usage is on `await stream.get_final_message()`).
  `_ClaudeCodeBackend` POSTs to the bridge, returns `{"text": …}` only. `DEFAULT_MODEL =
  "claude-sonnet-4-6"`, overridable by `NEXUS_LLM_MODEL`.
- Callers of `generate()`: `answer.py::generate_answer`, plus `a2a/server.py` and `cli.py` (text only).
- `generate_answer` produces `AnswerResult`; the stream path in `api.py` calls `stream()`.

## 3. Design — non-breaking (blast radius = opt-in only)

Keep `generate() -> str` **unchanged** (existing callers and test stubs untouched); add usage-returning
variants that only the cost-aware callers opt into.

- **Types** (new, in `providers/llm.py`):
  - `Usage(input_tokens: int | None, output_tokens: int | None, cost_usd: float | None, model: str)`.
    `model` is the service's **configured** model (`NEXUS_LLM_MODEL` / `DEFAULT_MODEL` = what the
    operator sets), **not** the response's dated model id — and it is exactly the key used for the
    pricing lookup, so the pricing table and `NEXUS_LLM_MODEL` share one vocabulary (I-002).
  - `LLMResult(text: str, usage: Usage)`.
- **Backends** gain a usage-returning generate; the plain `generate()` delegates to it and returns
  `.text`:
  - `_AnthropicBackend`: read `resp.usage.input_tokens/output_tokens`; `cost_usd` via `compute_cost`.
  - `_ClaudeCodeBackend`: the bridge returns text only today → `Usage(None, None, None, model)`
    (dev/keyless; real bridge usage is **Unit C**, out of scope). Never fabricates numbers.
- **`LLMService.generate_full(system, user, max_tokens) -> LLMResult`** (new); `generate()` returns
  `(await generate_full(...)).text`. Usage/cost computation **never raises** (see Cost below), so
  `generate()` fails only where it already did — on the LLM call itself — and its `-> str` contract and
  behaviour are preserved (I-003).
- **Streaming usage** (async generators can't return a value): `stream(..., usage_out: list | None =
  None)` gains an optional param; on **successful** stream completion the backend **appends exactly one
  `Usage`** (`_AnthropicBackend` from `get_final_message()`; `_ClaudeCodeBackend` from its single
  `generate_full`). **On an exception mid-stream, `usage_out` is left untouched** (empty) → the caller
  reads no usage = `None`, matching the failed/unknown call (I-004). Callers omitting `usage_out` are
  unaffected.
- **Cost** — pure, **total (never raises)** `compute_cost(input_tokens, output_tokens, model, pricing)
  -> float | None`. Returns `None` — never a partial or fabricated number — when **any** of: a token
  count is `None`; `model` is absent from `pricing`; the entry is malformed or partial (missing
  `input_per_mtok` or `output_per_mtok`, non-numeric). Otherwise
  `input/1e6·input_per_mtok + output/1e6·output_per_mtok`. `None ≠ 0` (unknown, not free — mirrors
  #136's nullable discipline). Pricing lives in `config.yaml` under
  `llm.pricing: {<model>: {input_per_mtok, output_per_mtok}}` (USD **per 1M tokens**,
  operator-maintained; no staleness detection — out of scope). A missing `llm.pricing` section ⇒ empty
  table ⇒ every `cost_usd` is `None` (I-006, I-007).
- **Surfacing** — `AnswerResult` gains `usage: dict | None` (`{input_tokens, output_tokens, cost_usd,
  model}` or `None` when no LLM call). `generate_answer` uses `generate_full`. `/search/answer` response
  and the stream `done` event carry `usage`. The stream path passes a `usage_out` list to `stream()` and
  reads it at the done event (alongside the existing citation/number capture).

## 4. Non-goals

- **Unit B**: `search_log` columns (`prompt_tokens`/`completion_tokens`/`cost_usd`), `SearchSignals`,
  `v_search_health` cost aggregates — the persistence + dashboard, a separate SPEC.
- **Unit C**: making the `claude_llm_bridge` return usage (dev backend); until then claude-code usage is
  `None`, not fabricated.
- **Prompt-caching / cache-read token accounting**, multi-call (retry) aggregation, per-tenant budgets.
- Changing `generate() -> str` or any existing caller/test-stub signature.

## 5. Testing

Pure / unit (no network — inject a fake client/transport as the provider tests already do):

- `compute_cost`: table hit → correct `in/1e6·p + out/1e6·p`; model absent from pricing → `None`; either
  token `None` → `None`.
- `_AnthropicBackend.generate_full`: mock client returns usage(in=100,out=50) → `LLMResult.usage` has
  those tokens and `cost_usd` per the pricing config; `generate()` still returns the bare text string.
- `_ClaudeCodeBackend.generate_full`: bridge returns `{"text": …}` (no usage) → `Usage(None, None,
  None, model)`; `cost_usd is None`.
- Streaming: `stream(..., usage_out=sink)` appends exactly one `Usage` at end; omitting `usage_out`
  yields text unchanged (back-compat).
- `generate_answer` populates `AnswerResult.usage` from the model result (drive the real path with a
  fake backend, as #139 did); no-snippet / llm-failed paths leave `usage = None`.

## 6. Acceptance

`generate_full`/`stream(usage_out=…)` surface the **provider-reported** input/output tokens and a
`compute_cost` figure (from `config.yaml` pricing; `None` when the model is unpriced or tokens unknown,
never fabricated or partial). `AnswerResult.usage` and the `/search/answer` + stream responses carry it.
`generate() -> str` and every existing caller/test stub are unchanged. Tests verify the *wiring* with
injected usage (the live figures against a real provider are environment-gated, as with #138/#139). No
persistence yet (Unit B). Deterministic and pure where it counts; no LLM judgment.
