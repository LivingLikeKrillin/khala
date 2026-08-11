---
target: SPEC-nexus-answer-quality-ruler
critiqued_hash: sha256:f4e2168be405dc28adc7a1064e1ec9e2dfc03e30c3551d264aa2185743356ab1
critiqued_at: '2026-08-11T17:07:12Z'
issues:
- issue_id: I-001
  category: undefined
  severity: high
  description: '§3.2 and §5 contradict each other on the artifact a human adjudicates
    from. §3.2 says the ruler ''names the cited documents in the report'' and then
    refuses to print a final grade (exit 1); §5''s run-level test requires the run
    to exit non-zero *and write no report* when the unadjudicated bucket is non-empty.
    If no report is written, the human has no list of cited documents to read, and
    §6 acceptance #1 (''pb-part-02 resolves through adjudication'') and #3 (''three
    answer runs recorded in packb-answer-runs.jsonl'') can never be reached from a
    run that has an open bucket. Define precisely what is emitted on the gated path
    (findings/citations yes, aggregate grade no).'
  status: accepted
  disposition_reason: null
- issue_id: I-002
  category: undefined
  severity: high
  description: '§3.1 defines `abstained` = `refuses` AND the required facts were not
    delivered outside the refusal, i.e. `refuses ∧ ¬has_facts`. `answerable: false`
    control labels have no required facts, so `has_facts` is vacuous — under the stated
    rule it is either trivially true (making all 5 controls score NOT abstained) or
    trivially false, and the SPEC never says which. This directly falsifies the measured
    claim in §3.1 that ''all 5 controls stay abstained'', and it conflicts with §3.4,
    which scores the control arm on `refuses` instead. The semantics of `has_facts`
    when `must_contain` is empty must be pinned, and the two sections reconciled.'
  status: accepted
  disposition_reason: null
- issue_id: I-003
  category: missing-invariant
  severity: high
  description: 'The 5 `answerable: false` controls are the positive control for the
    whole abstention rule, yet nothing binds their unanswerability to any corpus text.
    §3.3 binds *gold bodies only*, and controls have no gold — so the exact failure
    of §1.3 (a label signed against text that no longer exists) is left uncovered
    on the control arm. Under [[ADR-0010]] extraction, 44 screenshots entered the
    corpus on 2026-08-10 and can make a formerly unanswerable query answerable; §3.4
    then reports a correct, grounded answer as the ''insufficient/incorrect (hallucination)
    cell with a known-empty corpus behind it''. The claim ''known-empty corpus'' is
    asserted, never checked, and the SPEC provides no mechanism to re-verify it.'
  status: accepted
  disposition_reason: null
- issue_id: I-004
  category: missing-invariant
  severity: high
  description: '§3.2''s escape hatch is scoped to the pack: ''a citation whose title
    matches no pack key cannot be adjudicated and stays incorrect — it is indistinguishable
    from a fabricated source.'' But §1.3 establishes that the signed pack (116 documents)
    and the live tenant the run measures are different corpora, and that the live
    corpus grows (extraction, ingest-notion mirror). A correct answer citing a real
    live document that is simply not in the 116-doc pack is therefore scored `incorrect`
    and can never be adjudicated — precisely the §1.2 defect this SPEC exists to fix,
    reintroduced for out-of-pack documents. The SPEC needs a distinct outcome for
    ''cited document exists in the tenant but is outside the judged pack'' versus
    ''cited title resolves to nothing''.'
  status: accepted
  disposition_reason: null
- issue_id: I-005
  category: unverifiable-claim
  severity: high
  description: '§5 claims ''aggregate() reports unadjudicated separately and all_three
    keeps its old meaning, so runs before and after this SPEC remain comparable.''
    `all_three` includes `cites_gold`; §3.2 widens `gold` by adjudication and §6 acceptance
    #2 re-signs 21 of 40 labels (changing `must_contain`, `gold`, and `rationale`).
    Post-SPEC `all_three` is computed against a different label set over a different
    corpus snapshot, so cross-SPEC comparability does not follow from keeping the
    field name. Either drop the comparability claim or state the narrow sense in which
    it holds (identical labels + identical corpus hashes).'
  status: accepted
  disposition_reason: null
- issue_id: I-006
  category: missing-invariant
  severity: medium
  description: §3.3 states 'only gold bodies are bound' and the `corpus.bodies` example
    is commented '# gold documents only', but §3.2 introduces `not_gold` as an equally
    load-bearing human judgment ('judged, and it does not answer'). A `not_gold` verdict
    signed against a document whose text later changes — e.g. machine-read text arriving
    under [[ADR-0010]], which is exactly what changed `pb-part-01` — stays in force
    forever and permanently suppresses re-adjudication of a document that may now
    answer the query. The negative half of the judgment needs the same expiry binding
    as the positive half.
  status: accepted
  disposition_reason: null
- issue_id: I-007
  category: risky-assumption
  severity: medium
  description: §3.3 combines a whole-run halt ('the run stops and names the queries')
    with 'there is no bypass flag'. One byte of drift in one gold document blocks
    measurement for all 40 queries, not just the affected ones, and §1.3 shows drift
    is routine (8 of 116 documents in two days, from ordinary ingest and repair).
    With extraction and the Notion mirror running, the instrument is unavailable at
    exactly the moments the corpus is active. Per-query expiry with the aggregate
    refusing to include expired queries would preserve the gate's teeth without making
    the ruler self-denying; if the whole-run halt is intended, the SPEC should say
    why partial measurement is unsafe.
  status: accepted
  disposition_reason: null
- issue_id: I-008
  category: unverifiable-claim
  severity: medium
  description: '§6 acceptance #4 requires ''every number this SPEC reports is reproducible
    from a committed script'', while the same clause and U7''s U4 row keep the label
    file and the answers in `tests/eval/local/` (explicitly not committed, report
    in the PR body). A script without its inputs is not reproducible by anyone but
    the author, so this acceptance criterion cannot be checked by a reviewer. Either
    commit a redacted/derived fixture sufficient to re-derive the numbers, or restate
    the criterion as ''reproducible by the author from local inputs''.'
  status: accepted
  disposition_reason: null
- issue_id: I-009
  category: untestable-requirement
  severity: medium
  description: §5's unit tests are specified over 'real texts only' — the §1.1 hedge,
    the pb-part-07 refusal, and 'each of the 5 control answers (verbatim, stored locally)'.
    If the fixtures live in the uncommitted `tests/eval/local/`, these tests cannot
    run in CI and will either skip silently or fail on a clean checkout. That is the
    failure mode this repo has already been bitten by (a skipped test is an absent
    test). The SPEC should state where each fixture text is committed and assert the
    tests execute in CI without local state.
  status: accepted
  disposition_reason: null
- issue_id: I-010
  category: adr-contradiction
  severity: medium
  description: '§2 asserts ''No LLM judge, in any role. [[ADR-0002]]''s identity invariant.''
    ADR-0002 contains no such invariant — its principle is ''grounded answers only
    / system decides, LLM narrates'', which governs how answers are produced, not
    what an evaluation instrument may use. The attribution is doing real work here
    (it is the stated reason the ruler is deterministic) and it does not survive reading
    the ADR. It is also in tension with shipped behaviour: [[ADR-0010]] §3.1 cites
    Nexus already recording a `sufficiency_judge` value ''produced by a model'' beside
    a verdict. Ground the non-goal in its own reasoning, or cite the record that actually
    states it.'
  status: accepted
  disposition_reason: null
- issue_id: I-011
  category: adr-contradiction
  severity: medium
  description: The ruler is entirely tier-blind, but the defect that motivates §1.3
    is machine-read text arriving under [[ADR-0010]]. `_body_hash` is defined as sha256
    over active chunk texts, treating `authored` and `machine_read` chunks identically,
    and the fix for `pb-part-01` is to re-sign the label so a machine-read screen-spec
    table becomes the gold evidence an answer must match. ADR-0010 §2 requires machine-read
    text never be presented as equal to authored text, and §4 requires the tier to
    travel to every surface Nexus controls. The SPEC neither records the provenance
    tier of the text a label is signed against nor lets a reviewer see that they are
    signing off on machine-read evidence — which also means §4's 'the drift gate cannot
    tell what changed the text' is a self-inflicted limitation, since the tier is
    available at the chunk.
  status: accepted
  disposition_reason: null
- issue_id: I-012
  category: undefined
  severity: medium
  description: '§3.3 records `corpus.tenant: default` in the signed block but then
    defines the check as computing hashes ''over the tenant the run measures''. Behaviour
    is unspecified when a run measures a different tenant than the one signed: every
    label would expire (a false alarm with no bypass, per the same section), or the
    mismatch is ignored (a number computed against an unsigned corpus — the §1.3 failure).
    State whether the run refuses to start on tenant mismatch.'
  status: accepted
  disposition_reason: null
- issue_id: I-013
  category: untestable-requirement
  severity: medium
  description: '§6 acceptance #3 requires ''three answer runs ... so the noise band
    is visible rather than asserted'' but names no pass criterion — no band width,
    no threshold, no rule for what a visible band must show for acceptance to be met.
    §1 also records that three consecutive runs reporting 39/40 concealed four defects,
    so run-count alone is weak evidence of stability. Either state the criterion (e.g.
    per-query `ok` flips ≤ N across the three runs) or drop it from acceptance and
    keep it as a reporting obligation.'
  status: accepted
  disposition_reason: null
- issue_id: I-014
  category: risky-assumption
  severity: medium
  description: 'Both new rules are validated only against the sample they were derived
    from: §3.1 measures ''exactly one verdict moves'' on the same 40 answers plus
    the 5 controls that motivated the change, and the unit tests pin the very phrasings
    that produced the defects. §1 records that this rule has already been rewritten
    twice (phrase list → first sentence → segment), each time fitting the last failure.
    §4 concedes the bound is ''the same measured corpus of answers'', but the SPEC
    still offers no held-out phrasings and no falsifier — so there is no evidence
    distinguishing ''the rule is right'' from ''the rule was fitted to 45 answers''.'
  status: accepted
  disposition_reason: null
- issue_id: I-015
  category: risky-assumption
  severity: low
  description: §3.2 enters `unadjudicated` only when `cites_gold` is false. An answer
    that cites one gold document *and* one document nobody has judged passes as `correct`,
    and the unjudged document is never surfaced for adjudication — so the pool of
    unjudged-but-cited documents grows silently and is never resolvable, weakening
    the §4 defence that the gate is what keeps the softened score honest.
  status: accepted
  disposition_reason: null
- issue_id: I-016
  category: risky-assumption
  severity: low
  description: §3.1 step 3 strips whole refusal segments before evaluating `must_contain`.
    §4 bounds this only for unpunctuated lines, but the same bias applies to a well-formed
    sentence that denies and delivers together ('문서에 수치는 없지만 상한은 100곡입니다') — the fact
    is inside the stripped segment, so a correct answer scores `abstained`. This is
    the mirror of the §1.1 defect and is not covered by the stated bound.
  status: accepted
  disposition_reason: null
approved_by: LivingLikeKrillin
approved_at: '2026-08-11T18:40:55Z'
---

