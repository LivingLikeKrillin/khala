---
id: SPEC-nexus-notion-reconciliation
type: spec
title: Notion deletion reconciliation — soft_delete/revive primitives + root-scoped
  prune
status: approved
date: 2026-07-09
linked_adrs:
- ADR-0006
tags:
- nexus
- notion
- ingestion
- entropy
- lifecycle
approved_by: LivingLikeKrillin
reviewed_at: '2026-07-09T14:37:12Z'
content_hash: sha256:7109c7b51f2d23c055a78989d6917a8c31bfe9e916099ec49f6bf9459ed0d7a7
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

**Root identifiers are canonical Notion page ids** — lowercase UUID *with* dashes, the form
the API returns. `--roots` accepts the dash-less 32-hex form people copy out of a browser URL
and normalises it (`notion_ids.canonical_page_id`). Without this the root page is enumerated
under the caller's spelling while its children carry the API's, so the same page lands under
two different `doc_rid`s and the containment predicate below compares incomparable strings.
Both sides of `<@` — `prov_inputs` and `walked_roots` — are canonical by construction.

`build_csf()` carries into `provenance` both the roots that *reached* this page
(`source_roots`) and the roots this run *walked* (`walked_roots`). The external-ingest sink
uses them to update `documents.prov_inputs`:

```
prov_inputs := (prov_inputs \ walked_roots) ∪ source_roots
```

**Not a wholesale replace.** A run that walks only root `A` must not erase the record that the
page is also reachable from `B` — that record is exactly what stops `B`'s page from being
pruned by an `A`-only run (§3.2). **Nor an append**: a root that no longer reaches the page
must drop out, or the document becomes permanently un-prunable. Refreshing only the walked
roots is the one rule that satisfies both.

**The sink must write `prov_inputs` even on an idempotent hit.** `a2a/server.py` skips the
label/`doc_type` writes when nothing was re-indexed; an unchanged page would therefore never
acquire provenance. Writing it unconditionally (still never on a quarantined row) backfills
**still-live** pre-SPEC rows on the first full run — no schema migration, no backfill script.

> This backfill reaches only pages that are still walked. A page deleted from Notion *before*
> this SPEC shipped will never be enumerated again, so it never acquires `prov_inputs` and is
> **permanently outside the prune scope**. Those rows need a one-time manual cleanup; the
> reconciler will not remove them. Failing in this direction is deliberate.

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
the collector's dedup query — it looks only at active rows
(`ingest/collector.py:78`: `... WHERE source_uri = $1 AND tenant = $2 AND status = 'active'`)
— so an unchanged soft-deleted page is treated as new, re-ingested, and its chunks rewritten
(as `superseded`, since `ingest/pipeline.py:132` derives chunk status from the parent's).
Reconciliation then flips the statuses:

- `prune`  = `scope[status='active']` − `live_rids`  → `soft_delete()`
- `revive` = `scope[status='soft_deleted']` ∩ `live_rids` → `revive()`

`superseded` documents are in neither set. They are never revived and never pruned.

### 3.4 `soft_delete` / `revive` primitives

Reviving a document must not resurrect **stale chunk generations**. When a document's
text changes, its old chunks stay behind as `superseded`; blindly setting every chunk of
`doc_rid` back to `active` would bring dead text back into search.

The current generation is identifiable: `ingest/pipeline.py` binds the same
`collected.content_hash` to `documents.hash` + `documents.content_hash` (`pipeline.py:80`, bound
at `:97`) and to `chunks.hash` (`pipeline.py:156`, bound at `:173`).
So `chunks.hash = documents.content_hash` selects exactly the generation written by the last
ingest of that content.

> **Invariant (hash collision is benign).** Two generations can share a `content_hash` only if
> their content is identical. Chunk rids are derived from `(doc_rid, section_path, chunk_index)`
> — not from text (`rid.py: chunk_rid`) — so identical content re-writes the same rids. A stale
> chunk carrying the current `content_hash` therefore *is* a chunk of the current content. Reviving
> it is correct, not a resurrection.

**Invariant (atomicity).** Each primitive updates `documents` and `chunks` inside one
transaction (`lifecycle.py`, `async with conn.transaction()`). A document is never observed
`soft_deleted` with active chunks, nor `active` with none — states the search filters and the
`supersede()` guard were not designed for.

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
  unless `--force`. The figure is a heuristic, not a derived bound: it is tunable
  (`--threshold`) and it is a *tripwire*, not a proof. It does not catch a mis-typed `--roots`
  that happens to affect under half the scope, and it will refuse a legitimate bulk cleanup —
  which is what `--force` is for. Its only job is to turn the catastrophic case (a typo that
  makes the whole corpus look deleted) from silent into loud. The containment predicate (§3.2)
  is what provides the actual correctness guarantee; this is defence in depth.
- `live_index()` raises on enumeration failure, so a partial tree walk can never be mistaken
  for "these pages were deleted". Enumeration is **decoupled from per-page content fetch**:
  `_collect` walks via `blocks.children.list` / `databases.query` and lets exceptions
  propagate (`notion.py`), while `page_ref`/`fetch_markdown` failures are caught per page by
  `import_notion` and counted as `skipped`. A page whose *content* failed to fetch is still
  enumerated, hence still live, hence never pruned.

## 4. Known limits (accepted)

- **A page moved out of every walked root is indistinguishable from a deleted page**, as is
  a page whose integration share was revoked. Both get pruned. This is self-healing: the
  next run that walks the page's new location revives it.
- A document ingested before this SPEC has empty `prov_inputs` and is never a prune candidate
  until a run walks it again and attributes it. **A page deleted before this SPEC shipped is
  therefore never pruned at all** — it will never be walked. Such rows require a one-time
  manual `soft_delete`; see §3.1.
- Attribution converges rather than being exact on the first partial run. A page reachable from
  `A` and `B` that has only ever been walked under `A` carries `prov_inputs={A}`; an `A`-only run
  that no longer reaches it **will** prune it, and a later run walking `B` revives it. Walking the
  full root set once makes attribution complete and removes this window.
- Walking per root visits shared subtrees once per root. With no rate-limit backoff in the
  Notion client, very large trees may need `--roots` split across runs — which is exactly
  what the containment predicate makes safe.

## 5. Out of scope

Persisting `roots` in `config.yaml`, Notion webhooks, rate-limit backoff, hard delete.

## 6. Acceptance

1. `live_index()` maps each page to the set of walked roots that reach it; a page under two
   roots reports both. A dash-less root id yields the same keys as the API's dashed form.
2. A doc whose `prov_inputs` is not a subset of the walked roots is never pruned.
3. An `A`-only run over a page attributed `{A,B}` leaves `prov_inputs` still containing `B`;
   the page does not become a prune candidate.
4. A pruned doc leaves search; its row and chunks remain, `status='soft_deleted'`.
5. A revived doc returns to search with **only** its current chunk generation active.
   *Fixture:* a `soft_deleted` doc with `content_hash = h2` owning two chunks — one with
   `hash = h2` (current, written `superseded` by the ingest pass) and one with `hash = h1`
   (a stale generation). After revive, exactly the `h2` chunk is `active`.
6. `supersede`d docs are untouched by both directions.
7. Prune ratio over 50% refuses without `--force`; `--force` applies it.
8. `--dry-run` mutates nothing.
