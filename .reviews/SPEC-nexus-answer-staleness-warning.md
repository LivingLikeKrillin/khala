---
target: SPEC-nexus-answer-staleness-warning
critiqued_hash: sha256:ac793f67f8cdd213e20bf95f29011aa865dc54600aad13d7e51a2ee1fe61a137
critiqued_at: '2026-07-14T07:35:03Z'
issues:
- issue_id: I-001
  category: risky-assumption
  severity: high
  description: The entire verdict rests on documents.updated_at, which the doc itself
    states is ingest time, not content-authored/reviewed time. A Notion re-sync refreshes
    updated_at without the text changing, so a genuinely stale document appears fresh.
    This produces systematic false negatives — the feature will under-warn precisely
    on the re-synced sources most likely to be stale, undermining the 'staleness verdict'
    the goal promises. Acknowledging the caveat does not remove the risk that the
    signal is misleading in the common case.
  status: accepted
  disposition_reason: null
- issue_id: I-002
  category: missing-invariant
  severity: high
  description: staleness() computes ttl_days = ttl.get(doc_type.upper(), ...), but
    nothing guarantees doc_type is non-null. §2 says real doc_type values are 'mostly
    generic' and the retrieval chain may not always classify, so doc_type can be None/absent
    → doc_type.upper() raises AttributeError. This directly contradicts the stated
    'never raises' property. The spec handles updated_at is None but omits the doc_type
    is None case.
  status: accepted
  disposition_reason: null
- issue_id: I-003
  category: risky-assumption
  severity: medium
  description: _load_staleness_ttl() is 'best-effort, {} on failure → everything falls
    to default/never-stale.' A malformed or unreadable config silently turns the whole
    governance feature into a no-op with no error, log, or signal to the user. A broken
    TTL config would disable staleness warnings invisibly, which is the opposite of
    a governance guarantee. No fail-loud / warn-on-load-failure invariant is specified.
  status: accepted
  disposition_reason: null
- issue_id: I-004
  category: undefined
  severity: medium
  description: The type and tz-awareness of updated_at as consumed by staleness()/annotate_staleness
    is inconsistent/unspecified. §3 says the evidence_snippets dict carries updated_at
    as an ISO string, yet staleness() takes a datetime and does (now - updated_at).days
    with now = datetime.now(timezone.utc). It is undefined whether annotate_staleness
    receives a datetime or an ISO string, and whether updated_at is guaranteed tz-aware
    — a naive datetime would raise on subtraction with tz-aware now, again contradicting
    'never raises.'
  status: accepted
  disposition_reason: null
- issue_id: I-005
  category: untestable-requirement
  severity: medium
  description: The updated_at thread through _enrich_hits (the SQL SELECT change,
    a core deliverable of Unit 1) has no test within this SPEC; §5 defers it to 'the
    retrieval integration DB the recall job builds' — infrastructure outside this
    unit's scope and not exercised by the listed pure/wiring tests. The acceptance
    criterion that snippets carry updated_at end-to-end is therefore not directly
    verifiable by this SPEC's own test plan.
  status: accepted
  disposition_reason: null
- issue_id: I-006
  category: missing-invariant
  severity: low
  description: No validation is specified for config TTL values. A negative ttl_days
    makes age_days (>=0) > ttl_days always true → every doc of that type is flagged
    stale; a non-integer value would break the comparison. The design defines behavior
    for null and absent keys but states no invariant that ttl_days, when present,
    is a non-negative integer.
  status: accepted
  disposition_reason: null
- issue_id: I-007
  category: unverifiable-claim
  severity: low
  description: §1 asserts 'The deep research found no OSS RAG warns about this at
    answer time; it is a genuine governance gap and khala's differentiation.' This
    is an unfalsifiable competitive/marketing claim embedded as design justification,
    with no citation or test — it cannot be verified and should not drive scope decisions.
  status: accepted
  disposition_reason: null
approved_by: LivingLikeKrillin
approved_at: '2026-07-14T07:36:51Z'
---

