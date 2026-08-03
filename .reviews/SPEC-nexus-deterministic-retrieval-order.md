---
target: SPEC-nexus-deterministic-retrieval-order
critiqued_hash: sha256:a7ecf4949f790d6644955aab44962019d28ce7cc90a14fea3b1c811d1189d9ee
critiqued_at: '2026-08-03T10:11:45Z'
issues:
- issue_id: I-001
  category: untestable-requirement
  severity: high
  description: §6's determinism test ('load the same fixture corpus into two tenants...
    assert the returned chunk order is identical') is invalidated by the design's
    own definition of the tie-break key. §4 says `rid` is derived from the document
    uri, and ADR-0006 records `canonical_uri = "{tenant}:{filename}"` — the tenant
    is part of the identity string. If `doc_rid` is a hash (as ADR-0006's `rid = doc_rid(canonical_uri)`
    implies), the two tenants' chunks get unrelated rid values and the tie order legitimately
    differs between them, so the test fails even with a correct fix; if rids happen
    to share a sortable tenant prefix, the test passes trivially. Either way it does
    not test 'same content → same order'. The acceptance criterion 'loading the same
    corpus twice ... yields identical result orders' needs a same-tenant reload (drop/re-ingest)
    to mean anything.
  status: accepted
  disposition_reason: null
- issue_id: I-002
  category: untestable-requirement
  severity: high
  description: '§6''s ''Scores unchanged'' test contradicts §1''s stated mechanism.
    §1 says tie order ''decides which chunks fall inside LIMIT 20''. If that is true,
    then for any query where a tie straddles the LIMIT boundary the returned (rid,
    score) *set* changes before vs. after the fix — which is exactly what the test
    asserts must not happen. The test can only pass on a fixture where no tie crosses
    the limit, i.e. on a fixture that cannot exhibit the defect. §4''s ''No row that
    outranks another by score changes position'' is also wrong downstream: a changed
    leg candidate set changes RRF ranks, and RRF score is a function of rank, so non-tied
    rows can move in the fused output.'
  status: accepted
  disposition_reason: null
- issue_id: I-003
  category: adr-contradiction
  severity: high
  description: '§4 asserts `rid` is ''unique, non-null, and stable across reloads
    of the same content''. ADR-0006 (''Ground truth in the current code (verified)'')
    states the identity key `tenant:filename` is ''simultaneously too coarse (different
    docs sharing a basename collide → silent overwrite) and too fine (a renamed doc
    coexists)''. Uniqueness per distinct document is therefore not guaranteed, and
    stability is a function of the *filename*, not of the content: rename a file and
    every rid under it changes, so identical content produces a different total order.
    The design''s core guarantee inherits an identity weakness that ADR-0006 explicitly
    declined to fix in Slice 1 (it only measures the collision, signal ①), and the
    doc neither cites nor bounds it.'
  status: accepted
  disposition_reason: null
- issue_id: I-004
  category: missing-invariant
  severity: high
  description: The vector leg's determinism claim ignores the index. §5 says 'no new
    failure mode' and discusses only `idx_chunk_bm25`; nothing states what index `_vector_search`
    uses. If it is an ANN index (ivfflat/hnsw), the *candidate set* returned before
    ORDER BY is approximate and can vary with probes, buffer state, and parallel workers
    — adding `, c.rid ASC` orders whatever came back but does not make the leg deterministic.
    The design must state the required invariant (exact scan, or fixed `ivfflat.probes`/`hnsw.ef_search`
    plus a deterministic plan) or the acceptance criterion 'identical result orders
    in both legs' is unreachable.
  status: accepted
  disposition_reason: null
- issue_id: I-005
  category: risky-assumption
  severity: medium
  description: '§4 calls rid ''an arbitrary tie-break, not a meaningful one: it prefers
    the same chunks, not better ones'', and §2 leans on this to claim relevance is
    unchanged. But if rid derives from uri + chunk position, it is not arbitrary —
    it is a *systematic* corpus-wide bias toward one lexicographic/hash region of
    the uri space and toward early chunk positions, applied identically to every query.
    Across a 265-document set with 13–16 distinct scores in the top 25, that bias
    can consistently favour or starve the same documents, which is a relevance change
    even though no formula changed. The doc should either measure per-document recall
    before/after or state the bias as an accepted cost.'
  status: accepted
  disposition_reason: null
- issue_id: I-006
  category: missing-invariant
  severity: medium
  description: §4 concludes 'the result is a function of the data alone', but retrieval
    also depends on mutable derived state that ties do not cover. ADR-0006 records
    that re-embedding is 'emergent (NULL-column driven)' and that `embedding`/`tsvector_ko`
    are invalidated on text change — so a query run while a backfill is in flight
    sees a different *candidate set*, not merely a different order. Determinism therefore
    requires an invariant like 'no NULL embedding/tsvector rows for active chunks
    at query time' (or explicit exclusion of them), which the design never states,
    and which the two-load test would silently violate if either load is queried before
    backfill completes.
  status: accepted
  disposition_reason: null
- issue_id: I-007
  category: missing-invariant
  severity: medium
  description: Determinism at the fusion and diversify layers is inherited rather
    than enforced. §3 notes Python's sort is stable, and §6 only *documents* that
    with a test. But RRF scores are rank-derived and tie densely (any two rows at
    equal rank in their respective legs), so the fused order among equal scores depends
    on the input list construction order in `_rrf_fusion` — which is unspecified here
    (dict insertion order, set iteration, or leg interleaving). A refactor to `heapq.nlargest`,
    a set, or a parallel merge silently restores nondeterminism with no failing test
    at the leg level. The design should require an explicit final key (e.g. `(-score,
    rid)`) at fusion and in `_diversify`, not rely on sort stability.
  status: accepted
  disposition_reason: null
- issue_id: I-008
  category: undefined
  severity: medium
  description: The 'collapse to the user's top-k' — named in §1 as the step where
    chunk order becomes user-visible outcome — is never defined, and no acceptance
    criterion covers it. Which chunk represents a document, whether documents are
    ordered by best-chunk score or by count, and how *that* step breaks ties are all
    unspecified. §7 asserts determinism only 'in both legs', so the design can be
    fully implemented and accepted while the user-visible result order remains nondeterministic
    at the collapse. The goal in §1 ('the same question gets the same answer') is
    stated at a layer the acceptance criteria do not reach.
  status: accepted
  disposition_reason: null
- issue_id: I-009
  category: untestable-requirement
  severity: medium
  description: '§7''s ''the run-to-run range collapsed to a point'' has no operational
    definition: no number of repeated loads/runs, no tolerance, no statement of what
    varies between runs (fresh ingest? same DB, repeated query? different connection/worker
    count?). A single pair of runs agreeing is weak evidence for a defect that produced
    a 0.700–0.775 spread only across some loads. Specify N reloads and require exact
    equality of the score *and* the miss list across all N, otherwise the criterion
    is satisfiable by luck.'
  status: accepted
  disposition_reason: null
- issue_id: I-010
  category: unverifiable-claim
  severity: medium
  description: §1's diagnosis — 'The cause is not the tokenizer, the scorer, or the
    corpus' — rests on 'identical tsvectors, one md5 over the whole index', with the
    md5's input (which columns, in what order, over which rows) unstated; an md5 over
    an unordered aggregate proves less than claimed. No ablation is offered showing
    the tie ordering accounts for the *whole* 0.700–0.775 range (3 of ~40 labels).
    Since the entire change is justified by this single measurement, the doc should
    record the hash definition and a control (e.g. same load queried twice vs. two
    loads) so the attribution is checkable.
  status: accepted
  disposition_reason: null
- issue_id: I-011
  category: scope-creep
  severity: medium
  description: '§6 and §7 fold a second deliverable into this change: recording the
    Korean set''s floors, un-skipping `test_ko_eval_run_db.py`, clearing `FLOORS_PENDING`,
    and enabling the mecab-vs-nori re-run. Those numbers belong to SPEC-nexus-korean-retrieval-eval
    and carry their own evidence and CI-floor obligations; binding them to acceptance
    means this fix cannot merge until an unrelated numeric result lands, and a floor
    regression from any other cause blocks or falsely validates the ordering change.
    Determinism is testable on its own (the two-load assertion) — the floor recording
    should be a follow-on unit.'
  status: accepted
  disposition_reason: null
- issue_id: I-012
  category: adr-contradiction
  severity: low
  description: §4's 'the result is a function of the data alone' and §5's 'no new
    query path' sit awkwardly with ADR-0006's mandated document-level containment
    filter (`AND EXISTS (... d.status='active')`) in `_bm25_search`/`_vector_search`.
    Retrieval output is also a function of `documents.status`/`superseded_by`, which
    an operator mutates out-of-band via `supersede()` with no corpus content change.
    The §3 'what exists' table omits this clause entirely, so it is unclear whether
    the design was written against the post-ADR-0006 query text; if not, the proposed
    SQL may be editing a stale baseline.
  status: accepted
  disposition_reason: null
approved_by: LivingLikeKrillin
approved_at: '2026-08-03T10:31:11Z'
---

