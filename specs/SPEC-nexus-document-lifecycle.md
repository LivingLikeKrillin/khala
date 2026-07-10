---
id: SPEC-nexus-document-lifecycle
type: spec
title: Document lifecycle — origin, search, hide, and the inverse of every destructive
  act
status: approved
date: 2026-07-10
linked_adrs:
- ADR-0006
tags:
- nexus
- surface
- usability
- lifecycle
- reversibility
approved_by: LivingLikeKrillin
reviewed_at: '2026-07-10T03:26:47Z'
content_hash: sha256:ba45518841bf80b895a135b901476019d1f49c66a05eea61e8efbefc1d827ca1
---

# Document lifecycle

> The 2026-07-10 audit: *"The safety of a destructive action currently depends on which week
> it was written."* `supersede` removes a document from every search with no dry-run, no
> confirmation, and **no inverse**. An uploaded document cannot be removed from the browser at
> all. The Documents view is a read-only table that does not even show where a document came from.

## 1. Goal

Every destructive act on a document is reversible from the surface that performed it, and the
Documents view becomes the place a person actually manages a corpus: search it, see where each
document came from, open the original, hide one, put it back.

Same rule as the source console: **capability → HTTP endpoint → (web view · MCP tool · CLI).**

## 2. Non-goals

Hard delete (rows and chunks always survive; only `status` moves), bulk operations, document
editing, versioned diff of a document's content.

## 3. What exists

| Piece | State |
|---|---|
| `soft_delete` / `revive` primitives | `nexus/nexus/lifecycle.py` — exist, reachable only from Notion reconciliation |
| `supersede` | `nexus/nexus/supersede.py` — CLI + `POST /supersede`, no UI, **no inverse** |
| `GET /documents` | `nexus/nexus/api.py` — `offset`/`limit` only. No search, no status filter |
| Documents view | `nexus/nexus/web/js/views/documents.js` — read-only table; renders no origin, no actions |
| Delete / hide from the browser | **absent everywhere** |
| `documents.source_uri` | present: `default:ext-notion-{page_id}.md`, `default:<path>.md` |
| Manual-hold flag | **absent** — see §4.1, this is the load-bearing gap |

## 4. Design

### 4.1 A manual hide must survive the next sync

Reconciliation revives any `soft_deleted` document that is still live in Notion
(`notion_reconcile.plan_reconcile`). So if a person hides a Notion-sourced document by hand, the
next sync **un-hides it**, silently, because the page is still there. The two features would
fight each other.

Migration `003` adds:

```sql
ALTER TABLE documents ADD COLUMN IF NOT EXISTS hold BOOLEAN NOT NULL DEFAULT false;
```

`hold` means *a human decided this document should not be in search, regardless of its source.*

**Invariant:** reconciliation never revives a document with `hold = true`, and never clears
`hold`. Only an explicit restore clears it. Prune is unaffected — a held document is already
`soft_deleted`, and prune selects only `active` rows.

`hold` is orthogonal to `status`. Hiding sets `status='soft_deleted'` **and** `hold=true`.
Restoring clears both. A document pruned by reconciliation has `hold=false`, so a later sync
that finds the page again revives it — which is the behaviour SPEC-nexus-notion-reconciliation
promised, and this SPEC does not change.

### 4.2 `unsupersede` — the missing inverse

```sql
UPDATE documents SET status='active', superseded_by='' WHERE rid=$1 AND tenant=$2 AND status='superseded';
UPDATE chunks    SET status='active'
 WHERE doc_rid=$1 AND status <> 'active'
   AND hash = (SELECT content_hash FROM documents WHERE rid=$1);
```

Same generation rule as `revive` (`lifecycle.py`): only chunks whose `hash` equals the document's
current `content_hash` come back, so a stale generation is not resurrected. Idempotent; returns
`'unsuperseded' | 'noop'`. Guarded on `status='superseded'` — it can never touch a `soft_deleted`
or `active` row. (`documents.rid` is the primary key and `chunks.doc_rid` references it, so the
sub-select needs no tenant predicate; the document `UPDATE` carries one anyway.)

**Chain guard.** If `v2` superseded `v1`, and `v3` later superseded `v2`, then un-superseding `v1`
would put it back into search *alongside `v3`* — exactly the coexistence ADR-0006 names as the
primary entropy source, created by the very command meant to repair a mistake.

**Invariant:** `unsupersede(rid)` refuses unless the document named by `superseded_by` is itself
`active`. Otherwise `409 chain_broken`, naming the row that must be un-superseded first. A
supersession chain unwinds in reverse order or not at all.

**Durable record.** `v_entropy_signals.supersessions` counts `superseded_by <> ''` over current
state (`migrations/001_supersession.sql:34`), so reversing a supersession self-corrects that signal
— there is no stale count. What is missing is the *reversal itself*: a governance act undone with
no trace. structlog is not a record; it rotates.

Migration `003` therefore adds an append-only ledger, and **both directions write to it**:

```sql
CREATE TABLE IF NOT EXISTS doc_supersession_events (
    id            BIGSERIAL PRIMARY KEY,
    rid           TEXT NOT NULL,
    tenant        TEXT NOT NULL,
    action        TEXT NOT NULL CHECK (action IN ('superseded', 'unsuperseded')),
    superseded_by TEXT NOT NULL DEFAULT '',   -- the rid set, or the rid discarded
    reason        TEXT NOT NULL DEFAULT '',
    at            TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_supersession_events_rid ON doc_supersession_events (tenant, rid, at);
```

`unsupersede` requires a `reason` (non-empty after strip) and writes it there in the same
transaction as the status change. `supersede` writes its own event with an empty reason — it is not
gaining a required-reason argument in this SPEC, only a record. Neither act is blocked; neither is
silent.

### 4.3 Origin is derived, not stored

No new column. `source_uri` already carries it:

| `source_uri` | `origin` | `origin_url` |
|---|---|---|
| `<tenant>:ext-notion-<page_id>.md` | `notion` | `https://www.notion.so/<page_id, dashes stripped>` |
| `<tenant>:uploads/...` (the `/upload` default path) | `upload` | none |
| anything else | `file` | none |

Three origins, not two: an upload and a repo file are different answers to "where did this come
from", and conflating them defeats the column's purpose.

The API returns `{origin, origin_url, source_uri}`. `source_uri` goes out too — for a `file` the
path *is* the answer, and no derived label replaces it.

The Notion page id is the `ext-notion-` suffix minus `.md`; it is canonical (dashed lowercase,
`notion_ids.canonical_page_id`) because the importer wrote it that way. Stripping dashes yields the
form Notion accepts in a URL. If the suffix is not a canonical page id, `origin_url` is `null`
rather than a guess.

### 4.4 Endpoints

| Method | Path | Capability | Notes |
|---|---|---|---|
| `GET` | `/documents` | — (read) | gains `q` (title substring, case-insensitive), `status` (`active`\|`hidden`\|`superseded`\|`all`, default `active`), `origin` (`notion`\|`file`). Returns `origin`, `origin_url`, `hold`, `status`. |
| `GET` | `/documents/{rid}` | — (read) | one document + its active chunk count + `superseded_by` |
| `POST` | `/documents/{rid}/hide` | `manage_documents` | `soft_delete` + `hold=true`. Idempotent. Refuses a `superseded` row (`409 already_superseded`) — it is already out of search, and `hold` on a non-`soft_deleted` row is an undefined state. |
| `POST` | `/documents/{rid}/restore` | `manage_documents` | `revive` + `hold=false`. Refuses a `superseded` row (`409`) — that needs `unsupersede`, which is a different decision. |
| `POST` | `/documents/{rid}/unsupersede` | `manage_documents` | body `{reason}`; `400` if empty |
| `POST` | `/supersede` | `manage_documents` | **existing endpoint, now capability-gated** (it is destructive and was open to any principal) |

**The `status` filter accepts every state it can report**, or a row becomes unreachable:

| filter value | rows |
|---|---|
| `active` (default) | `status='active'` |
| `hidden` | `status='soft_deleted' AND hold=true` — a person hid it |
| `pruned` | `status='soft_deleted' AND hold=false` — reconciliation removed it because the page is gone |
| `superseded` | `status='superseded'` |
| `all` | every row, quarantined excluded as today |

`hidden` and `pruned` are the same row shape with different causes, and the UI must say different
sentences — *"you hid this"* vs *"removed from Notion"* — because the restore semantics differ: a
pruned document comes back on its own if its page returns, a held one never does.

`manage_documents` is a distinct capability from `manage_sources`: choosing where documents come
from and hiding individual documents are different powers.

**Gating `POST /supersede` is a breaking change and is stated as one.** It ships today with no
capability check, so any principal that can authenticate can remove a document from every search.
After this SPEC an explicitly configured principal without `manage_documents` gets `403` — including
the MCP server's `NEXUS_MCP_TOKEN` principal, whose `nexus_supersede` tool will stop working until
the capability is granted. `auth.local_dev_capabilities` defaults to
`["manage_sources", "manage_documents"]`, so the local web UI and the dev-token MCP path keep
working. The exposure note from SPEC-nexus-notion-source-console §4.7 applies unchanged and now
covers document deletion: behind a tunnel, whoever Cloudflare Access admits can hide documents.

### 4.5 The web view

Documents gains: a **title** search box (debounced, hits `q`), a status filter, an **출처** column
with a badge (Notion / 업로드 / 파일) that links to the original when there is one, a chunk count,
and per-row actions.

`q` matches titles, not content. Content search is what the 채팅 view already does through
`/search`; duplicating it here would be a second, worse retrieval path. The box is labelled
**제목 검색** so it does not promise otherwise.

**Hiding asks first.** A confirm panel names the document and says what will happen — *"검색에서
사라집니다. 문서와 청크는 지워지지 않으며 언제든 되돌릴 수 있습니다."* — because the sentence is
true and because a destructive control with no sentence is how `supersede` got shipped.

Hidden and pruned rows appear only when the filter asks for them, greyed, each with a **되돌리기**
button. A `superseded` row shows what superseded it, and its restore button reads **supersession
취소** and requires a reason — a different word for a different act.

### 4.6 CLI and MCP

- CLI: `nexus doc hide <ref>`, `nexus doc restore <ref>`, `nexus unsupersede <ref> --reason "..."`.
  `<ref>` resolves through the existing `resolve_active_doc` (rid | path | basename), extended to
  find non-active rows for restore.
- MCP: `nexus_documents_search`, `nexus_document_hide`, `nexus_document_restore`,
  `nexus_unsupersede`. Thin wrappers, same endpoints.

## 5. Error handling

| Condition | Result |
|---|---|
| hide an already hidden document | `200`, `{result: "noop"}` |
| restore a `superseded` document | `409 use_unsupersede` |
| restore an `active` document | `200`, `noop` |
| `unsupersede` a non-superseded document | `409 not_superseded` |
| `unsupersede` with empty reason | `400 reason_required` |
| any of the above without `manage_documents` | `403` |
| ambiguous `<ref>` in CLI | existing `ValueError` listing candidates |

## 6. Testing

**Unit:** origin derivation from every `source_uri` shape — notion (dashed page id → dashless URL),
`uploads/` prefix → `upload`, anything else → `file`, and a malformed `ext-notion-` suffix → `origin_url`
is `null`, never a guessed URL. `status` filter value → SQL predicate mapping, including `pruned`.

**Integration (real Postgres — the `nexus-postgres` job now runs these):**

- hide → the document and its **active** chunks become `soft_deleted`, `hold=true`; a stale
  superseded chunk generation is untouched.
- **A held document survives reconciliation.** Its Notion page is still live; a reconcile run
  leaves it `soft_deleted` and `hold=true`. This is the §4.1 invariant and the reason this SPEC
  exists in this order.
- A *pruned* document (`hold=false`) is still revived when its page reappears — the reconciliation
  contract is not weakened.
- restore → `active` again, only the current chunk generation.
- restore refuses a `superseded` row; `unsupersede` accepts it and refuses everything else.
- `unsupersede` restores only the current generation and clears `superseded_by`.
- `unsupersede` with an empty (or whitespace-only) reason is rejected **before any write** — the
  document stays `superseded` and no event row appears.
- `unsupersede` refuses with `409 chain_broken` when the superseding document is itself superseded,
  and names it. Unwinding in reverse order succeeds.
- `hide` refuses a `superseded` row.
- Both `supersede` and `unsupersede` append exactly one `doc_supersession_events` row, in the same
  transaction as the status change: a rolled-back status change leaves no event, and vice versa.
- `supersede` without `manage_documents` is `403`; with it, `200`.

**Browser:** hide a document from the list, confirm, watch it leave search and the header count
drop; filter to hidden, restore it, watch it come back.

## 7. Acceptance

1. From the browser: search the corpus by title, see each document's origin, click through to the
   Notion page it came from.
2. Hide a document after a confirm that names it. It leaves search. The row and chunks remain.
3. Restore it. It returns to search with only its current chunk generation.
4. Hide a Notion-sourced document, run a sync while its page is still live: **it stays hidden.**
5. Let reconciliation prune a document, then restore its Notion page and sync: it comes back.
6. `unsupersede` refuses without a reason; refuses a broken chain naming the blocking document; and
   on success leaves one `doc_supersession_events` row carrying the reason and the discarded
   `superseded_by`.
7. An agent does 2 and 3 through MCP tools, hitting the same endpoints.
8. Every one of these paths is exercised by the `nexus (pytest, postgres)` CI job.
