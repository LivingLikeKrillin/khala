---
target: SPEC-nexus-document-lifecycle
critiqued_hash: sha256:330734c909db972e8db3f3792d2bee4072da63af7084a4bc1d9845eff04e04e9
critiqued_at: '2026-07-09T21:22:34Z'
issues:
- issue_id: I-001
  category: adr-contradiction
  severity: high
  description: The unsupersede SQL clears superseded_by ('superseded_by=''') and restores
    chunks, but ADR-0006 records supersession/re-ingest history in the append-only
    doc_reingest_events log. The design never writes an event to that log when reversing
    a supersession, breaking the ADR's measurement spine (v_entropy_signals signal
    ①/④ would show a supersession that no longer exists with no reversal record).
    Only a structlog event is emitted, which is not the ADR's audited residual-measurement
    mechanism.
  status: accepted
  disposition_reason: null
- issue_id: I-002
  category: missing-invariant
  severity: high
  description: 'unsupersede sets the document to status=''active'' and revives chunks
    matching the current content_hash, but there is no guard that the document that
    superseded it (superseded_by) is itself still active. If v2 superseded v1, then
    v2 was later superseded by v3, unsupersede-ing v1 re-creates coexistence of v1
    with v3 — the exact ADR-0006 #1 entropy failure mode — with no invariant preventing
    it.'
  status: accepted
  disposition_reason: null
- issue_id: I-003
  category: adr-contradiction
  severity: medium
  description: The unsupersede chunk-restore query uses 'hash = (SELECT content_hash
    FROM documents WHERE rid=$1)' without a tenant predicate, while ADR-0006 defines
    identity as rid=doc_rid(tenant:filename) and the design's own hide/restore/supersede
    queries all carry 'AND tenant=$2'. The subquery on rid alone risks cross-tenant
    chunk selection or ambiguity.
  status: rejected
  disposition_reason: Unfounded. documents.rid is the PRIMARY KEY (globally unique,
    not per-tenant) and chunks.doc_rid REFERENCES documents(rid). The sub-select 'SELECT
    content_hash FROM documents WHERE rid=$1' therefore cannot select across tenants,
    and the chunks UPDATE keyed on doc_rid cannot either. Verified against the live
    schema. The document UPDATE carries AND tenant=$2 regardless, as defence in depth.
    The shipped revive() uses the identical pattern.
- issue_id: I-004
  category: risky-assumption
  severity: medium
  description: Origin derivation assumes source_uri of shape '<tenant>:ext-notion-<page_id>.md'
    maps cleanly to a Notion URL by stripping dashes from page_id. This assumes page_id
    never contains other characters and that every non-notion URI is a 'file/upload'
    — an upload with no real file path is conflated with a git file source, contradicting
    the doc's own goal of showing 'where a document came from.'
  status: accepted
  disposition_reason: null
- issue_id: I-005
  category: unverifiable-claim
  severity: medium
  description: 'The claim ''Deriving it means a document re-ingested from a different
    source cannot end up with a stale link'' is unverifiable as stated: source_uri
    is derived at ingest and the design provides no mechanism guaranteeing source_uri
    is rewritten on re-ingest from a different source; it asserts a property of code
    not shown.'
  status: accepted
  disposition_reason: null
- issue_id: I-006
  category: undefined
  severity: medium
  description: The query 'status' parameter enumerates active|hidden|superseded|all,
    but the response reports a 'pruned' status (soft_deleted, hold=false) that is
    not an accepted input value. It is undefined how a user filters to see pruned
    rows — 'hidden' maps to hold=true only, and 'all' is not specified to include
    pruned, so pruned rows may be unreachable via the filter.
  status: accepted
  disposition_reason: null
- issue_id: I-007
  category: missing-invariant
  severity: medium
  description: hide performs soft_delete + hold=true on a document, but there is no
    stated guard against hiding a 'superseded' document. restore explicitly refuses
    superseded rows (409), yet hide has no symmetric guard; hiding a superseded row
    would set hold=true on a non-active row, creating an ambiguous state (superseded
    + hold) with undefined restore/unsupersede behavior.
  status: accepted
  disposition_reason: null
- issue_id: I-008
  category: adr-contradiction
  severity: low
  description: The design retroactively adds a manage_documents capability gate to
    the existing POST /supersede endpoint, stating it 'was open to any principal.'
    ADR-0006 specifies supersede as exposed via CLI/API/MCP with fixed decision rules
    but no capability gate; adding auth is arguably a reasonable fix but is an unremarked
    change to the ADR-defined primitive's contract.
  status: accepted
  disposition_reason: null
- issue_id: I-009
  category: untestable-requirement
  severity: low
  description: Acceptance criterion 6 requires unsupersede to 'emit document.unsuperseded
    with the reason,' but the testing section only lists rejecting empty reason before
    write; there is no test asserting the structlog event is actually emitted with
    the discarded superseded_by, making the recorded-not-silent guarantee untested.
  status: accepted
  disposition_reason: null
- issue_id: I-010
  category: scope-creep
  severity: low
  description: The design introduces a new user-facing 'pruned' status distinction
    ('removed from Notion' vs 'you hid this') requiring UI copy and cause-tracking,
    which goes beyond the stated goal of reversible destructive acts and reconciliation
    compatibility, adding presentation logic not needed for the core invariant.
  status: rejected
  disposition_reason: Not scope creep — the distinction is load-bearing. A pruned
    document (hold=false) comes back on its own when its Notion page returns; a held
    document (hold=true) never does. Telling a user the same sentence for both would
    be false, and the restore affordance differs. The cause is already in the data
    (hold); surfacing it costs one filter value and one label.
- issue_id: I-011
  category: risky-assumption
  severity: low
  description: The 'q' search is specified as title substring, case-insensitive, but
    the acceptance criterion says 'search the corpus by title' while §1 goal says
    'search it' (the corpus). Assuming title-substring search satisfies the goal of
    managing/searching a corpus is a scope assumption that may not meet user expectation
    of content search.
  status: accepted
  disposition_reason: null
approved_by: LivingLikeKrillin
approved_at: '2026-07-10T03:26:47Z'
---

