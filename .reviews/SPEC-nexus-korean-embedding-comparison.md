---
target: SPEC-nexus-korean-embedding-comparison
critiqued_hash: sha256:06409d123554d09fe24086c8e297b36d3d0a5f30fdbc23589851abe0df4579f0
critiqued_at: '2026-08-04T03:18:11Z'
issues:
- issue_id: I-001
  category: undefined
  severity: high
  description: '§4.5 states the blind pool holds "821 candidate documents no gold
    set has judged yet", but §1 fixes the corpus at a "265-document pack". A pool
    drawn from that pack cannot contain 821 distinct unjudged documents. Either 821
    counts (query, document) pairs, or per-leg pool entries, or the pack size is wrong
    — the unit is never defined. This number is load-bearing: it sizes the deferred
    review labour ("821 records a person must actually read"), justifies preferring
    Pack B, and is printed beside every reported metric as the unjudged count in §7.
    It must be defined and reconciled with 265.'
  status: accepted
  disposition_reason: null
- issue_id: I-002
  category: risky-assumption
  severity: high
  description: §4.5's central justification — "Direction cannot move… Judging would
    widen it, not reverse it" — is asserted, not shown. Adjudicating the 821 pooled
    entries adds gold documents, which changes the Recall@10 denominator for every
    query, including queries where nomic returned documents that adjudication would
    mark relevant. The premise that the arm surfacing more novel documents absorbs
    more of the unjudged penalty establishes only that each arm's *own* score is a
    lower bound; it does not establish that the *gap* is a lower bound, because both
    arms' scores move under adjudication and by unequal, unmeasured amounts. No bound
    on the possible movement is offered, yet the entire deferral in §4.5 and the acceptance
    criterion in §7 rest on it.
  status: accepted
  disposition_reason: null
- issue_id: I-003
  category: missing-invariant
  severity: high
  description: §3 records the invariant "labels are at revision 2, pooled over mecab-ko
    and nori — any arm absent from the pool is penalised by construction", and Unit
    4 concedes the eval SPEC's §4.2 "already mandates re-pooling for a new configuration".
    §4.5 then scores two arms (nomic, KURE-v1) that are absent from the revision-2
    pool against revision-2 labels, and closes the loop by keeping labels at revision
    2. The SPEC therefore knowingly violates the construction constraint it states
    and the parent SPEC's mandate it cites. Committing the blind pool without adjudicating
    it satisfies the pooling half and drops the half that removes the penalty; nothing
    in the design says why a by-construction penalty applied to both arms is safe
    when the arms have very different novel-document rates (which §4.5 itself asserts
    they do).
  status: accepted
  disposition_reason: null
- issue_id: I-004
  category: missing-invariant
  severity: high
  description: '§4.7''s comparable subset is defined as queries whose gold documents''
    chunks are "all within nomic''s window", and §6 tests it "given a chunk-length
    map" against "the narrower arm''s window". This is exactly the character-length
    inference §4.3 disavows: the length-based estimate was wrong by a factor of twenty
    (232 predicted, 10 actual; shortest actual refusal 3,324 chars against a ≈2,042-char
    boundary). The confirmatory analysis — the only test in the change spending α
    — would therefore be defined by a predictor the SPEC declares invalid, mis-excluding
    queries nomic could in fact answer and admitting ones it could not. The subset
    must be derived from observed `status=''refused''` rows in `ko_eval_embeddings`,
    not from a length map.'
  status: accepted
  disposition_reason: null
- issue_id: I-005
  category: adr-contradiction
  severity: high
  description: ADR-0008 §6 lists "an embedding-model change" as one of three decisions
    blocked by the §2.6 measurement gap, and §5(b) defines the closing instrument
    as one that works on "Khala's real corpus". §4.6 concedes Pack A is public documentation
    and does not move (b), yet §4.7 issues a model verdict on Pack A and §2 makes
    a favourable result the precondition for a swap SPEC. The SPEC never explains
    why Pack A is insufficient evidence for the tokenizer/(b) decision but sufficient
    for the embedding-model decision, when ADR-0008 blocks both on the same gap. Either
    the asymmetry is argued explicitly, or the verdict must be scoped as not discharging
    the block.
  status: accepted
  disposition_reason: null
- issue_id: I-006
  category: adr-contradiction
  severity: medium
  description: ADR-0008's Status is "In review. Binding on acceptance." §1.1 nonetheless
    treats it as in force — performing its §5 backstop re-read, recording an outcome
    ("the deferral stands"), and citing §3 and §6 as governing authority. If the ADR
    is not yet accepted, a backstop it does not yet impose cannot be discharged; if
    it has been accepted, the SPEC should cite the acceptance rather than an ADR whose
    own text says it is not binding. As written the compliance record in §1.1 is unverifiable.
  status: accepted
  disposition_reason: null
- issue_id: I-007
  category: adr-contradiction
  severity: medium
  description: 'ADR-0008 §3 item 3 fixes the procedure: a demand-pull gate is "declared
    fired by the director and recorded in that direction''s first SPEC — it is not
    argued into existence by the SPEC", and ADR-0008 unblocks only two items to be
    proposed (multi-turn retrieval, a Korean evaluation set) — an embedding comparison
    is not among them. §1.1 records an instruction "that the embedding measurement
    follow" the eval SPEC, then argues both readings at once: continuation (gate lives
    elsewhere) or separate direction (this instruction is the declaration). A work
    instruction dated after the eval set landed is not on its face a gate declaration,
    and offering two alternative readings is the argument-into-existence the ADR forbids.
    The reading must be fixed and the declaration recorded in the form the procedure
    names.'
  status: accepted
  disposition_reason: null
- issue_id: I-008
  category: unverifiable-claim
  severity: medium
  description: §7 requires "zero silently truncated payloads — detected by tokenising,
    not inferred", but only the KURE arm tokenises before encoding (§4.3, §5, §6).
    For the nomic arm, absence of truncation is inferred entirely from the claim that
    "Ollama refuses rather than truncating", evidenced by a boundary probe and 10
    real refusals — the same inference-from-boundary the SPEC elsewhere rejects. No
    per-row check establishes that the 1,896 accepted payloads were embedded whole.
    Either the acceptance criterion is not met for one of two arms, or it must be
    reworded to state that nomic's guarantee is backend-behavioural, not measured.
  status: accepted
  disposition_reason: null
- issue_id: I-009
  category: missing-invariant
  severity: medium
  description: '§4.3 extends the same-input guard to queries (I-013): "the pre-prefix
    query text is recorded per arm and must match". No storage exists for this. `ko_eval_embeddings`
    (§4.1) is keyed on `(model, tenant, pack, chunk_rid)` and holds document rows
    only; there is no query table, no query `input_sha256`/`payload_sha256`, and §5''s
    abort conditions and §7''s acceptance both reference query-side hash equality
    with nothing defined to compare. The document-side guard is fully specified; its
    query-side twin is asserted and unimplementable as designed.'
  status: accepted
  disposition_reason: null
- issue_id: I-010
  category: untestable-requirement
  severity: medium
  description: '§6''s exploratory deliverable requires "the re-issued tokenizer report
    on revision 3", and §4.7''s multiplicity paragraph classifies "the re-issued tokenizer
    comparison" as one of the descriptive analyses. §4.6 and §7 state the opposite:
    the tokenizer report "is neither re-run nor re-issued here", labels stay at revision
    2, and it is "untouched". A reviewer cannot tell whether Unit 5 must produce a
    revision-3 tokenizer report or must not. Given §4.5 also names the artifact `pool-rev3-blind.json`
    while labels remain revision 2, the revision-3 references appear to be residue
    from the earlier re-pooling draft and should be removed or reinstated deliberately.'
  status: accepted
  disposition_reason: null
- issue_id: I-011
  category: risky-assumption
  severity: medium
  description: The analysis plan is fixed after the outcome is known. §4.5 already
    reports the run's result (0.402 vs 0.975, "p ≈ 0 on the comparable subset"), and
    the decision to defer adjudication is explicitly conditioned on that outcome ("here
    that is KURE, the winner"). §4.7 then introduces the comparable-subset restriction
    as "the only test in this change whose α is spent on a confirmatory question",
    and Unit 5 is listed as not yet landed. A confirmatory test whose subset definition
    and whose accompanying label-collection decision were chosen after seeing the
    p-value does not carry the error rate §4.7 claims for it. Either the α claim is
    dropped, or the confirmatory analysis is pre-registered and re-run.
  status: accepted
  disposition_reason: null
- issue_id: I-012
  category: missing-invariant
  severity: medium
  description: §4.1's DDL does not enforce the invariants stated in prose around it.
    `status TEXT` has no CHECK restricting it to 'embedded' | 'refused'; nothing enforces
    "`embedding` is NULL exactly when `status='refused'`" (needs a CHECK on the pair);
    `embedding vector` is dimension-unconstrained, with the dimension guard living
    only in the harness registry; and `refusal_reason` may be NULL on a refused row,
    defeating §7's requirement that every refusal carry "the backend's own message".
    The row-count guard in §5 catches missing rows but none of these malformed-row
    cases.
  status: accepted
  disposition_reason: null
- issue_id: I-013
  category: missing-invariant
  severity: medium
  description: '§4.7''s incumbency rule ("inconclusive or underpowered leaves nomic-embed-text")
    combined with §2''s non-goal ("Editing the rule or the config to resolve their
    contradiction") leaves the `nexus/CLAUDE.md` rule 9 violation §1 opens with —
    an English-only embedding model in a Korean-first system — standing and unresolvable
    by this SPEC on the most likely non-decisive outcome. §1 says "evidence decides
    which side moves", but no branch of §4.7 moves either side: a KURE win defers
    to a future swap SPEC, and anything else retains the violating configuration with
    both remedies declared out of scope. The design needs an explicit disposition
    for the inconclusive branch.'
  status: accepted
  disposition_reason: null
- issue_id: I-014
  category: risky-assumption
  severity: medium
  description: §4.2 designates the exact vector leg as the decisive one while conceding
    "a model could in principle win here and lose under ANN", and §2 forecloses "making
    production's ANN exact". The verdict that licenses a production swap is thus taken
    on an instrument the SPEC says does not predict production. Compounding this,
    a swap changes the dimension 768 → 1024, which changes ivfflat behaviour (list
    sizing, probe recall) in ways this design measures for neither arm. The risk is
    acknowledged in a sentence but not carried into §4.7's verdict rule, which should
    state that the exact-leg result is necessary but not sufficient evidence for the
    swap.
  status: accepted
  disposition_reason: null
- issue_id: I-015
  category: untestable-requirement
  severity: medium
  description: Both deferrals rest on triggers that cannot be checked mechanically.
    §4.5's is "the first time a claim needs the absolute level rather than the direction"
    — a judgment about a future document's argument, not an observable event; the
    claim that "each of those is a document that would have to cite the figure" assumes
    the future author both notices the dependence and cites the source. §4.3's coverage-defect
    trigger ("the first change to chunking, to the production embedding model, or
    to `embed_health.py`") names real commits, but nothing in the repository fires
    on them — no CI check, no CODEOWNERS entry, no test. Both are checkable only by
    someone who already remembers to look, which is the failure mode a trigger exists
    to remove.
  status: accepted
  disposition_reason: null
- issue_id: I-016
  category: scope-creep
  severity: low
  description: Unit 4 is included in this SPEC's units and its output appears in §7's
    acceptance criteria, while the unit's own authority note states "the labels, the
    floors and the tokenizer report belong to `SPEC-nexus-korean-retrieval-eval`…
    Nothing in it is decided by this SPEC." A deliverable this SPEC must satisfy to
    be accepted, but whose rules and dispositions are owned elsewhere, has no accountable
    owner at review time — a reviewer of this SPEC cannot approve or reject the pool's
    construction, and a reviewer of the parent SPEC never sees it. Either the artifact
    moves to the parent SPEC's acceptance, or this SPEC owns the decision it disclaims.
  status: accepted
  disposition_reason: null
- issue_id: I-017
  category: undefined
  severity: low
  description: Quantities the verdict depends on are never stated. The labelled-query
    count is absent, so the "≥ 6 discordant-pair" power precondition in §4.7 cannot
    be assessed and the reported Recall@10 figures (0.402, 0.975) have no N. Unit
    4 pools "over all six legs" without enumerating them. §6's isolation test lists
    three forbidden imports (`sentence_transformers`, `torch`, harness arm modules)
    then asserts "neither appears in the app image's dependency set", leaving the
    third unclear, and a name-based check does not cover transitive imports — the
    realistic way production would acquire the dependency §4.4 and §7 both promise
    it will not have.
  status: accepted
  disposition_reason: null
approved_by: LivingLikeKrillin
approved_at: '2026-08-04T03:19:49Z'
---

