---
target: SPEC-nexus-ko-eval-pool-sensitivity
critiqued_hash: sha256:9bc5c521a60c27be0cb45cc7f4ace00c0ee196acde777696f1b4f2d695d05cea
critiqued_at: '2026-08-05T08:59:07Z'
issues:
- issue_id: I-001
  category: adr-contradiction
  severity: high
  description: §0 states the entire work (instrument repair, bound, concentration
    test, 30-pair sample) was performed on 2026-08-05 before the SPEC entered the
    gate. ADR-0009 §3(ii) recorded the identical inversion as 'an exception, and calling
    it anything else would be worse', 'not a licence', with 'nothing currently prevents
    recurrence' as an open item owned by the director. This SPEC is the second instance,
    names it, and supplies no mechanism — it asks the gate to ratify the recurrence
    of a departure that the linked ADR explicitly refused to license. ADR-0008 §3
    item 3 likewise requires the gate to be declared and recorded, not argued into
    existence after the artifact.
  status: deferred
  disposition_reason: An inversion that already happened cannot be edited away. Section
    0 names it as the second instance of the departure ADR-0009 3(ii) refused to license,
    and supplies no mechanism because none exists. Ratifying or refusing the recurrence
    is the approver's act, not a documentation change.
- issue_id: I-002
  category: risky-assumption
  severity: high
  description: '§8 and §4.5 compare the sample''s unstructured base rate (point estimate
    25–50 relevant pairs of 746) against §3''s adversarial minimum of ''10 pairs in
    a specific pattern'', and conclude ''the confirmatory margin may be an artefact
    of incomplete adjudication''. These are not commensurable quantities: §3''s 10
    pairs are a hand-picked adversarial set (specific queries, specific cost-1 documents),
    while the base rate describes relevant pairs distributed as the pool actually
    holds them. Randomly distributed relevant judgements can equally widen the margin
    (§1''s own three-way argument), so the count of relevant pairs anywhere in the
    pool places no bound on the probability that the adversarial pattern is realised.
    The inference routed to the director as ''evidence'' does not follow from the
    measurement.'
  status: accepted
  disposition_reason: 'Correct and the inference is retracted in section 8. The base
    rate and the adversarial minimum are not commensurable: 10 pairs is a specific
    pattern, the rate describes pairs scattered as the pool holds them, and a relevant
    KURE-only pair widens the margin. What would license a probabilistic statement
    (a distributional calculation) is named as not done.'
- issue_id: I-003
  category: missing-invariant
  severity: high
  description: 'The unit of a relevance judgement is not fixed and the two sections
    disagree. §3 states ''The unit is the pair'' and costs every move in (query, document)
    pairs. §4 reasons at document level: the concentration table''s intervention is
    ''documents declared non-relevant'', and the complementary branch claims ''one
    document buys 7 moves at once'' for node-autoscaling.md. If judgements are per-pair,
    that document costs 7, not 1, and §4''s branch is mis-stated; if judgements are
    per-document (a document is relevant or not, globally), then the 82 cost-1 documents
    can each buy several moves and the true adversary minimum is well below the headline
    10. The bound''s headline number changes depending on which model holds, and no
    section states which the DP implements.'
  status: accepted
  disposition_reason: 'The DP costs (query, document) pairs; section 4''s document-level
    sentence was wrong. Corrected: node-autoscaling.md in 7 cost-1 positions is 7
    judgements, not one move-buying decision. Concentration changes the correlation
    between judgements, not the adversary''s price.'
- issue_id: I-004
  category: unverifiable-claim
  severity: high
  description: §0 tells reviewers 'to treat the numbers as claims to verify' and offers
    '§7 is the test suite that would fail if the numbers were wrong'. §7's CI regression
    explicitly re-computes the headline figures from a committed fixture of per-query
    (outcome, flip cost, tie cost, removal availability) — i.e. from the outputs of
    the very run being checked — and states the live eval store is deliberately not
    used. The suite therefore verifies the DP's arithmetic over asserted costs, never
    that the costs or outcomes match the store. If the move costing was wrong on 2026-08-05,
    no test in §7 can fail.
  status: accepted
  disposition_reason: The committed fixture is an output of the run being checked,
    so it cannot verify the costing. Section 7 now splits the regression into a CI
    half (DP arithmetic only, and says so) and a store-dependent half that recomputes
    costs and is reported when skipped.
- issue_id: I-005
  category: missing-invariant
  severity: high
  description: §4.5 pre-registers that proposed_by and reviewed_by are 'recorded and
    required to differ', and §4.5.1 reports reviewed_by empty — an incomplete record
    by the SPEC's own rule. Yet the incomplete result is used as load-bearing evidence
    in §8 ('the point estimate is 2.5–5× the 10 pairs'), in §9 ('a judgement against
    the point estimate'), and in the decision not to buy resolution; §6 also ships
    the unreviewed judgements as a committed artifact (pool-sensitivity-sample.json)
    that §7 pins a test against. The 'nothing ships until reviewed' guard covers documentation
    only and does not cover the three uses that actually influence the disposition.
  status: accepted
  disposition_reason: 'The unreviewed record was load-bearing in sections 8 and 9
    and in the not-buying decision. Scoped: until review lands, the sample supports
    one sentence only - the pool has not been shown free of relevant pairs. The artifact
    stays committed with reviewed_by null, because a published judgement with its
    reasons is auditable and a withheld one is not.'
- issue_id: I-006
  category: adr-contradiction
  severity: high
  description: 'ADR-0009''s open-item table sets the trigger for two items (a backstop
    detector; a usable predicate for ''materially expand'') as ''the next SPEC that
    links ADR-0008'', chosen precisely because it is detectable. Both SPECs in this
    round carry linked_adrs: ADR-0008, so the trigger is now spent. Item 2 (the predicate)
    is not addressed by either SPEC (§1.2.2), and §6 explicitly declines to supply
    one. §1.2.1 concedes ''nothing guarantees another ADR-0008-linked SPEC''. The
    net effect is that ADR-0009''s only detectable trigger is consumed without discharging
    the items it was created to force, leaving them open with no remaining event to
    surface them.'
  status: deferred
  disposition_reason: 'Factually correct and unfixable by this SPEC: both SPECs in
    the round link ADR-0008, so the trigger is spent, and the predicate item is addressed
    by neither. Whether a spent trigger can be re-armed is ADR-0009''s owner''s decision,
    put as questions 1 and 2 in section 1.2.'
- issue_id: I-007
  category: undefined
  severity: medium
  description: '§1.2 poses four items ''as questions requiring an answer, not as dispositions''
    — including whether ADR-0009''s rollback-guard trigger fires on this work — and
    no answer is supplied anywhere in the document. But the SPEC does not wait: §5
    and §6 ship changes touching ko_eval_embeddings and the shared conftest. An approved
    SPEC that ships while its own gate questions are unanswered means the answers,
    whatever they turn out to be, arrive after the work again (see §0).'
  status: accepted
  disposition_reason: 'Paid. Section 1.2 now states the four questions are a precondition
    on implementation: no code from section 6 is written until they are answered,
    and approval covers the record and the plan, not authority to start.'
- issue_id: I-008
  category: undefined
  severity: medium
  description: 'The backstop record is internally inconsistent about whether a backstop
    event occurred. It reports reread: ''performed 2026-08-05'' (a re-read is what
    ADR-0008 §5 prescribes *at* a backstop event) while simultaneously ruling clause:
    none / does-not-fire. §8 then reports the non-re-check of conditions (a) and (c)
    as a stated deficiency — but if the trigger does not fire, those re-reads are
    not owed, and if it does fire, the ruling is wrong. Which of the two the record
    means determines whether §8''s ''Not re-checked'' paragraph is a disclosed omission
    or a category error.'
  status: accepted
  disposition_reason: The backstop record now states that ADR-0008 section 5's re-read
    is what one performs in order to judge whether the event fires, so 'read it, ruled
    does-not-fire' is coherent, and that (a)/(c)'s re-reads are owed only for a firing
    event.
- issue_id: I-009
  category: untestable-requirement
  severity: medium
  description: '§7 requires that ''seed 20260805 over the committed pool-blind.json
    reproduces the same 30 pairs'' and calls this ''the test that makes §A checkable
    without the database''. Three inputs are unpinned: (1) random.Random.sample is
    CPython-version-dependent and only ''CPython'' is named, no version; (2) the population
    order depends on labels.yaml ordering and pool-blind.json file order, neither
    of which is asserted immutable; (3) the population is the 36-query comparable
    subset and its 9 refused-chunk documents, which are derived from the eval store
    — §6''s ship table commits no artifact carrying the refused-chunk list, so the
    test as described cannot be built from committed files alone.'
  status: accepted
  disposition_reason: Paid. Section A.1 pins CPython 3.11+ as part of the procedure
    (Random.sample is an implementation detail) and section 6 commits refused-chunk-docs.json,
    so the population is reconstructible from files alone.
- issue_id: I-010
  category: risky-assumption
  severity: medium
  description: §4.5 defect 2 concedes 'the same actor computed the costs and proposed
    the judgements' with no held-out artifact and no separate process. The judgements
    are therefore taken by a party that knows which pairs are cost-1 moves, which
    is exactly the correlation that would bias a base-rate estimate of adversary-relevant
    pairs in either direction. Publishing the list (§A) makes the judgements auditable
    but does not remove the correlation, and §8 nonetheless routes the resulting point
    estimate to the director as evidence bearing on an accepted ADR's stated ground.
  status: deferred
  disposition_reason: 'The correlation cannot be removed after the fact - the same
    actor computed the costs and proposed the judgements. Publishing the full list
    in appendix A makes it auditable, which is mitigation, not repair. Binding on
    any future sample: the roles must be separated before drawing.'
- issue_id: I-011
  category: missing-invariant
  severity: medium
  description: §4.5's relevance criterion ('the document contains the information
    the query asks for — could stand alone as the answer source; topical adjacency
    is not relevance') is stated fresh and is nowhere reconciled with the criterion
    used for the original blind adjudication that produced labels.yaml / pool-rev2-adjudication.json.
    If the two differ, the sampled base rate does not estimate the quantity §3's bound
    is denominated in, and any future full adjudication under this criterion yields
    a gold set inconsistent with the labels the harness already scores against — with
    no invariant requiring the criteria to match.
  status: deferred
  disposition_reason: 'Correct and unchecked: the relevance criterion here was written
    fresh and never reconciled with the one behind labels.yaml and pool-rev2-adjudication.json.
    Owed before any full walk, since a mismatch would make the sampled rate estimate
    a different quantity than the bound is denominated in.'
- issue_id: I-012
  category: undefined
  severity: medium
  description: §5 item 3 adds ko_eval_embeddings to clean_db and then makes the fixture
    'refuse to run against a database whose store is populated unless --allow-eval-store-truncation
    is passed'. The flag's mechanism is unspecified (pytest CLI option, env var, marker),
    and because clean_db is a shared fixture, the default behaviour is that the entire
    suite refuses to run on any machine where the store is loaded — the normal state
    for anyone doing this work. That converts a silent corruption into a hard block
    on all testing, with no documented path that both preserves the hours-costly store
    and runs the suite, and it sits awkwardly against the repo's existing disposable-test-DB
    discipline (the suite truncates; the store now says it may not).
  status: accepted
  disposition_reason: Paid, by inverting the default. clean_db truncates the eval
    store like everything else - the repo's disposable-test-DB discipline - and a
    developer protecting an expensive store sets NEXUS_PRESERVE_KO_EVAL_STORE=1, which
    skips the store and skips the suites depending on it. An env var because clean_db
    is autouse.
- issue_id: I-013
  category: unverifiable-claim
  severity: medium
  description: §4's load-bearing claims — '82 distinct documents each supply a cost-1
    move', the four-row concentration curve, and 'two documents together cover 11'
    — have no coverage in §7. The committed regression fixture holds per-query (outcome,
    flip cost, tie cost, removal availability) only, which cannot reconstruct per-document
    cost-1 attribution. §9 lists 'concentration's favourable branch only' as a standing
    risk, so these numbers are cited in the risk register while being recomputable
    on one machine only.
  status: accepted
  disposition_reason: Section 7 now assigns the per-document concentration figures
    to the store-dependent half explicitly, and section 9 keeps them as recomputable
    on one machine.
- issue_id: I-014
  category: scope-creep
  severity: medium
  description: 'A SPEC whose stated subject is pool sensitivity ships three unrelated
    production-shaped changes: a new CLI subcommand (ko_eval_embed_compare restore-chunks)
    with its own content-verification semantics, a new abort precondition in ko_eval_harness,
    and a new opt-in flag on the shared conftest fixture. §1.1 additionally records
    that an adjudication protocol previously removed as unbought work was executed
    anyway at n=30 and is now shipped as a committed artifact. Each of these is defensible
    on its own; none is the sensitivity analysis, and the SPEC asks for one approval
    covering all of them.'
  status: deferred
  disposition_reason: 'Correct: three changes (restore-chunks, the scorer precondition,
    the conftest fixture) are bundled with a sensitivity analysis under one approval.
    Section 5 already requires them to land as their own commit; whether they need
    their own SPEC is the approver''s call.'
- issue_id: I-015
  category: risky-assumption
  severity: low
  description: §3's DP condition is pre-registered as p > 0.05 or W + L < 6. The reachable
    defeat W22 L10 at p = 0.0501 satisfies that condition as written, but is set aside
    as 'too close to α to carry a claim on its own'. Discarding a case that meets
    a pre-registered threshold on a post-hoc closeness judgement is the same defect
    §4.5 defect 1 records against itself; here it happens not to change the headline
    10, but the rule and its application no longer agree.
  status: accepted
  disposition_reason: W22 L10 at p = 0.0501 satisfies the pre-registered p > 0.05
    and was set aside on a post-hoc closeness judgement - the same defect section
    4.5 records against itself. Both cost-10 defeats are now reported without editorial.
- issue_id: I-016
  category: unverifiable-claim
  severity: low
  description: §4.5's confidence intervals apply Clopper–Pearson (a binomial interval)
    to a sample drawn 'uniformly without replacement' from a finite population of
    746 (§A.1). The sampling distribution is hypergeometric; the mismatch is conservative
    at n/N ≈ 4% and does not change the 'spans 10' conclusion, but the interval is
    labelled '95 %' without stating the approximation. Combined with §4.5's own 'unquantified
    error term' from heading-level read depth, the reported interval is not the coverage
    the label asserts.
  status: accepted
  disposition_reason: Clopper-Pearson is a binomial interval applied to a draw without
    replacement; the exact distribution is hypergeometric. Now stated as an approximation,
    conservative at n/N about 4 percent, and noted as excluding the read-depth error.
approved_by: LivingLikeKrillin
approved_at: '2026-08-05T09:28:49Z'
---

