---
target: SPEC-nexus-notion-source-console
critiqued_hash: sha256:3dcc9cef594fc80ba6d7204b43a7127f5348bb3bf3f1b41a21bdb0bc45dbea7c
critiqued_at: '2026-07-09T16:26:42Z'
issues:
- issue_id: I-001
  category: adr-contradiction
  severity: high
  description: The DESIGN doc stores canonical Notion page-ids (root_id) and relies
    on connector-driven stable ids for root attribution and reconciliation. ADR-0006
    explicitly defers 'Connector-driven stable ids (Confluence/Notion page-id) — pilot
    C remains deferred' as out-of-scope Slice 2, gated on v_entropy_signals. The spec
    adopts Notion page-id identity without noting the gate.
  status: accepted
  disposition_reason: null
- issue_id: I-002
  category: adr-contradiction
  severity: medium
  description: ADR-0004/0006 establish Nexus as index-only and DELETE /roots states
    unregistering 'does not delete documents' — but the reconcile/prune flow soft-deletes/prunes
    index documents, which is index governance and consistent. However the doc never
    reconciles its prune semantics with the ADR's supersession-based containment model
    (status='active' filter, superseded_by); pruned docs vs superseded docs are two
    overlapping status pathways with no stated interaction/invariant.
  status: accepted
  disposition_reason: null
- issue_id: I-003
  category: missing-invariant
  severity: high
  description: plan_hash = sha256(sorted(prune_rids) || '|' || sorted(revive_rids))
    only covers the set of rids, not their content/titles or the roots walked. A plan
    can be considered 'unchanged' while the underlying document set that produced
    it differs (e.g., same rids but different reachable roots), so the confirm-against-hash
    guarantee is weaker than claimed.
  status: accepted
  disposition_reason: null
- issue_id: I-004
  category: risky-assumption
  severity: high
  description: The advisory-lock 'one sync per tenant' invariant is held by an asyncio
    task in the app process, but the startup sweep marks orphaned 'running' rows as
    failed. In a multi-process/multi-replica deployment (implied by Cloudflare Access
    team dogfood), pg_try_advisory_lock is per-connection and a restart of one replica
    could sweep runs still executing on another, or two replicas could each hold locks
    on different connections incorrectly. Single-process assumption is unstated.
  status: accepted
  disposition_reason: null
- issue_id: I-005
  category: risky-assumption
  severity: medium
  description: Recovery claim 'the row stays running — a startup sweep marks any running
    row as failed; recovery is to run again; ingest is idempotent' assumes reconcile/prune
    operations are also idempotent and safe to interrupt mid-apply. A crash between
    soft_delete of some documents and completion could leave a partially-applied plan;
    idempotency of ingest does not cover partial destructive reconciliation.
  status: accepted
  disposition_reason: null
- issue_id: I-006
  category: missing-invariant
  severity: medium
  description: No invariant ties confirm_plan back to the same reconcile/dry_run flags
    or roots as the preview run. The confirm request re-supplies {reconcile, force,
    since} independently; nothing prevents confirming a dry_run plan under different
    since/root parameters than were used to compute it.
  status: accepted
  disposition_reason: null
- issue_id: I-007
  category: unverifiable-claim
  severity: medium
  description: '§4.4 claims reconciliation ''already holds live_index(): page → the
    roots that reach it'' and ''will write prov_inputs for every live page'' fixes
    the --since first-run bug. This asserts a code capability and behavior change
    without a verifiable reference to the mechanism that writes prov_inputs outside
    the ingest sink; it is stated as fact but not demonstrable from the doc.'
  status: accepted
  disposition_reason: null
- issue_id: I-008
  category: untestable-requirement
  severity: medium
  description: 'Acceptance #8 (''A first --reconcile --since <t> run prunes correctly
    — no first-run rule anywhere'') asserts a global absence (''no first-run rule
    anywhere''), which cannot be verified by a bounded test; you cannot test that
    a rule exists nowhere in docs/code.'
  status: accepted
  disposition_reason: null
- issue_id: I-009
  category: untestable-requirement
  severity: low
  description: 'Acceptance #3 (''Close the browser mid-sync, reopen, see the run''s
    current state'') is timing-dependent and lacks a defined observable state contract
    for what ''current state'' must show at a given progress point, making pass/fail
    subjective.'
  status: accepted
  disposition_reason: null
- issue_id: I-010
  category: undefined
  severity: medium
  description: The 50% prune threshold and --force are referenced as a 'second line
    of defence' but the threshold's exact definition (ratio of what to what — prune
    candidates over live count? over total?) and where it is configured are never
    specified.
  status: accepted
  disposition_reason: null
- issue_id: I-011
  category: undefined
  severity: low
  description: run_id generation scheme is unspecified (UUID? monotonic?), yet it
    is used as PRIMARY KEY and passed as confirm_plan token and in 409 responses;
    collision/format guarantees are undefined.
  status: accepted
  disposition_reason: null
- issue_id: I-012
  category: undefined
  severity: low
  description: 'The ''refused'' sync_status enum value and the error/reason semantics
    are defined for prune-ratio, but the mapping between run.status=''refused'' and
    the HTTP responses (503/409) vs a 202+run_id that later becomes refused is inconsistent:
    refused-by-threshold happens inside a background run while plan_stale/sync_in_progress
    are synchronous 409s, and the doc does not reconcile these two failure surfaces.'
  status: accepted
  disposition_reason: null
- issue_id: I-013
  category: scope-creep
  severity: low
  description: §4.1 claims moving roots to DB 'retires the --roots typo hazard that
    forced the 50% prune threshold into existence' — but §4.3/§5 keep the 50% threshold
    as a defence. Introducing per-root document counts, labels, added_by auditing
    goes beyond the stated first-capability goal and edges into source-management
    admin features not required to close the ingest-notion HTTP hole.
  status: accepted
  disposition_reason: null
- issue_id: I-014
  category: risky-assumption
  severity: medium
  description: Granting the local-dev principal manage_sources (§4.6) is acknowledged
    to widen access so that 'anyone the team lets in behind Cloudflare Access can
    now manage sources.' This couples app-level authz to an external network gate,
    an unstated assumption that Cloudflare Access is always in front; a direct/local
    exposure would grant unauthenticated source management.
  status: accepted
  disposition_reason: null
- issue_id: I-015
  category: missing-invariant
  severity: low
  description: notion_sync_runs has no tenant+status index or constraint enforcing
    at most one 'running' row per tenant at the DB level; the single-run guarantee
    rests entirely on the advisory lock, so a bug bypassing the lock leaves no data-level
    backstop.
  status: accepted
  disposition_reason: null
approved_by: LivingLikeKrillin
approved_at: '2026-07-09T16:45:13Z'
---

