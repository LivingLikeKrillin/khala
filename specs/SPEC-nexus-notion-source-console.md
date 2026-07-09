---
id: SPEC-nexus-notion-source-console
type: spec
title: Notion source console — endpoint-first source management, background sync,
  previewed deletion
status: approved
date: 2026-07-10
linked_adrs:
- ADR-0006
tags:
- nexus
- notion
- surface
- usability
- ingestion
approved_by: LivingLikeKrillin
reviewed_at: '2026-07-09T16:45:13Z'
content_hash: sha256:0d32659f4870f25224e4374a81ce6c0921209674de5e909fab06b60517b8ae4e
---

# Notion source console

> The 2026-07-10 surface audit found that four of Nexus's fifteen capabilities are reachable
> from a browser, and that `ingest-notion` has **no HTTP endpoint at all** — so it is unusable
> by a person *and* by an agent. This SPEC closes that hole for the first capability, and
> establishes the shape every capability will follow.

## 1. Goal

A person opens Nexus in a browser, pastes a Notion page URL, presses **Sync**, watches progress,
reviews what is about to be deleted, and confirms. An agent does the same thing through MCP tools.
Both go through the same HTTP endpoints. Nobody types `docker compose exec`.

**Architectural rule established here:** *capability → HTTP endpoint → (web view · MCP tool · CLI).*
The endpoint is canonical; the three surfaces are thin clients. A capability that skips the API is
lost to both audiences.

## 2. Non-goals

Document delete/undo (separate SPEC), browser authentication (separate SPEC), scheduling UI (cron
stays), multi-tenant admin, multi-replica deployment (§4.2), Confluence or any other source.

## 3. What exists

| Piece | State |
|---|---|
| Notion tree walk, CSF conversion, idempotent ingest | `nexus/nexus/ingest/sources/notion*.py` — works |
| Document identity keyed on Notion page id | **already shipped**: `ext-notion-{page_id}` → canonical uri (`notion_reconcile.py:17-18`) |
| Deletion reconciliation (`soft_delete`/`revive`, containment prune) | `nexus/nexus/lifecycle.py`, `notion_reconcile.py` — works, CLI-only |
| Root list | **a per-invocation `--roots` argument.** No persistence. |
| Any HTTP endpoint | **absent** |
| Any UI | **absent** |
| Background jobs anywhere in Nexus | **absent** — no precedent to follow |
| Capability-gated writes | `Principal.capabilities`, default-deny (`nexus/nexus/auth/principal.py:14-30`) |

### 3.1 Relationship to ADR-0006

ADR-0006 §"Deferred" states: *"Connector-driven stable ids (Confluence/Notion page-id) — pilot C
remains deferred"* (`adr/ADR-0006-nexus-entropy-spine.md:129`). **This SPEC does not open that
pilot.** Notion page-id identity is already the shipped behaviour of the importer; nothing here
extends it to other connectors, and nothing here depends on the deferred cross-source identity
work. What this SPEC persists is the *root list*, not a document identity scheme.

## 4. Design

### 4.1 Roots move to the database

`config.yaml` is a repo file; the browser cannot edit it. Roots therefore live in Postgres
(migration `002`):

```sql
CREATE TABLE IF NOT EXISTS notion_sources (
    tenant     TEXT NOT NULL,
    root_id    TEXT NOT NULL,          -- canonical dashed page id
    label      TEXT NOT NULL DEFAULT '',
    added_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant, root_id)
);
```

The API accepts a Notion **URL or a bare id, dashed or not**, and canonicalises through
`notion_ids.canonical_page_id` before storing. `--roots` remains as a CLI override; with no
`--roots`, the CLI reads this table.

Persisting roots removes the class of accident where a shortened `--roots` makes a live corpus look
deleted. It does **not** retire the prune-ratio guard (§4.4) — the guard also covers a Notion-side
mistake (someone archives a whole section), which persistence cannot prevent.

### 4.2 Sync is a background job with durable state

Sync takes minutes (Notion API + embeddings). A request/response call would die to a proxy timeout
and would tell a `cron` invocation nothing. So `POST /sources/notion/sync` returns `202 {run_id}`
immediately, and progress is written to Postgres — surviving a browser close, a page reload, and an
app restart.

`run_id` is `uuid4().hex`.

```sql
CREATE TYPE sync_status AS ENUM ('running','succeeded','failed','refused');

CREATE TABLE IF NOT EXISTS notion_sync_runs (
    run_id       TEXT PRIMARY KEY,             -- uuid4 hex
    tenant       TEXT NOT NULL,
    started_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at  TIMESTAMPTZ,
    status       sync_status NOT NULL DEFAULT 'running',
    dry_run      BOOLEAN NOT NULL DEFAULT false,
    reconcile    BOOLEAN NOT NULL DEFAULT false,
    force        BOOLEAN NOT NULL DEFAULT false,
    since        TEXT NOT NULL DEFAULT '',
    walked_roots TEXT[] NOT NULL DEFAULT '{}',
    counts       JSONB NOT NULL DEFAULT '{}',  -- ingested/idempotent/empty/skipped/pruned/revived
    plan         JSONB NOT NULL DEFAULT '{}',  -- {prune:[{rid,title}], revive:[{rid,title}]}
    plan_hash    TEXT NOT NULL DEFAULT '',
    reason       TEXT NOT NULL DEFAULT ''
);

-- Data-level backstop: at most one live run per tenant, independent of the advisory lock.
CREATE UNIQUE INDEX IF NOT EXISTS uq_notion_sync_running
    ON notion_sync_runs (tenant) WHERE status = 'running';
```

**Single-process invariant.** Nexus runs as one uvicorn process; this SPEC assumes that and does not
introduce a job runner. The job is an `asyncio` task on the app process. Multi-replica deployment is
an explicit non-goal (§2) — the design below stays *safe* under it, but is not *complete* for it.

**Mutual exclusion** is `pg_try_advisory_lock(hashtext('notion_sync:'||tenant)::bigint)` held on a
dedicated connection for the job's life, plus the partial unique index above as a data-level
backstop. (`hashtext` is 32-bit, so two tenants can collide onto one lock key. The consequence is
that their syncs serialise — never that one is skipped. The unique index is per-tenant and exact.)

**Crash recovery.** A dead process leaves a `running` row and releases its advisory lock (the
connection dies). The startup sweep therefore does **not** blindly fail every `running` row: for each
one it attempts `pg_try_advisory_lock` on that tenant. Acquiring it proves no live job holds it, so
the row is marked `failed` (reason `interrupted`) and the lock released. A row whose lock is still
held — a job running on another connection or replica — is left alone. This is what makes the sweep
safe even outside the single-process assumption.

**Interrupted apply.** Recovery is to run again. Ingest is idempotent (content-hash), and so is the
destructive half: `soft_delete` and `revive` are status-guarded and return `noop` when already in the
target state (`nexus/nexus/lifecycle.py`). A crash between two `soft_delete` calls therefore leaves a
partially applied plan that the next reconcile completes; it never leaves a document in an
unrepresentable state, because each primitive is a single transaction over its document and chunks.

### 4.3 Prune and supersede are disjoint

Two status pathways exist and the SPEC must say how they meet. They do not.

- `supersede` sets `status='superseded'` + `superseded_by` (ADR-0006 §"Decision").
- Reconciliation sets `status='soft_deleted'` (prune) or back to `'active'` (revive).

**Invariant:** reconciliation never reads or writes a `superseded` document. `plan_reconcile`
selects prune candidates only from `status='active'` and revive candidates only from
`status='soft_deleted'`; `superseded` rows fall in neither set, and `soft_delete`/`revive` are
guarded on the source status. A document deliberately superseded by a human is not resurrected by a
Notion sync, and a pruned document is not mistaken for a superseded one. Both are excluded from
search by the same `status='active'` filter.

### 4.4 Deletion is previewed, then confirmed against the same plan

Two calls, not one:

1. `POST /sources/notion/sync {reconcile: true, dry_run: true}` → walks, applies nothing, records a
   `plan` and a `plan_hash`.
2. `POST /sources/notion/sync {confirm_plan: "<run_id>"}` → **carries no other parameters.** The
   server reads `reconcile`, `force`, `since` and `walked_roots` from the stored run, recomputes the
   plan under exactly those inputs, and applies it only if the recomputed hash equals the stored
   `plan_hash`.

Passing `confirm_plan` together with any of `{reconcile, dry_run, force, since}` is `400`. This is
what stops a preview computed over one root set from being confirmed under another.

Mismatch ⇒ `409 {error: "plan_stale"}`, apply nothing.

```
plan_hash = sha256(
    "roots:"  + ",".join(sorted(walked_roots)) + "\n" +
    "prune:"  + ",".join(f"{rid}:{content_hash}" for rid, content_hash in sorted(prune)) + "\n" +
    "revive:" + ",".join(f"{rid}:{content_hash}" for rid, content_hash in sorted(revive))
)
```

Hashing the rid **set** alone is not enough: the same rids under a different walked-root set, or with
different document content, is a different plan. The roots and each document's `content_hash` are
therefore part of the hash.

**Threshold.** `refused` when `|prune| / |active documents in the reconciliation scope| > threshold`
— the same ratio the CLI already computes in `plan_reconcile` (`notion_reconcile.py`). Default
`0.5`; overridable per request (`threshold`) and per CLI invocation (`--threshold`); bypassed by
`force`. Scope is the containment-filtered set (`prov_inputs <@ walked_roots`), **not** the whole
corpus.

### 4.5 The `--since` trap is deleted, not documented

Today root attribution (`prov_inputs`) is written only by the ingest sink
(`nexus/nexus/ingest/external_metadata.py` → `write_source_roots`). `--since` skips unchanged pages,
so the sink never runs for them, so they never acquire `prov_inputs`, so reconciliation silently
excludes them. The runbook warns about this. **A warning is not a fix.**

`import_notion` already computes `index = source.live_index()` — page → the roots that reach it —
before the ingest loop, independent of `since`. Reconciliation will call `write_source_roots` for
**every** page in that index, not only for the pages the ingest pass touched. Backfill then happens
on any reconcile run, `--since` becomes a pure performance knob, and the "first run must omit
`--since`" rule is deleted from `TEAM_DOGFOOD_DEPLOY.md`.

### 4.6 Endpoints

| Method | Path | Capability | Notes |
|---|---|---|---|
| `GET` | `/sources/notion/roots` | — (read) | roots + per-root active document count + `token_configured` |
| `POST` | `/sources/notion/roots` | `manage_sources` | `{url_or_id, label?}`; canonicalises; `409` on duplicate |
| `DELETE` | `/sources/notion/roots/{root_id}` | `manage_sources` | unregisters. **Deletes no documents** — they stop being walked, and by containment they also stop being prune candidates. The response states this. |
| `POST` | `/sources/notion/sync` | `manage_sources` | `{reconcile?, dry_run?, force?, since?, threshold?}` **or** `{confirm_plan}` → `202 {run_id}` |
| `GET` | `/sources/notion/sync/{run_id}` | — (read) | status, counts, plan, reason |
| `GET` | `/sources/notion/sync/latest` | — (read) | most recent run for the tenant |

All write paths clamp through `effective_scope` like every other write. `NOTION_TOKEN` stays in the
server environment; it is never accepted over HTTP and never returned.

**Failure surfaces are split deliberately.** Conditions knowable *before* work starts are synchronous
and create no run row: `409 sync_in_progress`, `409 plan_stale`, `400` on parameter conflict,
`503 notion_not_configured`. Conditions discovered *during* the walk become the terminal status of an
existing run: `refused` (threshold) and `failed` (enumeration error, crash sweep). A client therefore
learns of the first class from the POST, and of the second by polling.

### 4.7 The capability problem this exposes

`Principal.capabilities` is default-deny, and the injected `local-dev` principal
(`nexus/nexus/auth/config.py:44-49`) carries **none**. If `manage_sources` gates the write endpoints,
the local web UI — whose only credential is that principal — locks itself out of its own console.

Decision: the injected principal's capabilities become configurable, `auth.local_dev_capabilities`,
defaulting to `["manage_sources"]`. Every explicitly configured principal keeps default-deny.

**State the exposure plainly.** `GET /auth/dev-token` hands that principal's bearer to anyone who can
reach it. Granting it `manage_sources` means *anyone who can reach the app can manage sources and
trigger a previewed deletion.* On `localhost` that is the operator. Behind a tunnel it is whoever
Cloudflare Access admits — and **Access is the only thing standing there.** This SPEC does not make
app-level authz depend on a network gate; it makes the dependency explicit and configurable: set
`auth.local_dev_capabilities: []` to keep the local UI read-only. `TEAM_DOGFOOD_DEPLOY.md` §0 and §8
must be updated to say so.

### 4.8 Surfaces over the endpoints

- **Web** — a `소스` nav item beside 채팅·그래프·문서. Root list with label, document count, last sync;
  add-by-URL field; **Sync** button; a progress panel polling `/sync/{run_id}`; a deletion preview
  listing document titles with a **Confirm** button. Follows the existing view contract
  (`render(container)` + registration in `nexus/nexus/web/js/app.js`).
- **MCP** — `nexus_sources_list`, `nexus_sources_add`, `nexus_sources_sync`, `nexus_sync_status`:
  thin wrappers over the same endpoints, like every existing tool.
- **CLI** — `ingest-notion` keeps working; with no `--roots` it reads the table. `--reconcile` applies
  directly without the two-phase confirm, because the operator is typing an explicit auditable
  command; `--dry-run` remains.

## 5. Error handling

| Condition | Surface | Result |
|---|---|---|
| `NOTION_TOKEN` unset | synchronous | `503 notion_not_configured`; UI shows "not connected" |
| Another sync running | synchronous | `409 sync_in_progress` + running `run_id` |
| `confirm_plan` + other params | synchronous | `400 conflicting_params` |
| Stored plan no longer matches | synchronous | `409 plan_stale` |
| Enumeration fails mid-walk | run status | `failed`; **nothing pruned** — `live_index()` raises rather than returning a partial set |
| Per-page fetch fails | counted | `skipped`; the page is still enumerated, hence still live, hence never pruned |
| Prune ratio over threshold | run status | `refused` + `reason`; nothing applied |
| Process dies mid-run | startup sweep | `failed` (`interrupted`), only if the tenant's advisory lock can be acquired |

## 6. Testing

**Unit (no DB).** `plan_hash` is order-independent over the rid lists and *changes* when the walked
roots change or a document's `content_hash` changes. Notion URL → canonical id. Rejection of
`confirm_plan` combined with other parameters.

**Integration (real Postgres).** Root CRUD and canonicalisation, duplicate → 409. The partial unique
index rejecting a second `running` row. The advisory lock refusing a second sync. The startup sweep
failing an orphaned row **and leaving alone** a row whose lock is still held. `confirm_plan` applying
when the hash matches and refusing when a document changed in between. A `superseded` document
untouched by both prune and revive (§4.3). **`prov_inputs` written for a live page that the ingest
pass skipped because of `--since`** — the §4.5 fix, proving reconciliation is correct on a first run
with a watermark.

**End-to-end** with a fake `NotionSource` through the real endpoints: add root → sync → dry-run plan
→ confirm → the document leaves search → the page reappears in Notion → next sync revives it.

## 7. Acceptance

1. From a browser, with no terminal: add a Notion page by URL, sync it, see documents appear.
2. Delete a page in Notion, sync with preview, see it listed, confirm, and it leaves search.
3. During a run, `GET /sync/{run_id}` returns `status='running'` with a `counts` object whose
   `ingested + idempotent + empty + skipped` is non-decreasing across polls; after completion it
   returns a terminal status and `finished_at`. Closing and reopening the browser changes nothing
   about what that endpoint returns.
4. A second `POST /sync` while one runs returns `409` naming the running `run_id`, and creates no row.
5. A `confirm_plan` whose recomputed hash differs returns `409 plan_stale` and applies nothing.
6. An MCP agent performs (1) and (2) through tools, hitting the same endpoints.
7. `nexus ingest-notion --reconcile` with no `--roots` uses the stored roots.
8. In the integration suite: a page that exists in `live_index()` but is skipped by the `--since`
   watermark has `prov_inputs` written by the reconcile step, and a deleted sibling under the same
   roots is pruned in that same first run.
