---
id: SPEC-nexus-graph-scope-filter
type: spec
title: The graph channel must obey base_filter — stop cross-tenant / over-clearance
  / quarantined leakage
status: approved
linked_adrs:
- ADR-0004
- ADR-0006
tags:
- nexus
- graph
- security
- base-filter
approved_by: LivingLikeKrillin
reviewed_at: '2026-07-11T18:00:51Z'
content_hash: sha256:41864fb750d82d641644a22879b26c56aa75e65fd6743402edf5141eab27cf09
---

## 1. Goal

Close a confirmed correctness/security leak found during the query-quality review: the **graph
relationship channel bypasses `base_filter`**. BM25 and vector legs correctly enforce
`tenant / classification <= clearance / is_quarantined = false / status = 'active'`, but the graph
enrichment does not — so a query can surface entity names, edge types, and confidence for entities in
**other tenants**, **above the caller's clearance**, or **quarantined**. This violates the CLAUDE.md
invariant "base_filter … 예외 없음" and "quarantined 리소스를 검색 결과에 포함 금지".

## 2. The leak (verified 2026-07-11)

- `f_graph_neighbors(p_entity_rid, p_max_hops)` (`init.sql:316-338`): the recursive CTE joins both
  endpoint entities (`ef`, `et`) but filters **only** `e.status = 'active'`. No tenant, no
  classification, no `is_quarantined`, no entity `status`. A 2-hop walk (default `graph_hops = 2`)
  follows any active edge into any tenant / any classification / quarantined entity.
- The observed-edges query in `get_neighbors` (`repositories/graph.py:146-159`): same — filters only
  `o.status = 'active'`.
- `find_path` (`repositories/graph.py:264-`): same inline CTE, `e.status='active'` only — a latent
  leak on the same shape.
- The center-name lookup (`repositories/graph.py:124`) has no tenant/clearance filter — it can
  confirm the existence and name of an out-of-scope seed entity.
- **The graph evidence-snippet channel leaks document *content* (worst of all, I-001).**
  `GET /graph/{rid}?include_evidence=true` (`api.py:589-606`) fetches, per edge,
  `SELECT ev.note, c.chunk_text, c.section_path, d.title FROM evidence ev LEFT JOIN chunks c … LEFT
  JOIN documents d … WHERE ev.subject_rid = $1 AND ev.status = 'active'` — **no tenant, no
  classification, no `is_quarantined`, no chunk/doc `status`**. This returns actual `chunk_text` (200
  chars of document body) for any edge, regardless of the caller's scope. Unlike the relationship
  leak, this exposes **document content**, so it is the highest-severity path here.
- `entities` carries the full CRM columns (`tenant`, `classification`, `is_quarantined`, `status` —
  `init.sql:117-140`), and `chunks`/`documents` carry theirs, so every path *can* be filtered; the
  queries simply don't.

Blast radius: the **relationship layer** (entity names, edge types, confidence, observed metrics)
**and — via the evidence channel — document chunk content**. The BM25/vector chunk legs are correctly
filtered; the graph channel and its evidence sidecar are not. The invariant is absolute.

## 3. What exists

- `GraphRepository` Protocol + `PostgresGraphRepository` (`repositories/graph.py`).
  `get_neighbors(entity_rid, hops)` — **no** tenant/clearance params. Callers:
  `search/hybrid.py:332` (search enrichment — **has** `tenant`+`clearance` in scope),
  `api.py:563` (`GET /graph/{rid}` — has a principal → scope), `cli.py:303` (`nexus graph`).
- `hybrid_search(query, tenant, clearance, …)` already threads the scope for the BM25/vector legs.
- Migrations are versioned SQL under `migrations/00N_*.sql`, applied by the update path (last is
  `003_document_lifecycle.sql`).

## 4. Design

**Every graph relationship read takes the caller's `(tenant, clearance)` and enforces it on both
endpoint entities.** An edge is returned only if **both** its endpoints satisfy
`tenant = caller_tenant AND classification <= clearance AND is_quarantined = false AND
status = 'active'`. The same predicate the chunk legs use, applied to entities.

### 4.1 SQL (migration `004_graph_scope_filter.sql`)

`DROP FUNCTION IF EXISTS f_graph_neighbors(TEXT, INT)` (idempotent — the migration re-applies
cleanly, I-008) and recreate as
`f_graph_neighbors(p_entity_rid TEXT, p_max_hops INT, p_tenant TEXT, p_clearance classification_level)`.
Both the base and recursive members add, for `ef` and `et`, **all four** predicates:
`AND ef.tenant = p_tenant AND ef.classification <= p_clearance AND ef.is_quarantined = false
AND ef.status = 'active'` (and the same for `et`). The signature change forces the DROP (a new arg
list is a new overload, not a replace).

**Traversal semantics change, by design (I-006):** filtering endpoints *inside* the recursive member
means the walk **stops at scope boundaries** — an in-scope entity reachable only *through* an
out-of-scope entity becomes unreachable. That is the correct security behaviour: you cannot hop a
path you are not allowed to see. The SPEC states this explicitly so it is not mistaken for a bug.

`find_path` is **not** a DB function — it is an inline recursive CTE in Python (`graph.py:264`,
I-009); it is fixed in the repository (§4.2), not in the migration. `f_graph_neighbors` is the only
DB function this migration touches.

### 4.2 Repository

`get_neighbors(entity_rid, hops, tenant, clearance)` (Protocol + Postgres impl) — required params, no
scope-defaulting default (a missing-scope call is a call error, not a silent leak). It:
- passes the two new args to `f_graph_neighbors`;
- adds the four-predicate endpoint filter to the inline **observed-edges** query (`ef`/`et`);
- adds tenant/clearance/quarantine/status to the **center-name** lookup — an out-of-scope seed
  resolves to an empty subgraph, never a leaked name.

`get_subgraph(center_rid, radius, tenant, clearance)` delegates to `get_neighbors` (`graph.py:181`),
so it threads the same scope. `find_path(from_rid, to_rid, max_hops, tenant, clearance)` gains the
same endpoint filter on its inline CTE.

### 4.3 The graph evidence-snippet channel (§2's worst leak)

`GET /graph/{rid}?include_evidence=true` (`api.py:589-606`) joins `evidence → chunks → documents`
with no scope. The fix adds the **chunk/document base_filter** to that query:
`AND c.tenant = :tenant AND c.classification <= :clearance AND c.is_quarantined = false
AND c.status = 'active' AND d.status = 'active'`. An edge whose backing chunk is out of scope yields
**no** evidence snippet (the edge may still render if its endpoints are in scope, but its content
does not leak). This is the same predicate the BM25/vector legs already apply to chunks.

### 4.4 Callers thread the scope

- `hybrid.py` graph enrichment passes the `tenant`/`clearance` it already holds.
- `GET /graph/{rid}` (`api.py`) resolves scope from the principal (the same `effective_scope` the
  search endpoints use) and passes it to `get_neighbors` **and** the evidence query.
- `nexus graph` (`cli.py`) has **no clearance concept** (I-002); it passes `tenant="default"` (its
  existing default) and a fixed **`INTERNAL`** clearance — stated explicitly here, not hand-waved as
  "existing defaults". A local operator CLI at INTERNAL is the documented ceiling; RESTRICTED graph
  reads are not a CLI path.

## 5. Non-goals

- **Making graph a ranking signal.** This SPEC only *scopes* the existing graph channel; it does not
  add graph hits to RRF (a separate quality concern).
- **Row-level security / policy engine.** The fix is the same explicit predicate the other legs use,
  not a new authorization framework.
- **Re-checking already-filtered chunk legs.** BM25/vector are correct; untouched.

## 6. Testing

DB-backed (the integration fixture, `_disposable_test_db`), because the leak is in SQL:

- Seed: tenant `A` entities `a1—a2` (edge), a cross-tenant edge `a1—b1` (b1 in tenant `B`), a
  `RESTRICTED` entity `a_secret` edged to `a1`, and a **quarantined** entity `a_quar` edged to `a1`.
- `get_neighbors(a1, hops=2, tenant="A", clearance="INTERNAL")` returns `a2` and **never** `b1`
  (cross-tenant), `a_secret` (over-clearance), or `a_quar` (quarantined). Asserted on names and edge
  presence.
- `clearance="RESTRICTED"` **does** surface `a_secret` (the filter narrows, it doesn't blanket-deny).
- An out-of-scope seed (`get_neighbors(b1, …, tenant="A", …)`) returns an empty subgraph with no
  leaked center name.
- The observed-edges path is covered with a cross-tenant observed edge — same exclusion.
- **The evidence-snippet channel (§4.3):** an edge whose backing chunk is in another tenant / above
  clearance / quarantined returns **no** `chunk_text` from `GET /graph/{rid}?include_evidence=true`.
  This is the content-leak test and is asserted directly.
- A unit test pins that the SQL for observed-edges / center-name / evidence contains **all four**
  predicates — tenant, classification, `is_quarantined`, `status` (I-007) — not just two.
- **The direct DB-function caller is updated (I-004):** `tests/test_e2e.py:196` calls
  `f_graph_neighbors($1, 1)` with the old 2-arg signature; it is updated to the 4-arg signature.
  "existing tests still pass" is made true by fixing this call, not assumed.

## 7. Acceptance

A search whose route enrichment touches the graph (`hybrid_then_graph` / `graph_then_hybrid`), and a
`GET /graph/{rid}` (with or without `include_evidence`), return **only** relationships whose both
endpoints — and only evidence whose backing chunk — satisfy `tenant = caller_tenant AND
classification <= clearance AND is_quarantined = false AND status = 'active'`. A cross-tenant edge, a
RESTRICTED neighbor at INTERNAL clearance, a quarantined entity, and an out-of-scope evidence snippet
are each absent.

The claim is scoped to **that four-part predicate** — the one the chunk legs already enforce — not to
full parity with every chunk-leg behaviour: document **supersession** (ADR-0006) is a doc-lifecycle
concern the graph edges do not model, and this SPEC does not extend supersession semantics to the
graph (I-003). It closes the base_filter hole; it does not claim the graph is now identical to the
chunk legs in every respect.
