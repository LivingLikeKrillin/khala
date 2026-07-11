---
target: SPEC-nexus-graph-scope-filter
critiqued_hash: sha256:2fde77ad85c00052a9eceee3602dd2898493516b0ac4e0ddae9a1f15bde0774e
critiqued_at: '2026-07-11T17:57:51Z'
issues:
- issue_id: I-001
  category: missing-invariant
  severity: high
  description: 'The graph endpoint''s evidence-snippet channel is left unscoped and
    unmentioned. `GET /graph/{rid}` with `include_evidence=true` (api.py:589-606)
    returns `c.chunk_text[:200]` joined via `evidence → chunks → documents` filtered
    only by `ev.status=''active''` — no tenant, no classification, no `is_quarantined`,
    no chunk/document status. This directly contradicts the doc''s §2 blast-radius
    claim that ''Document chunk **content** is not leaked'' and the §7 acceptance
    claim that `GET /graph/{rid}` returns ''only'' in-scope data: even after edges
    are endpoint-scoped, an in-scope edge can carry evidence from a quarantined, superseded,
    or higher-classification chunk. The design fixes entities but leaves actual document
    text leaking through the same endpoint.'
  status: accepted
  disposition_reason: null
- issue_id: I-002
  category: undefined
  severity: medium
  description: '§4.3 says `nexus graph` ''passes its configured tenant and clearance
    (the CLI''s existing defaults)'' — but the CLI has no clearance concept at all:
    the `graph` command (cli.py:280-284) takes only `--tenant` (default ''default''),
    and there is no clearance option or config anywhere in cli.py. The clearance the
    CLI will pass is undefined, and the choice is security-relevant: defaulting to
    INTERNAL silently hides RESTRICTED relationships from local operators; defaulting
    to max clearance makes the CLI a scoping bypass. The doc treats a decision that
    must be made as if it already exists.'
  status: accepted
  disposition_reason: null
- issue_id: I-003
  category: adr-contradiction
  severity: medium
  description: The §7 parity claim — 'The invariant that made the chunk legs safe
    now holds for the graph channel too — no exceptions' — ignores ADR-0006's supersession
    containment. The chunk legs enforce `EXISTS (… documents d WHERE d.status='active')`
    so superseded documents 'vanish from retrieval' (ADR-0006's deterministic containment
    backstop), but `supersede()` cascades only chunks; entities/edges extracted from
    a superseded document stay `status='active'` and will still be served by the newly
    scoped graph channel. The graph channel thus continues to bypass ADR-0006's containment
    invariant even after this fix, so the 'no exceptions' parity claim is false as
    stated.
  status: accepted
  disposition_reason: null
- issue_id: I-004
  category: unverifiable-claim
  severity: medium
  description: '§6 asserts ''Existing graph tests still pass with the scope threaded
    through'', but tests/test_e2e.py:196 calls the DB function directly with the old
    signature (`SELECT * FROM f_graph_neighbors($1, 1)`), which migration 004 drops
    — that test fails with ''function does not exist'' unless rewritten, which the
    doc does not plan for. Relatedly, the doc is silent on updating init.sql (the
    canonical DDL, where the unfiltered 2-arg function lives at init.sql:316-338):
    any environment bootstrapped from init.sql without migration 004 retains the leaking
    overload as its only definition.'
  status: accepted
  disposition_reason: null
- issue_id: I-005
  category: risky-assumption
  severity: medium
  description: '§4.2 claims required params make a missing-scope call ''a compile/call
    error, not a silent leak'', but the caller/method enumeration is incomplete: `get_subgraph`
    (graph.py:179-181) delegates to `get_neighbors` and is part of the Protocol, yet
    is never mentioned; and in Python a changed signature only errors when the path
    actually executes — the CLI path has no listed test coverage, so its breakage
    (or mis-threading) surfaces at runtime, not at review time. ''Compile error''
    also silently assumes mypy runs and gates CI, which the doc does not establish.'
  status: accepted
  disposition_reason: null
- issue_id: I-006
  category: missing-invariant
  severity: low
  description: 'Filtering both endpoints inside the recursive CTE member changes traversal
    semantics, not just result filtering: an in-scope entity reachable only through
    an out-of-scope or quarantined intermediate (a1—a_quar—a3, a3 in tenant A and
    in clearance) becomes unreachable at hops=2. This is probably the desired behavior
    (transit through a hidden node leaks path information), but the doc never states
    the decision, and §6''s test seeds contain no transit-chain case to pin it — a
    later ''fix'' could reintroduce transit through hidden nodes without failing any
    test.'
  status: accepted
  disposition_reason: null
- issue_id: I-007
  category: untestable-requirement
  severity: low
  description: The §6 regression guard ('a unit test pins that the SQL string … contains
    the tenant and classification predicates') covers only two of the four predicates.
    `is_quarantined = false` and `status = 'active'` — including the quarantine rule
    CLAUDE.md marks absolute ('quarantined 리소스를 검색 결과에 포함 금지') — are not pinned, so
    a future edit could drop exactly the quarantine predicate without failing the
    guard the doc designs for this purpose.
  status: accepted
  disposition_reason: null
- issue_id: I-008
  category: adr-contradiction
  severity: low
  description: '§4.1''s bare `DROP FUNCTION f_graph_neighbors(TEXT, INT)` is non-idempotent
    DDL: re-applying the migration (or applying it to a DB where the old overload
    is already gone) fails on the DROP. ADR-0006 established idempotent DDL as the
    migration convention (`001_supersession.sql`, ''idempotent DDL''); this migration
    should use `DROP FUNCTION IF EXISTS` to match.'
  status: accepted
  disposition_reason: null
- issue_id: I-009
  category: undefined
  severity: low
  description: 'The doc contradicts itself on where `find_path` is fixed: §2 and §4.2
    correctly identify it as an inline CTE in Python (repositories/graph.py:264),
    but §4.1 says ''Any sibling path function (find_path) is updated the same way
    in the same migration'' — there is no `find_path` SQL function to migrate. Harmless
    if implementers notice, but as written the migration section specifies work that
    cannot exist, and the actual fix location for find_path is stated ambiguously
    across two sections.'
  status: accepted
  disposition_reason: null
approved_by: LivingLikeKrillin
approved_at: '2026-07-11T18:00:51Z'
---

