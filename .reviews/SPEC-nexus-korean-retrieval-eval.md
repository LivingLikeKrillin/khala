---
target: SPEC-nexus-korean-retrieval-eval
critiqued_hash: sha256:0d5b33ef8f59ebd47a3633126542d1785e04c52b58a8c08b3c3b6c916dfee827
critiqued_at: '2026-08-02T09:58:10Z'
issues:
- issue_id: I-001
  category: missing-invariant
  severity: high
  description: No negative control. ADR-0008 §2.6 confound 5 names `test_search_recall.py::test_and_semantics_would_break_this_suite`
    as "the check that proves the instrument has teeth" and records that the nori
    exploration failed precisely because "nothing established that it could have failed."
    §6 lists parse tests, schema bans, integrity gates and metric unit tests — but
    nothing that deliberately degrades query assembly or retrieval and asserts the
    new metrics collapse. The SPEC builds a replacement instrument while dropping
    the one property the ADR identified as making an instrument trustworthy.
  status: accepted
  disposition_reason: null
- issue_id: I-002
  category: undefined
  severity: high
  description: 'The comparison criterion is never defined. ADR-0008 §5 explicitly
    delegates it: "(b) deliberately says ''does not favour mecab-ko'' rather than
    naming a metric or margin … The set''s own SPEC is where the comparison criterion
    belongs." This SPEC produces Recall@10/MRR@10/misses per leg and per stratum (§4.3)
    and a report stating "which segmentation retrieves better" (§7), but nowhere states
    which metric is decisive, on which leg, what margin counts as better, or how per-stratum
    results that disagree with the aggregate are resolved. The one job the ADR assigned
    to this SPEC is left open, so the resulting report cannot answer (b) without a
    post-hoc rule invented after the numbers are visible.'
  status: accepted
  disposition_reason: null
- issue_id: I-003
  category: adr-contradiction
  severity: high
  description: Pack B, as designed, can never satisfy ADR-0008 §5(b). §4.1 concedes
    Pack A is a stand-in and that (b) "is fully satisfied only when Pack B is also
    labelled and run", and defines Pack B as a git-ignored label pack "over the live
    tenant" — the same tenant §3's table disqualifies because it "changes whenever
    someone syncs". §4.1 also asserts "A ruler that moves is not a ruler." No pinning,
    snapshotting, or manifest protocol is specified for Pack B, so the SPEC's own
    stated route to closing (b) is ruled out by its own corpus-stability rule.
  status: accepted
  disposition_reason: null
- issue_id: I-004
  category: adr-contradiction
  severity: high
  description: 'The demand-pull gate is never recorded. ADR-0008 §3 item 3 fixes the
    procedure: a Korean evaluation set is unblocked only to be *proposed*, "with ADR-0002''s
    demand-pull discipline applying", and "a gate is declared fired by the director
    and recorded in that direction''s first SPEC — it is not argued into existence
    by the SPEC." It further states it "takes no position on whether ADR-0006''s entropy/ingestion-trust
    override extends to a retrieval-quality instrument" and that stretching it "is
    a call for the director to make." This is that first SPEC, and it contains no
    gate record, no director declaration, and no citation of an override — §1 instead
    argues the need directly, which is the mode the ADR forbids.'
  status: accepted
  disposition_reason: null
- issue_id: I-005
  category: risky-assumption
  severity: high
  description: §4.2's pooling defence — "Since both tokenizer configurations are pooled
    together, neither is favoured over the other" — does not survive §4.6's promised
    reuse. §4.6 states the KURE-v1 embedding comparison "needs no new labels" and
    reuses the same 45 labels against the vector and fused legs. A KURE-v1 run was
    not in the pool, so documents only it retrieves are "unjudged and counted as non-relevant"
    (§4.2) — a systematic penalty against exactly the new system the reuse exists
    to evaluate. The SPEC names TREC pooling bias and then relies on the reuse case
    where the bias is unmitigated, with no re-pooling requirement for later configurations.
  status: accepted
  disposition_reason: null
- issue_id: I-006
  category: missing-invariant
  severity: high
  description: Pooled adjudication mutates `gold` after the floors are set, and nothing
    binds them together. §4.2 adds adjudicated documents to `gold` after the first
    run; Recall@10 is `|top-10 ∩ gold| / |gold|` (§4.3), so growing a gold set lowers
    recall for an unchanged retriever. §4.5 pins the CI floors to "the date and pack
    revision they were measured on" but *not* to a label revision (label revision
    is recorded only in the exploratory report). A later adjudication round therefore
    breaks CI with no code change, and "lowering them requires a reason in the same
    commit" gives no way to distinguish a genuine regression from a denominator change.
  status: accepted
  disposition_reason: null
- issue_id: I-007
  category: undefined
  severity: high
  description: '"Recall@10" is ambiguous under chunk→document collapse. §4.3 has each
    leg produce a ranked *chunk* list, then collapses to documents, then measures
    at 10. But §3 pins `bm25_top_k: 20`, `vector_top_k: 20`, `final_top_k: 10` — so
    it is unstated whether the metric is over the top-10 documents distilled from
    the 20-chunk leg output, or over the documents surviving in the 10-chunk final
    window (which can be far fewer than 10 distinct documents when one document contributes
    several chunks). The two readings give materially different numbers and different
    sensitivity to a tokenizer change, and the CI floors are asserted against whichever
    one an implementer chooses.'
  status: accepted
  disposition_reason: null
- issue_id: I-008
  category: undefined
  severity: high
  description: '"the `nori` analyzer" (§4.4) is underspecified for the property being
    measured. nori''s `decompound_mode` (none/discard/mixed), plugin/OpenSearch version,
    and any user dictionary determine how compound nouns segment — and `compound`
    and `spacing` are two of the five strata (§4.2). §4.4 pins the *engine* to remove
    the ADR-0008 §2.6 confound but leaves the analyzer''s own decisive parameters
    unpinned, so the committed report cannot be reproduced and "nori''s segmentation
    under our filter policy" names no specific configuration.'
  status: accepted
  disposition_reason: null
- issue_id: I-009
  category: missing-invariant
  severity: high
  description: Nothing enforces that index-time and query-time use the same tokenizer,
    or that the index is rebuilt when the tokenizer changes. §4.4 asserts "Index-time
    and query-time analysis use the one tokenizer" as prose, but the seam injects
    independently at two call sites (`index/bm25.py`, `search/hybrid.py`). A run that
    indexes with mecab and queries with nori (or reuses a mecab-built tsvector for
    a nori run) produces plausible-looking but meaningless numbers, and §6 lists no
    test that fails on a mismatch — only "default tokenizer is still mecab". Given
    the whole SPEC exists because a previous instrument could not detect its own invalidity,
    this is the invariant most worth asserting.
  status: accepted
  disposition_reason: null
- issue_id: I-010
  category: scope-creep
  severity: medium
  description: §2 declares "Changing anything in the production retrieval path" a
    non-goal and §7 requires "Nothing in the production retrieval path behaves differently",
    but Unit 4 introduces a `Tokenizer` protocol and injection points into `index/bm25.py:110`
    and `search/hybrid.py:63` — both production files. "Byte-identical when nothing
    is injected" is a behavioural claim, not the absence of a change; it adds a production-reachable
    indirection whose only consumer is the harness. Either the non-goal should be
    narrowed to "no change in retrieval *results*", or the seam belongs behind an
    explicit carve-out, since ADR-0008 §5's backstop names "a tokenizer … change"
    as a re-read trigger.
  status: accepted
  disposition_reason: null
- issue_id: I-011
  category: untestable-requirement
  severity: medium
  description: The CI floor acceptance criterion is unfalsifiable as written. §4.5
    says floors are "recorded when the harness first runs, not guessed here", and
    §7 accepts when "CI holds the mecab keyword-leg floors." Since the floors are
    whatever the first run produced, this criterion is satisfied by construction regardless
    of whether Pack A retrieval works well, badly, or is silently broken (e.g. a mis-built
    index yielding recall 0.2 would simply become the floor). No independent sanity
    bound — a minimum absolute recall, or agreement with the negative control — is
    specified.
  status: accepted
  disposition_reason: null
- issue_id: I-012
  category: unverifiable-claim
  severity: medium
  description: §4.2 justifies 40 answerable queries with "a tokenizer comparison shows
    its signal at this scale" — asserted with no power analysis, no expected effect
    size, and no variance estimate. §4.3/§7 then require per-*stratum* verdicts computed
    from 8 queries each, where one query flipping moves stratum recall by 12.5 points.
    Combined with the missing comparison criterion, the SPEC promises a per-stratum
    ranking that its sample size may not be able to support, and provides no way for
    a reader of the committed report to tell a real difference from noise.
  status: accepted
  disposition_reason: null
- issue_id: I-013
  category: risky-assumption
  severity: medium
  description: The structural lexeme ban (§4.2, §5, §6) bans *key names* matching
    `token|lexeme|morpheme|term|expected_word`, and §5 credits it with stopping "the
    exact defect being fixed". But the ADR-0008 §2.6 confound 4 defect was that gold
    expectations were *derived from mecab's output*; a labeller can still pick gold
    documents by running mecab retrieval and accepting what it returns, with no schema
    key implicated. The only guard against that is the process rule "queries authored
    from the document side" plus a forbidden-title-reuse convention — neither of which
    is machine-checkable, and §6 asserts neither. The guard table overstates what
    the schema ban buys.
  status: accepted
  disposition_reason: null
- issue_id: I-014
  category: missing-invariant
  severity: medium
  description: §3 leans on "`tokenize_korean()` has exactly two call sites … That
    is the entire tokenizer seam" — a point-in-time observation the ADR itself warns
    will drift ("Khala-side references … are point-in-time as of 2026-08-01 and will
    drift"). §6 asserts the default path calls mecab, but nothing fails if a third
    call site is added later that bypasses the injected tokenizer, which would silently
    make future nori/KURE runs partially mecab-tokenized. A test enumerating the call
    sites (or forbidding direct `tokenize_korean` imports outside the seam) is absent.
  status: accepted
  disposition_reason: null
- issue_id: I-015
  category: undefined
  severity: low
  description: The corpus selection rule is presented as "deterministic and re-runnable"
    but is incomplete. The `[2 KiB, 40 KiB]` size filter does not say whether it applies
    before or after Unit 1's "strip Hugo front-matter/shortcodes" transform, and the
    strip itself is unspecified (which shortcodes, what replacement text). Since the
    manifest hashes the *packed* files, two implementers following §4.1 can produce
    different 265-document packs — or a different count — and the stated 265 / ~2.75
    MiB figures cannot be used to check the build.
  status: accepted
  disposition_reason: null
- issue_id: I-016
  category: missing-invariant
  severity: low
  description: The 5 unanswerable labels have `gold == []` (§4.2, §6) while Recall@10
    divides by `|gold|` (§4.3). §4.3 never states that unanswerable queries are excluded
    from aggregate recall/MRR/miss counts, so a naive implementation divides by zero
    or scores them as universal misses. §4.2 says only that "they resolve to no gold
    document"; the aggregation rule, and whether the reported denominators are 40
    or 45, is left implicit — which also makes the CI floors ambiguous.
  status: accepted
  disposition_reason: null
approved_by: LivingLikeKrillin
approved_at: '2026-08-02T10:27:36Z'
---

