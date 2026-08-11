---
target: SPEC-nexus-vision-reader-of-record
critiqued_hash: sha256:ad86f57e2588135f9de434eb8dccc7b98f10bfc5e9f97efccf6c7ce534f2b8b5
critiqued_at: '2026-08-11T10:57:42Z'
issues:
- issue_id: I-001
  category: undefined
  severity: high
  description: §2.2's selection procedure contradicts its own conclusion. Deployability
    is stated as a hard eligibility condition ("a reader that cannot run in a deployed
    ingest cannot be the reader of record") but is encoded as tie-break (c), reachable
    only if (a) fewer inventions and (b) lower variation both tie. The SPEC then concedes
    "On today's numbers Opus wins (a) and (b) and loses (c)" — i.e. the pre-registered
    algorithm as written selects the reader the prose says is not a candidate. Either
    deployability is a gate that runs before the tie-breaks (like §2.2's steps 2 and
    3) or it is a tie-break; the SPEC pre-registers one and argues the other, which
    is precisely the re-argument it claims to foreclose.
  status: accepted
  disposition_reason: null
- issue_id: I-002
  category: unverifiable-claim
  severity: high
  description: §2.4 justifies keeping the existing chunks because they have "been
    answering correctly (39/40 on the answer harness)". ADR-0010 records that run
    as 40/40 and states explicitly that it "was scored against text only, using labels
    an agent authored from that same text" — "The ruler never pointed at the images."
    The harness therefore contains no measurement of the machine_read chunks at all,
    so it cannot support a claim about whether the extracted policy text is answering
    correctly. The number is also cited at a different value than the ADR it derives
    from, with no reconciliation.
  status: accepted
  disposition_reason: null
- issue_id: I-003
  category: risky-assumption
  severity: high
  description: §6 records that the tokeniser splits mixed-script identifiers and,
    "worse, it can score two readings as agreeing on `02` when they read different
    identifiers" — i.e. it inflates measured agreement — and defers the fix until
    "Before the next cross-check is used for a decision". §2.2 is a cross-check used
    for a decision (choosing the reader of record) and its gates (≤10% token variation;
    adjudicated invention counts) are computed by that same instrument. The deferral's
    own trigger condition is fired by this SPEC, so every pre-registered number is
    produced by an instrument the SPEC declares defective in the direction that matters
    (false agreement → understated variation, understated one-sided disagreement).
  status: accepted
  disposition_reason: null
- issue_id: I-004
  category: risky-assumption
  severity: high
  description: The control design is circular and cannot establish the premise it
    is said to establish. Controls are "drawn from tokens all four runs agreed on",
    and 10/10 present is read as "the premise holds — stable agreement means the token
    is in the image". Tokens sampled from the agreeing set can only confirm agreement→presence
    on inputs already selected for agreement; they cannot bound the failure mode that
    matters, which is two readers inventing the same plausible string (both are LLMs
    reading the same pixels, so failures are correlated, not independent). Such a
    shared invention is not merely undetected — it is eligible for selection as a
    control, and would be scored as passing. The invention gate consequently measures
    only one-sided disagreement, never fidelity to the image.
  status: accepted
  disposition_reason: null
- issue_id: I-005
  category: undefined
  severity: high
  description: '"Policy-value invention" — the sole disqualifying condition in §2.2''s
    invention gate — is never defined, and neither are the two exculpating classes
    ("markup-name", "dummy-placeholder"). §2.2 concedes the classes come from §1:
    "§1''s adjudication established those categories", i.e. they were drawn after
    seeing the four inventions the two current candidates actually made, and they
    exactly cover them (0 disqualifying inventions for both). That is the post-hoc
    threshold §2.2''s opening sentence rejects ("so that a threshold cannot be drawn
    around whichever candidate wins"), applied to the category boundary instead of
    the number. It is also unstated who classifies, and whether that classification
    is blinded — the blinding described covers presence adjudication, not category
    assignment, and category assignment is what decides the outcome.'
  status: accepted
  disposition_reason: null
- issue_id: I-006
  category: missing-invariant
  severity: high
  description: '§2.2 runs each candidate twice over all 44 images and §2.3 states
    "44 images are re-read under the new identity", but ADR-0010 §5 fixes two invariants
    that this collides with: "Unchanged bytes are never re-extracted" (re-ingest resolves
    the stored result by byte hash + extractor identity) and "an extraction result,
    once stored, is never replaced by a re-read of the same bytes under the same extractor
    identity." The SPEC never says whether qualification runs are out-of-band (not
    written to vision_extractions) or which of the two runs becomes the stored extraction
    of record for each image. This is not cosmetic: if the runs are stored, §5''s
    non-replacement invariant is violated by the measurement itself; if they are out-of-band,
    §2.3''s "the change is one migration" needs the prompt fix to remain undeployed
    through qualification, which §2.1 ("it must be fixed before the candidates are
    ranked") appears to contradict.'
  status: accepted
  disposition_reason: null
- issue_id: I-007
  category: missing-invariant
  severity: high
  description: The migration's feasibility depends on obtaining the 44 images' bytes
    again, and the SPEC never says where they come from. ADR-0004 fixes Nexus as index-not-store,
    ADR-0010 §3.1 records that "Notion's image URLs are time-limited signed links
    that expire within the hour" and requires a re-resolvable source reference precisely
    so that "re-read the image at its source" is not an empty promise. §2.3 claims
    to enumerate "Consequences, all of them" and omits both the byte-acquisition path
    and the state of `source_ref`. If the reference is absent or unstored, the entire
    re-extraction — and §2's recourse for every machine_read chunk — has nothing behind
    it.
  status: accepted
  disposition_reason: null
- issue_id: I-008
  category: missing-invariant
  severity: medium
  description: 'ADR-0010 §6 fixes three constraints as "the price of §6''s order"
    and states "The SPEC must implement and test them": the reader has no tools and
    no filesystem, no code branches on its output, and blast radius is one image per
    invocation. This SPEC replaces the reader — plausibly with a different vendor,
    transport and SDK (`gemini-3.6-flash`, or `opus` via `claude_llm_bridge.py`, which
    the SPEC itself describes as a host-authenticated dev bridge) — and neither restates
    the constraints for the candidates nor tests them; §5''s five tests cover none
    of them. A reader swap is exactly the change that can silently reintroduce tool
    access ahead of the default-deny quarantine gate.'
  status: accepted
  disposition_reason: null
- issue_id: I-009
  category: risky-assumption
  severity: medium
  description: '§1''s comparison table is presented as one measurement but mixes populations:
    the shipped reader was measured on 20 images, the two candidates on 44, and the
    SPEC draws a pass/fail verdict against the ≤10% threshold across those unequal
    sets without addressing comparability. Separately, the shipped reader is eliminated
    on numbers taken under the old prompt, while §2.1 argues the candidates must not
    be ranked on old-prompt numbers because "otherwise the ranking is of readers we
    are about to change". The same reasoning is not applied to the reader being eliminated,
    and no argument is given for why the prompt change cannot affect its variation.'
  status: accepted
  disposition_reason: null
- issue_id: I-010
  category: untestable-requirement
  severity: medium
  description: '§4''s protocol amendments are stated as binding requirements but leave
    no artifact and are tested by nothing in §5: "Every `absent` verdict is looked
    at a second time, at full zoom, before it is recorded", questions on identifier
    fragments "are not asked", controls "scored first" with blinding. Nothing in the
    recorded output distinguishes a run in which the second look happened from one
    in which it did not, and §1.1 shows the second look changes verdicts (2 of 20
    flipped, eliminating the last candidate policy-value invention) — so the requirement
    most load-bearing for the gate''s outcome is the one with no evidence trail.'
  status: accepted
  disposition_reason: null
- issue_id: I-011
  category: untestable-requirement
  severity: medium
  description: §2.1's prompt rule is the SPEC's only substantive fix and has no efficacy
    criterion. §5 test 1 asserts only that `prompt_sha` changes — that the string
    differs, not that the defect is gone. Meanwhile §2.2(3) states markup-name disagreements
    "are recorded and do not disqualify", so the qualification cannot fail a candidate
    that ignores the new rule. Nothing in the SPEC establishes whether the fix worked,
    and §2.1's claim that this is "a transcription error with a precise remedy" (i.e.
    that a prompt instruction reliably suppresses it) is asserted, not measured.
  status: accepted
  disposition_reason: null
- issue_id: I-012
  category: adr-contradiction
  severity: medium
  description: '§6 defers the ADR-0006 signal ① perturbation with the trigger "When
    signal ① is next read". ADR-0010''s own Open items rejects this exact construction,
    striking an earlier draft''s trigger because it was "a trigger nothing can observe".
    The consequence is concrete rather than notional: ADR-0006 designates `v_entropy_signals`
    as the demand-pull gate for Slice 2, and this SPEC knowingly injects five `doc_reingest_events`
    rows that "look like undisciplined re-upload" into that trigger with no marker,
    so the corruption is committed now and the correction is owed to an event no one
    is obliged to notice.'
  status: deferred
  disposition_reason: '표식 기제가 이 SPEC 에 없다. `doc_reingest_events` 에 ''의도된 마이그레이션''
    을 구분할 컬럼이 없고, 그걸 만드는 것은 ADR-0006 의 엔트로피 신호 스키마를 건드리는 별개 변경이다. 다만 지적의 절반은 옳다 —
    ''신호 ① 을 다음에 읽을 때'' 는 아무도 지키지 않는 방아쇠다. 그래서 방아쇠를 **관측 가능한 것**으로 바꿨다: 이 마이그레이션이
    넣는 5행의 시각과 문서 rid 를 §6 에 적어 둔다. 신호를 읽는 사람이 그 목록과 대조하면 구분되고, 그것은 지금 확인 가능한 사실이다.'
- issue_id: I-013
  category: undefined
  severity: medium
  description: §2.2's qualification has no defined behaviour when fewer than two candidates
    survive. Step 2 eliminates any candidate exceeding 10% variation "regardless of
    anything else"; step 3's cross-check is defined only "between the two surviving
    candidates" and structurally requires two readers to produce one-sided disagreements.
    With one survivor there is no invention gate at all; with zero, no reader of record
    — and the currently shipped reader has already failed the same gate, so the corpus
    would be left on a reader the SPEC has disqualified with no stated fallback. The
    number of adjudicated questions per candidate is likewise not pre-registered,
    although the stringency of "any policy-value invention disqualifies" depends entirely
    on it.
  status: accepted
  disposition_reason: null
- issue_id: I-014
  category: undefined
  severity: low
  description: §2.3 and §5(5) require that `nexus status` "must show no coverage gap
    when it finishes" / "after the migration completes", without defining completion
    for an asynchronous re-embed queue, a bound on how long the corpus may sit with
    nulled vectors and tsvectors, or the behaviour if the queue stalls mid-migration.
    Relatedly, §2.4's assurance that the existing chunks are "labelled" because "`nexus
    status` already reports that their reader's variation is above threshold" holds
    only for the 20 images measured — §2.3 states the old identity keeps `NULL` on
    the other 24, for which status reports nothing.
  status: accepted
  disposition_reason: null
approved_by: LivingLikeKrillin
approved_at: '2026-08-11T11:01:07Z'
---

