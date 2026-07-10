---
target: SPEC-nexus-notion-reconciliation
critiqued_hash: sha256:bf2ae9aad90cb33fa8675059b13f48dbb843453bf2a91c04171c5db3235674f4
critiqued_at: '2026-07-09T14:25:13Z'
issues:
- issue_id: I-001
  category: risky-assumption
  severity: high
  description: Section 3.1 claims writing prov_inputs unconditionally will 'backfill
    the rows ingested before this SPEC on the first full run — no schema migration,
    no backfill script.' This assumes every pre-existing row is re-walked and re-touched
    on that first run. Section 4 contradicts this by stating pre-SPEC docs have empty
    prov_inputs and are 'never a prune candidate until one full run re-attributes
    it' — but a page that has since been deleted/unshared in Notion will never be
    walked again, so it can never acquire prov_inputs and is permanently un-prunable.
    The backfill claim only holds for still-live pages.
  status: accepted
  disposition_reason: null
- issue_id: I-002
  category: missing-invariant
  severity: high
  description: The revive chunk query (3.4) matches chunks by hash = documents.content_hash
    across all statuses <> 'active'. If a stale superseded generation ever shared
    the same content_hash as the current generation (e.g., content reverted to a prior
    value), revive would resurrect stale-generation chunks. No invariant guarantees
    content_hash uniqueness per generation, undermining the stated goal that revive
    activates 'only its current chunk generation.'
  status: accepted
  disposition_reason: null
- issue_id: I-003
  category: missing-invariant
  severity: high
  description: The prune/revive operations across documents and chunks are shown as
    separate UPDATE statements with no stated transaction boundary. Without an explicit
    atomicity invariant, a failure between the document UPDATE and the chunks UPDATE
    leaves a document soft_deleted with active chunks (or vice versa), a state the
    search filters and guards were not designed to handle.
  status: accepted
  disposition_reason: null
- issue_id: I-004
  category: risky-assumption
  severity: medium
  description: 'Section 3.3 relies on ordering: reconciliation runs after ingest so
    soft_deleted docs are re-ingested and their chunks rewritten before status flips.
    This assumes the ingest pass always re-touches a still-live but previously soft_deleted
    document. If dedup or hash-unchanged logic causes the ingest pass to skip re-writing
    chunks for an unchanged soft_deleted doc, the revive path may find no current-generation
    chunks in the expected state.'
  status: accepted
  disposition_reason: null
- issue_id: I-005
  category: risky-assumption
  severity: medium
  description: The 50% prune-ratio guard (3.5) is a heuristic that assumes a legitimate
    deletion event never exceeds half the active scope. A large but legitimate reorganization/deletion
    would be refused, while a mis-typed --roots affecting <50% of scope would still
    prune silently. The threshold is asserted as 'the last line of defence' without
    justification for the specific 50% figure.
  status: accepted
  disposition_reason: null
- issue_id: I-006
  category: risky-assumption
  severity: medium
  description: Section 3.5 states per-page fetch failures don't affect pruning because
    a failed-fetch page is 'still enumerated, hence still live.' This assumes live_ids()
    enumeration is fully decoupled from per-page fetch success. If enumeration itself
    depends on fetching parent/child pages, a fetch failure could silently drop a
    page from live_ids without raising, causing an erroneous prune — the exact scenario
    the design claims to prevent.
  status: accepted
  disposition_reason: null
- issue_id: I-007
  category: unverifiable-claim
  severity: medium
  description: Section 3.4 asserts 'pipeline.py writes chunks.hash and documents.content_hash
    from the same value,' which the entire generation-safe revive logic depends on.
    This cross-file behavioral claim is stated without a cited line reference or a
    test, unlike other claims in Section 2 which carry file:line citations.
  status: accepted
  disposition_reason: null
- issue_id: I-008
  category: untestable-requirement
  severity: medium
  description: Acceptance criterion 4 ('A revived doc returns to search with only
    its current chunk generation active') is not testable without a defined scenario
    producing multiple chunk generations for the same doc_rid where a stale generation
    exists at revive time. No acceptance step establishes that fixture, so the criterion
    cannot be exercised as written.
  status: accepted
  disposition_reason: null
- issue_id: I-009
  category: undefined
  severity: medium
  description: The prune predicate uses source_uri LIKE '<tenant>:ext-notion-%' and
    walked_roots as $3, but the format/derivation of walked_roots values and how they
    correspond to the entries build_csf() writes into prov_inputs (source_roots) is
    never defined. The soundness of the <@ containment operator depends entirely on
    both sides using identical root identifiers, which is unspecified.
  status: accepted
  disposition_reason: null
- issue_id: I-010
  category: missing-invariant
  severity: medium
  description: The containment predicate treats prov_inputs as the complete set of
    roots that ever reached a page, but attribution is per-run (Section 4). A page
    reachable from roots A and B, walked only under A in run 1, would have prov_inputs={A};
    if it is then absent in a run walking only A, it satisfies prov_inputs <@ {A}
    and gets pruned even though it is still alive under B. There is no invariant that
    prov_inputs accumulates across runs to reflect all reaching roots.
  status: accepted
  disposition_reason: null
- issue_id: I-011
  category: scope-creep
  severity: low
  description: The design introduces a --force flag, a --dry-run mode, and a 50% ratio
    guard with reporting. Relative to the stated Goal (bidirectional convergence via
    soft_delete/revive), the ratio-guard-plus-force control surface is additional
    operational tooling not clearly required by the goal, expanding the deliverable
    beyond the minimal reconciliation writer identified as the only missing piece
    in Section 2.
  status: rejected
  disposition_reason: --dry-run, --force and the ratio guard are not scope creep on
    a path that silently deletes data. A reconciliation writer without a dry-run is
    not shippable; the guard exists because --roots is a per-invocation argument with
    no persistent config, which is the single most likely operator error. The Goal
    (bidirectional convergence) is unreachable in practice without them.
- issue_id: I-012
  category: adr-contradiction
  severity: low
  description: 'ADR-0002 states its decision ''ships zero new product code'' and ''Does
    not change: no product code, schema, endpoint, or skill,'' and that new capabilities
    are gated on a pulled demand signal. This design doc introduces new product code
    (a reconciliation/soft_delete writer path in nexus). While arguably a bug fix
    rather than a new debt-servicing feature, the design is not tied to any recorded
    demand-pull signal per the ADR''s demand-pull discipline, and its relationship
    to the ADR''s no-new-code posture is unaddressed.'
  status: accepted
  disposition_reason: null
- issue_id: I-013
  category: unverifiable-claim
  severity: low
  description: Section 3.1 claims the sink 'Today skips the label/doc_type writes
    when nothing was re-indexed; an unchanged page would therefore never acquire provenance.'
    This description of current sink behavior is asserted without a file:line citation
    and is load-bearing for the no-migration backfill argument.
  status: accepted
  disposition_reason: null
approved_by: LivingLikeKrillin
approved_at: '2026-07-09T14:37:12Z'
---

