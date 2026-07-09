---
id: SPEC-nexus-notion-reconciliation
type: spec
title: Notion deletion reconciliation — soft_delete/revive primitives + root-scoped prune
status: draft
date: 2026-07-09
linked_adrs:
- ADR-0002
tags:
- nexus
- notion
- ingestion
- entropy
- lifecycle
---

# Notion deletion reconciliation

> A mirror that never deletes is not a mirror — it is an append-only log that diverges
> from its source monotonically. Nexus ingests Notion additively and idempotently, but a
> page deleted or unshared in Notion **stays in the index forever** and keeps being cited
> as evidence. That is precisely the entropy symptom this project exists to eliminate.

## 1. Goal

Make `nexus ingest-notion` converge on the live Notion tree in **both** directions:

- a page that disappeared from the walked roots becomes `soft_deleted` (drops out of search),
- a page that reappears is **revived** back to `active`,

without ever pruning a page that is merely out of the walk's scope, and without touching
documents that were deliberately `superseded`.

## 2. What already exists (and what is missing)

| Piece | State |
|---|---|
| `resource_status` enum `('active','superseded','soft_deleted')` | `init.sql:11` — exists |
| Search excludes non-active docs and chunks | `search/hybrid.py:74,76,110,112` — exists |
| `supersede()` guard: never cascades into `soft_deleted` rows | `supersede.py:26` + regression test — exists |
| `documents.prov_inputs TEXT[]` (CRM provenance slot) | `init.sql` — exists, currently empty for every row |
| `NotionSource.live_ids()` — full descendant enumeration, all-or-nothing | `notion.py:98` — exists |
| **Any code that writes `soft_deleted`** | **absent — 0 call sites** |
| **Any deletion/reconciliation path** | **absent** |

The status value, the search filter, and the guards were designed for this. Only the
writer is missing.

## 3. Design

### 3.1 Root provenance

`build_csf()` carries the roots that reach a page into `provenance.source_roots`. The
external-ingest sink writes them to `documents.prov_inputs`.

**The sink must write `prov_inputs` even on an idempotent hit.** Today it skips the
label/`doc_type` writes when nothing was re-indexed; an unchanged page would therefore
never acquire provenance. Writing it unconditionally (still never on a quarantined row)
also backfills the rows ingested before this SPEC on the first full run — no schema
migration, no backfill script.

### 3.2 The prune predicate

Naively pruning "everything under the walked roots that is no longer live" is **wrong**.
A page reachable from both root `A` and root `B` is absent from `live(A)` when only `A`
is walked, yet it is still alive under `B`.

The sound predicate is **containment**: a document is a prune candidate only if every
root it came from was walked in this run.

```sql
WHERE tenant = $1
  AND source_uri LIKE $2          -- '<tenant>:ext-notion-%'
  AND prov_inputs <> '{}'         -- unattributed rows are never pruned
  AND prov_inputs <@ $3           -- ⊆ walked_roots
```

`{A,B} ⊄ {A}` — the shared page is excluded. One Postgres array operator.

### 3.3 Reconciliation runs *after* the ingest pass

Order is load-bearing. During the ingest pass a `soft_deleted` document is invisible to
the collector's dedup query (which filters `status='active'`), so it is re-ingested and
its chunks are rewritten. Reconciliation then flips the statuses:

- `prune`  = `scope[status='active']` − `live_rids`  → `soft_delete()`
- `revive` = `scope[status='soft_deleted']` ∩ `live_rids` → `revive()`

`superseded` documents are in neither set. They are never revived and never pruned.

### 3.4 `soft_delete` / `revive` primitives

Reviving a document must not resurrect **stale chunk generations**. When a document's
text changes, its old chunks stay behind as `superseded`; blindly setting every chunk of
`doc_rid` back to `active` would bring dead text back into search.

The current generation is identifiable: `pipeline.py` writes `chunks.hash` and
`documents.content_hash` from the same value. So:

```sql
-- soft_delete: only active rows; old superseded generations untouched
UPDATE documents SET status='soft_deleted' WHERE rid=$1 AND tenant=$2 AND status='active';
UPDATE chunks    SET status='soft_deleted' WHERE doc_rid=$1 AND status='active';

-- revive: only from soft_deleted (never from superseded), only the current generation
UPDATE documents SET status='active' WHERE rid=$1 AND tenant=$2 AND status='soft_deleted';
UPDATE chunks    SET status='active'
 WHERE doc_rid=$1 AND status <> 'active'
   AND hash = (SELECT content_hash FROM documents WHERE rid=$1);
```

Both are idempotent and return `'soft_deleted' | 'revived' | 'noop'`.

**The pipeline's `ON CONFLICT DO UPDATE` must not be changed to reset `status`.** It would
resurrect deliberately superseded documents on every re-ingest. Revival stays explicit and
confined to this path.

### 3.5 Safety

- `--reconcile` is **opt-in**. Without it `ingest-notion` behaves exactly as today.
- `--dry-run` reports the plan and applies nothing.
- If the prune set exceeds **50%** of the active scope, the run **refuses** and reports,
  unless `--force`. This is the last line of defence against a mis-typed `--roots`.
- `live_ids()` raises on enumeration failure, so a partial tree walk can never be mistaken
  for "these pages were deleted". Per-page *fetch* failures do not affect pruning — a page
  that failed to fetch is still enumerated, hence still live.

## 4. Known limits (accepted)

- **A page moved out of the walked roots is indistinguishable from a deleted page**, as is
  a page whose integration share was revoked. Both get pruned. This is self-healing: the
  next run that walks the page's new location revives it.
- Attribution is per-run. A document ingested before this SPEC has empty `prov_inputs` and
  is therefore never a prune candidate until one full run re-attributes it.
- Walking per root visits shared subtrees once per root. With no rate-limit backoff in the
  Notion client, very large trees may need `--roots` split across runs — which is exactly
  what the containment predicate makes safe.

## 5. Out of scope

Persisting `roots` in `config.yaml`, Notion webhooks, rate-limit backoff, hard delete.

## 6. Acceptance

1. `live_index()` maps each page to the set of walked roots that reach it; a page under two
   roots reports both.
2. A doc whose `prov_inputs` is not a subset of the walked roots is never pruned.
3. A pruned doc leaves search; its row and chunks remain, `status='soft_deleted'`.
4. A revived doc returns to search with **only** its current chunk generation active.
5. `supersede`d docs are untouched by both directions.
6. Prune ratio over 50% refuses without `--force`.
7. `--dry-run` mutates nothing.
