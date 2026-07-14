---
id: SPEC-nexus-embed-generation-drift
type: spec
title: Detect mixed embedding generations (partial re-embed guardrail)
status: approved
linked_adrs: []
tags:
- nexus
- llmops
- embedding
approved_by: LivingLikeKrillin
reviewed_at: '2026-07-14T07:17:33Z'
content_hash: sha256:de5fe7e39fabfcfc3e1733201f9be8163b99d38ab5f95ecf3a829b05063bf807
---

## 1. Goal

This session's deep research flagged **partial re-embedding** (some chunks on a new embedding model, the
rest on the old one) as a leading cause of *silent* retrieval drift (directional, vendor-sourced — not a
hard-cited figure). khala **already records the producing model per vector** (`chunks.embed_model`, set
in `index/embed.py` from `EmbeddingService.get_model_name()`). This SPEC turns that existing column into
a cheap **guardrail**: report the distribution of `embed_model` across the searchable corpus and flag
when it spans more than one generation — so a half-finished re-embed (the danger the KURE swap would
introduce) is visible instead of silent.

**Operational definition (I-001):** "generation" here = the **`embed_model` string value**, which is the
only versioning axis khala records. A fuller notion (model + dimension + preprocessing + normalization)
is richer, but `embed_model` is what exists; this guardrail detects a *model-string* split, which is the
dominant partial-re-embed signature. Finer generation keys are out of scope. This is the
demand-pull-appropriate slice; the heavy blue-green / dimension-migration machinery is deferred to the
actual embedding swap that defines its shape.

## 2. What exists

- `chunks.embed_model TEXT NOT NULL DEFAULT 'multilingual-e5-base'`; `index/embed.py` overwrites it with
  the real model (`nomic-embed-text`) whenever it writes an embedding. The column **default is stale**
  (it names a model khala no longer uses) — harmless here precisely because the `embedding IS NOT NULL`
  filter (below) excludes never-embedded chunks that still carry it (I-009; a separate cleanup could fix
  the default).
- `embedding vector(768)` is dimension-locked (nomic 768d). The IVFFlat cosine index
  (`idx_chunk_vector`) has the **partial predicate** `WHERE status='active' AND is_quarantined=false AND
  embedding IS NOT NULL` — that predicate *is* the definition of "in the index," and §3's query mirrors
  it exactly (I-005).
- Surfaces: `GET /status` (`api.py:1013`) returns a `data` dict of corpus counts; CLI `status`
  (`cli.py:390`) prints the same. Both are the natural home for a corpus-health field (human + agent
  parity, per the surfaces model).

## 3. Design

- **Pure** `embed_generation_report(rows: list[tuple[str, int]]) -> dict` in a new
  `nexus/index/embed_health.py`. Input = `(embed_model, count)` pairs. It **sorts deterministically by
  `(count desc, model asc)`** (secondary key breaks count ties, I-006) and returns:
  `{"generations": [{"model", "count"} …], "distinct": int, "total": int, "mixed": bool,
  "dominant": str | None}` where `total` = **sum of counts** (indexed chunks across generations, I-007),
  `distinct` = number of generations, `mixed = distinct > 1`, and `dominant` = the first generation
  after the deterministic sort (`None` if empty). Empty input ⇒ `{[], 0, 0, False, None}`.
- **No threshold (I-003):** *any* second generation sets `mixed`. A guardrail should surface, not hide,
  a split; the returned `generations` counts make the proportion self-evident, so a single stray/legacy
  chunk reads as an obvious `{99.9%, 1}` rather than an alarm — a percentage threshold would be
  guessing. The operator judges expected-migration vs accident from the distribution.
- **DB helper** `fetch_embed_generations() -> list[tuple[str, int]]` (same module): 
  `SELECT embed_model, count(*) FROM chunks WHERE status='active' AND is_quarantined=false AND
  embedding IS NOT NULL GROUP BY embed_model`. The WHERE clause is **identical to the `idx_chunk_vector`
  partial predicate** (§2) — counting exactly the vectors in the index; unembedded chunks (stale default)
  are excluded. This is a single grouped aggregate; at the target ~100-person corpus it is cheap, and it
  runs only on a `/status`/CLI call. At much larger corpora an index on `embed_model` or a short cache
  would help — deferred (I-004), not needed now.
- **Surfacing (parity):** `/status` adds `data["embed_generations"] = embed_generation_report(await
  fetch_embed_generations())` inside the existing `db_connected` block. CLI `status` prints the
  generations and, when `mixed`, a visible warning line naming the models. Both read-only.

## 4. Non-goals (deferred to the KURE embedding swap — demand-pull)

- **blue-green / alias / shadow-table index, dimension change (768→1024), full re-embed
  orchestration, canary-distance baseline** — these are *components of* an embedding migration, not
  standalone guardrails, and their correct shape is determined by the migration's target (e.g. KURE's
  1024d). Built then, as one piece.
- **query↔top-K cosine-similarity drift over time** — a separate signal (would extend `search_log`);
  not this guardrail.
- **Auto-remediation** (triggering a re-embed) — this SPEC only *reports*; acting is the operator's.
- **Per-tenant breakdown** — the vector index generation is a physical, tenant-agnostic property;
  global distribution is the right granularity here.

## 5. Testing

- **Pure** (`embed_generation_report`): one model ⇒ `mixed False`, `dominant` set, `distinct 1`;
  two models ⇒ `mixed True`, `dominant` = larger, generations sorted desc; empty ⇒
  `{generations: [], distinct: 0, total: 0, mixed: False, dominant: None}`.
- **Determinism:** count ties sort by model name ascending (`dominant` stable across runs).
- **Integration** (`pytest.mark.integration`, disposable test DB 5433): insert two active, embedded
  chunks with **different** `embed_model` (and one with `embedding IS NULL` on a third model to prove it
  is excluded); `fetch_embed_generations()` returns exactly the two embedded generations, and the report
  is `mixed True` with the right `total`.
- **Surface (I-008):** the `/status` field is thin wiring over the tested `fetch`+`report`; an API-level
  assertion that `status()` returns an `embed_generations` dict with the `mixed`/`generations` keys, and
  the CLI `status` echo, are exercised at verification (calling `status()` / running the command) rather
  than by a browser — the logic that could be wrong lives in the two functions above.

## 6. Acceptance

`GET /status` and CLI `status` expose the embedding-generation distribution of the searchable corpus
(the vectors matched by `idx_chunk_vector`'s predicate) and flag `mixed` when more than one generation is
present, with a deterministic `dominant`. The check is read-only, pure where it counts, adds no write
path, and leverages the existing `embed_model` column — a visible partial-re-embed guardrail before any
embedding swap, without pre-building the migration itself. The pure report + DB helper are unit/integration
tested; the two surface hooks are thin wiring driven at verification.
