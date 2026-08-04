---
target: SPEC-nexus-kure-embedding-swap
critiqued_hash: sha256:bdb947fdcdd9bb8c62c97d2578396ad7e4faa6a439eee6d704f641b49eef1579
critiqued_at: '2026-08-04T05:48:46Z'
issues:
- issue_id: I-001
  category: risky-assumption
  severity: high
  description: §4.2 creates `idx_chunk_vector_1024` at migration time, before §4.4's
    re-embed populates `embedding_1024`. An ivfflat index trains its centroid lists
    at build time; built over a column that is entirely NULL (and whose partial predicate
    `embedding_1024 IS NOT NULL` matches zero rows), it will have no usable centroids
    and ANN recall will be arbitrarily bad regardless of the model. The `lists` value
    is computed from the row count while the vectors that must be clustered do not
    exist yet. The SPEC never sequences an index (re)build *after* the re-embed completes,
    so §4.6's ANN measurement would be measuring a degenerate index and could produce
    a false negative that §7 then interprets as 'a negative ANN result is information
    about the index'.
  status: accepted
  disposition_reason: null
- issue_id: I-002
  category: missing-invariant
  severity: high
  description: 'The blue-green window has no dual-write rule. §3 records that `ingest/pipeline.py`
    nulls `embedding` on text change and back-fills `WHERE embedding IS NULL`; §4.4
    only defines a batch walk over chunks with NULL `embedding_1024`. Nothing states
    that during the window (and after cutover) ingest must populate BOTH columns.
    Concretely: a document ingested after cutover gets only `embedding_1024`; flipping
    `search.embedding_column` back to `embedding` then leaves those chunks invisible
    to the vector leg. Rollback is therefore not ''one setting'' and not lossless,
    contradicting §4.5, §7 and the §6 rollback test.'
  status: accepted
  disposition_reason: null
- issue_id: I-003
  category: adr-contradiction
  severity: high
  description: 'ADR-0008 §6 states the Korean measurement gap ''blocks three separate
    decisions: mecab-ko retention, an embedding-model change, and resume condition
    (b)'', and §2.6 says ''an embedding-model change is equally unevaluable'' until
    an instrument exists on Khala''s real corpus. §1.1 concedes (b) ''is still unmet
    — Pack A is a public stand-in'', and §4.6 repeats that the live corpus is only
    covered ''when Pack B exists''. The SPEC discharges ADR-0008 §5''s backstop (a
    re-read obligation) but never addresses §6''s blocking statement, and proceeds
    with the very decision the ADR says is blocked. Either §6 needs amendment or the
    block must be shown discharged; the SPEC does neither.'
  status: accepted
  disposition_reason: null
- issue_id: I-004
  category: untestable-requirement
  severity: high
  description: The cutover decision rule is circular and has no threshold. §4.5 condition
    4 requires only that the ANN measurement 'has been run and recorded' — a recorded
    bad result satisfies it. §4.6 says 'the cutover condition is written against the
    self-delta, not against the cross-arm p-value', but the stated go/no-go is 'if
    ANN erases the advantage, the swap does not happen' — 'the advantage' is inherently
    a cross-arm quantity, which the same section declares non-confirmatory. The inherited
    verdict rule (paired sign test, ≥6 discordant pairs) is a two-arm rule and is
    not defined over a per-arm exact→ANN delta. No numeric self-delta magnitude is
    named that would block the flip, so §4.5(4) is not independently checkable as
    §6 claims.
  status: accepted
  disposition_reason: null
- issue_id: I-005
  category: untestable-requirement
  severity: high
  description: The latency rollback trigger is self-satisfying. §4.1 and §4.5 define
    the budget as 'the budget recorded at cutover', and §4.6 records p50/p95 'before
    and after… at cutover as the budget rollback is judged against'. If the budget
    is the post-swap measurement itself, the swap can never fail it by construction;
    only later drift can. No pre-committed p95 ceiling (absolute ms or ratio to the
    recorded baseline) is stated, and 'queries are interactive-safe' at 101 ms / 217
    ms is asserted with no defined threshold.
  status: accepted
  disposition_reason: null
- issue_id: I-006
  category: unverifiable-claim
  severity: medium
  description: '§3''s discharge of ADR-0008 §7 rests on a text search: ''Archon and
    Arbiter contain no reference to `embedding` or the vector search path''. Absence
    of the literal string does not establish the components are unimplicated. ADR-0008
    §7 records that Arbiter *writes into* Nexus (publish path, `approved_hash` provenance,
    `ingest_external_spec`), so the documents Arbiter publishes are embedded and re-embedded
    by this change even though Arbiter''s own source never names `embedding`; and
    §7 specifically calls out ''where [Archon''s] user-visible grounding signal would
    render''. The recorded check does not support the conclusion drawn from it.'
  status: accepted
  disposition_reason: null
- issue_id: I-007
  category: undefined
  severity: medium
  description: §4.3's precedence rules are mutually inconsistent. It states 'an explicit
    config key **overrides** [the per-model default]', then states that an explicit
    prefix set against a model whose card documents none 'fails at startup'. For KURE-v1
    (default empty) every non-empty explicit value is simultaneously a legal override
    and a startup failure. The rule that distinguishes a legitimate override from
    the forbidden combination is never given — 'nomic's strings configured for KURE'
    is an example, not a predicate — yet §6 asserts tests 'cover all four cases' without
    enumerating them.
  status: accepted
  disposition_reason: null
- issue_id: I-008
  category: missing-invariant
  severity: medium
  description: §4.5 condition 3 requires '`embed_health` shows a single generation
    for the new column', but `index/embed_health.py` queries against the old index's
    partial predicate (its docstring states 'WHERE 는 idx_chunk_vector 부분술어와 동일' and
    it selects over `embedding`). The SPEC repeatedly asserts embed_health 'already
    reports' what is needed (§3, §4.4, §4.5) without specifying that it must be taught
    the new column, the new partial predicate, or the `waived` metric §4.5(1) says
    it 'reports thereafter'. As written, condition 3 would report on the column being
    replaced.
  status: accepted
  disposition_reason: null
- issue_id: I-009
  category: undefined
  severity: medium
  description: The waiver mechanism of §4.5(1) is specified only as prose. Where a
    waiver is stored, its schema (chunk id, reason, waiver identity), how the identity
    is authenticated, whether it survives a re-run of the resumable CLI, and how `embed_health`
    reads it are all unstated — yet a waiver is a human override that permanently
    exempts corpus content from the vector index. §6 tests the cutover checker's four
    conditions but never tests the waiver path.
  status: accepted
  disposition_reason: null
- issue_id: I-010
  category: adr-contradiction
  severity: medium
  description: '§4.2 says ''The measurement therefore rebuilds the old column''s index
    at the same computed `lists`'', while §7 requires that ''`embedding` and its index
    are untouched and still queryable'' and §6 tests that the migration adds the new
    index ''without touching `embedding`'' and that rollback ''returns the old ranking
    **exactly**''. These cannot all hold: re-sizing `lists` on the old index changes
    its ANN results by the SPEC''s own argument (''Re-sizing `lists` changes ANN recall
    by itself''). The SPEC never states whether the rebuild happens only in the disposable
    measurement environment or in production, and ivfflat indexes are table-wide,
    not tenant-scoped.'
  status: accepted
  disposition_reason: null
- issue_id: I-011
  category: unverifiable-claim
  severity: medium
  description: The latency table compares 'nomic-embed-text via Ollama (today)' against
    'KURE-v1 via sentence-transformers, CPU' — i.e. an over-HTTP production path against
    what reads as an in-process library call. §4.1's whole design is a sidecar, so
    the +34 ms median / +144 ms worst figures omit the HTTP round-trip, serialization,
    and container-boundary cost of the path actually being shipped. The 8.8 s model
    load is also not accounted for in any cold-start or health-check behaviour, while
    §5 assumes an unreachable service degrades cleanly rather than hanging.
  status: accepted
  disposition_reason: null
- issue_id: I-012
  category: unverifiable-claim
  severity: medium
  description: §1 claims the recall figures 'behave as **lower bounds** because 821
    pooled documents are unjudged; the bound direction is conservative against the
    winner'. §4.6 asserts the opposite property for the same unjudged pool — 'the
    penalty is not symmetric between arms' — and uses that asymmetry to demote the
    cross-arm ANN comparison to non-confirmatory. If unjudged-pool penalty is asymmetric
    under a retrieval-path change, no argument is given for why it is uniformly conservative-against-the-winner
    under exact scan. The claim is asserted, not derived or measured.
  status: accepted
  disposition_reason: null
- issue_id: I-013
  category: adr-contradiction
  severity: medium
  description: 'ADR-0008 §3(3) authorises nothing and names exactly two items as unblocked
    to be proposed: ''Multi-turn retrieval and a Korean evaluation set''. An embedding-model
    swap is not among them, and ADR-0008 §5''s backstop is a *re-read* obligation
    triggered by such work, not an authorisation for it. §1.1''s gate record documents
    a director choice of ordering (''choosing the swap over Pack B labelling and multi-turn'')
    but does not record the ADR-0002 demand-pull gate being declared fired for this
    direction, which ADR-0008 §3(3) states is the required procedure (''declared fired
    by the director and recorded in that direction''s first SPEC'').'
  status: accepted
  disposition_reason: null
- issue_id: I-014
  category: scope-creep
  severity: low
  description: The §2 non-goal 'One variable' is not held. Beyond the model, this
    SPEC lands a new production service (torch, ~2–3 GB), a new column and index,
    a re-sizing of the *existing* production index's `lists` (which the SPEC itself
    says changes ANN recall independently), a per-model prefix registry with new startup-failure
    modes, a new `nexus reembed` CLI with a waiver system, and a new `search.embedding_column`
    config seam. §4.2 names the second and third variables and argues they cannot
    confound §4.6, which addresses measurement validity but not delivery risk or the
    non-goal itself.
  status: accepted
  disposition_reason: null
- issue_id: I-015
  category: undefined
  severity: low
  description: '`lists` sizing is specified as ''rows / 1000 up to a million rows''
    with no value for the >1M case and no defined ''small-corpus floor'' — yet §6
    requires a unit test for ''`lists` sizing from row count, **including the small-corpus
    floor**''. The test''s expected value is unspecifiable from the design. It is
    also unstated which row count feeds the computation (all chunks, or only those
    matching the index''s partial predicate), which differ materially during the migration
    window.'
  status: accepted
  disposition_reason: null
approved_by: LivingLikeKrillin
approved_at: '2026-08-04T05:49:54Z'
---

