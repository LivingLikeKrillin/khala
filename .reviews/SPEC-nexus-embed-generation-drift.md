---
target: SPEC-nexus-embed-generation-drift
critiqued_hash: sha256:38ea75b4a2c1e7532a683aea7bbbee740a4f61a84e8f3cd3b2c578b4433b782a
critiqued_at: '2026-07-14T07:15:28Z'
issues:
- issue_id: I-001
  category: undefined
  severity: high
  description: The core term "generation" is never defined. The whole SPEC operationalizes
    it as "a distinct embed_model string" (mixed = distinct > 1), but a generation
    (embedding model family/version producing incompatible vector spaces) is not the
    same as a raw model-name string. Two name variants of the same model (e.g. version
    suffix, casing, provider prefix) would falsely register as mixed, and conversely
    two genuinely incompatible models sharing a name would not. Acceptance and the
    mixed flag rest on this undefined mapping.
  status: accepted
  disposition_reason: null
- issue_id: I-002
  category: unverifiable-claim
  severity: medium
  description: '"The research names partial re-embedding as the #1 cause of silent
    retrieval drift" cites an unnamed source with no reference, so the premise that
    justifies building this guardrail (and its priority ranking) cannot be verified.'
  status: accepted
  disposition_reason: null
- issue_id: I-003
  category: risky-assumption
  severity: medium
  description: mixed is set by ANY second embed_model with no threshold. A single
    stray/legacy/backfilled chunk carrying a different model string would flag mixed=True
    indefinitely, producing a persistent warning (alarm fatigue) even when the index
    is effectively homogeneous. The doc delegates judgment to the operator but assumes
    the distribution will be interpretable rather than dominated by long-tail noise.
  status: accepted
  disposition_reason: null
- issue_id: I-004
  category: risky-assumption
  severity: medium
  description: fetch_embed_generations runs a GROUP BY COUNT(*) over all active, non-quarantined,
    embedded chunks on every /status and CLI status call, inside the db_connected
    block. On a large corpus this is a full aggregate scan on a frequently-polled,
    read-only health endpoint; no caching, sampling, or cost bound is specified.
  status: accepted
  disposition_reason: null
- issue_id: I-005
  category: missing-invariant
  severity: medium
  description: The WHERE clause (status='active' AND is_quarantined=false AND embedding
    IS NOT NULL) is asserted to select exactly "only vectors actually in the index,"
    but there is no invariant tying this predicate to the IVFFlat partial-index predicate.
    If the index definition has any additional/different condition, the report silently
    diverges from the true index contents and the guardrail misreports.
  status: accepted
  disposition_reason: null
- issue_id: I-006
  category: undefined
  severity: medium
  description: Tie behavior is unspecified. generations is "sorted by count desc"
    and dominant is "the highest-count model" with no secondary sort key, so when
    two models have equal counts both the ordering and the choice of dominant are
    non-deterministic — yet a test asserts "generations sorted desc" and "dominant
    = larger."
  status: accepted
  disposition_reason: null
- issue_id: I-007
  category: undefined
  severity: low
  description: The output field total is listed in the schema but never defined (sum
    of counts? count of generations? total corpus?). Section 5 asserts "the right
    total" without stating what total means.
  status: accepted
  disposition_reason: null
- issue_id: I-008
  category: untestable-requirement
  severity: medium
  description: Acceptance requires that GET /status and CLI status report the distribution
    and that CLI prints a visible warning line when mixed, but Section 5 only tests
    the pure function and fetch_embed_generations. No test exercises the /status payload
    field or the CLI warning-line output, so the surfacing half of the acceptance
    criterion is not verified by any described test.
  status: accepted
  disposition_reason: null
- issue_id: I-009
  category: risky-assumption
  severity: low
  description: Section 2 states the column default is 'multilingual-e5-base' while
    embed.py actually writes 'nomic-embed-text', and the vector column is dimension-locked
    to 768d. This assumes every embedded chunk had embed_model correctly overwritten
    from the default; any historical/edge chunk that got an embedding but retained
    the column default would appear as a spurious second generation, undermining the
    mixed signal.
  status: accepted
  disposition_reason: null
approved_by: LivingLikeKrillin
approved_at: '2026-07-14T07:17:33Z'
---

