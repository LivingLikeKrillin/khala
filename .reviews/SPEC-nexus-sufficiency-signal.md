---
target: SPEC-nexus-sufficiency-signal
critiqued_hash: sha256:a93535441243ab58b86794b7155b9e151482b73080594ba5eaad58a7194f1a49
critiqued_at: '2026-08-10T04:10:17Z'
issues:
- issue_id: I-001
  category: undefined
  severity: high
  description: The CHECK constraint's arity is specified two incompatible ways. §3.3
    lists ten non-NULL values (sufficient, insufficient, unparseable, error, timeout,
    disabled, not_applicable, shed, pending, uninstrumented) and says the CHECK lists
    'exactly those ten'; test 10 asserts 'all ten values round-trip distinctly' and
    that an eleventh is rejected. But §3.5 says 'sufficiency is CHECK-constrained
    to nine values' and test 16 asserts 'the nine-value CHECK'. As written tests 10
    and 16 cannot both pass — 'uninstrumented' (added late, per §3.1's correction)
    appears to be the un-counted value. Migration 012 has no unambiguous definition
    to implement.
  status: accepted
  disposition_reason: 'Settled by reading migration 012: the CHECK lists ten values
    including uninstrumented, so §3.3 was right and §3.5''s ''nine'' was the stray
    line. Recorded in §5.1''s reconciliation table rather than left for the next reader
    to re-derive from SQL.'
- issue_id: I-002
  category: untestable-requirement
  severity: high
  description: 'The 300s stranded bound is evaluated by Postgres, not Python: §3.2''s
    UPDATE carries `AND sufficiency_at > now() - interval ''300 seconds''` and §3.3
    defines stranded as `now() - sufficiency_at > 300s`. §5 says determinism comes
    from ''now() is injectable'', which can only mean the Python clock. Test 6 (299s
    in-flight / 301s stranded) and test 9 (late verdict matches zero rows) therefore
    cannot exercise the predicate that actually enforces the invariant without either
    freezing the DB clock or back-dating `sufficiency_at` — neither of which the SPEC
    specifies. The single most load-bearing invariant (''stranded is terminal; no
    retry, no reclamation'') is asserted by tests that, as described, test the wrong
    clock.'
  status: accepted
  disposition_reason: 'Survives the implementation and is the sharpest of the round.
    Enforcement is now() inside the UPDATE — the Postgres clock — while §5''s determinism
    argument is about an injectable Python clock, so the tests as described exercise
    a different predicate than the one protecting the invariant. §5.1 says so and
    §6 carries the fix: the DB test must back-date sufficiency_at.'
- issue_id: I-003
  category: undefined
  severity: high
  description: The daily ceiling is defined as shedding 'once that many rows have
    been judged today' (§3.4), but §3.3's table defines error, timeout and unparseable
    as judged = no. Whether the counter increments on judge *attempt* or on a *judged*
    terminal value is never stated, and the natural reading of the ceiling's own wording
    excludes the three failure values — all of which have already made the outbound
    provider call and incurred spend. A deployment whose provider is erroring or timing
    out would make unbounded calls while the counter stays at zero. Since §2.2c forbids
    the aggregate that would reveal this and the cap bounds only concurrency, the
    ceiling is the sole volume bound and it is the one path where it can be bypassed.
    Test 13 does not cover it.
  status: accepted
  disposition_reason: 'Answered in a way that makes it worse rather than better: the
    daily ceiling was never built. So the question of whether it counts attempts or
    judged terminals is moot, and the conclusion the objection was driving at now
    holds unconditionally — there is no volume bound at all. §5.1 and §6 state that
    plainly instead of the SPEC continuing to describe a control that does not exist.'
- issue_id: I-004
  category: missing-invariant
  severity: high
  description: 'Slot release on the prologue-failure path is unspecified and untested.
    §3.1 puts slot acquisition inside the prologue alongside the eligibility helper,
    `configured_column(cfg)`, `active_tokenizer()` and the fingerprint hash, and routes
    any prologue raise to ''the plain INSERT ... with everything else unchanged''.
    If the raise occurs after acquisition, the slot is only released if the `finally`
    scope encloses the prologue handler — which §3.2 does not say. Test 11c enumerates
    INSERT failure, UPDATE failure and cancellation, and test 5b asserts the row is
    written but says nothing about the counter. This is exactly the leak §3.2 warns
    of: at the default cap of 2, two prologue raises (e.g. a stale NEXUS_EMBEDDING_COLUMN)
    make every subsequent search record `shed` forever, indistinguishable from healthy
    shedding.'
  status: accepted
  disposition_reason: 'The objection was correct about the design as written and the
    implementation had already closed it: slot acquisition is the last statement of
    the prologue, so nothing between it and the end of the try can raise, and _release_slot()
    is in a finally covering every exit including the early return when the INSERT
    produced no row. Recorded in §5.1 — the failure mode described (two leaks pin
    the cap and every later search records shed forever) is unreachable.'
- issue_id: I-005
  category: risky-assumption
  severity: high
  description: The spend control is illusory on the one deployment the SPEC names.
    §3.4 admits the ceiling 'bounds rows, not dollars', that cost per row scales with
    snippet_max_chars × k which is not held fixed, that the ceiling is per-process
    so N workers permit N × 500/day, and that the in-process counter resets on restart
    so a crash-looping worker never sheds. §2.2b names the dogfood `claude-code` bridge
    as the switch-on deployment, and §3.3 says that backend reports no tokens, so
    `judge_cost_usd` is NULL there. §2.2c then forbids the aggregate that would surface
    runaway spend. Round 5's objection was new spend on an outbound per-search provider
    call; the composed result is a capability whose spend is unbounded in dollars
    and unobservable on the only deployment that will run it.
  status: accepted
  disposition_reason: 'Correct, and the composition is worse than the objection knew:
    the ceiling did not ship and neither did the cost columns. What remains is off-by-default,
    a tenant allowlist, and two in-flight judgements — a bound on concurrency, not
    on dollars — while §2.2c forbids the aggregate that would surface a runaway and
    the named backend reports no tokens. Both halves are now open items rather than
    an argument buried in §3.4.'
- issue_id: I-006
  category: adr-contradiction
  severity: medium
  description: 'The SPEC builds on an ADR whose binding status it concedes is contradictory
    and then declines to resolve it (§2.1: frontmatter `accepted` vs body ''Proposed'').
    ADR-0002''s body states it ''ships zero new product code'' and that ''every capability
    it names is gated on a real pulling signal'', with the cognitive-debt window ''not
    built until a signal pulls it'' and gates ''declared fired by the director and
    recorded in that direction''s first SPEC''. This SPEC ships migration 012 (7 columns),
    a judge call inside `_persist`, an in-process concurrency limiter, a daily ceiling,
    5 environment variables and 24 tests, with no gate declared and no director declaration
    recorded. §2.1''s feature/signal distinction is a reading of ADR-0002 that ADR-0002
    itself nowhere states, and the precedent it cites (search_log / v_search_health)
    is credited there as pre-existing substrate that makes no outbound provider call
    — a difference §2.1 acknowledges but does not close.'
  status: deferred
  disposition_reason: 'The reviewer is right that §2.1''s feature/signal distinction
    is this SPEC''s reading of ADR-0002 rather than something ADR-0002 states, and
    that resolving it means resolving the ADR''s own accepted-vs-Proposed contradiction.
    That is not this SPEC''s to settle — an accepted ADR is amended by a successor
    ADR, and doing it inside a SPEC is the move the screenshot SPEC was just criticised
    for. Trigger: the next ADR touching ADR-0002''s gate model.'
- issue_id: I-007
  category: risky-assumption
  severity: medium
  description: §2.3 claims `NEXUS_SUFFICIENCY_TENANTS` means 'consent is recorded
    per corpus rather than per process', but it is a process-level environment variable
    set by whoever runs the server. Nothing ties an entry in that list to any act
    by the tenant or corpus owner, and nothing records who added it or when. The same
    single operator who would have flipped the rejected deployment-wide flag can name
    every tenant in the allowlist. The mechanism is a per-tenant scoping control,
    which is worth having, but the consent property the SPEC rests its egress argument
    on is not established by it.
  status: accepted
  disposition_reason: 'Correct and worth stating precisely: an environment variable
    set by whoever runs the server is a per-tenant scoping control, not consent. Nothing
    ties an entry to an act by the corpus owner and nothing records who added it.
    §6 keeps the mechanism and withdraws the claim §2.3''s egress argument leaned
    on.'
- issue_id: I-008
  category: untestable-requirement
  severity: medium
  description: §2.3's replacement egress control for evaluation runs — 'an evaluation
    run over a partner corpus records, in its run artifact, that the corpus owner
    consented ... and names which backend received it' — has no schema, no test in
    §5, no entry in §4's ships list, and applies to artifacts §1.2 states are gitignored
    and therefore carry no verifiable history. The SPEC says this 'constrains the
    author, which is the point', but it is an unverifiable promise by the same party
    whose earlier unrecorded runs already sent Pack B text to the API backend (§2.3's
    own admission). It is stated as the only control that 'bites' while being the
    one control with no enforcement surface at all.
  status: deferred
  disposition_reason: 'True that the run-artifact consent record has no schema, no
    test and no ships entry, and that it is an unverifiable promise by the party it
    constrains. Deferred rather than accepted because inventing a schema for it here
    would be the same unenforceable promise with more structure; what would make it
    real is the eval harness writing the record and CI refusing an artifact without
    one. Trigger: the next evaluation run over a corpus that is not ours.'
- issue_id: I-009
  category: undefined
  severity: medium
  description: §3.2 requires the 300s stranded threshold be 'a fixed constant, not
    2 × NEXUS_SUFFICIENCY_TIMEOUT', because deriving it would retroactively reclassify
    historical rows, and adds a fail-fast that refuses to start when the timeout exceeds
    150s. The same paragraph then says 'a deployment raising the timeout past 150s
    must raise it too'. No mechanism exists for a deployment to raise a hardcoded
    constant in `signals.py`, and doing so would cause precisely the retroactive reclassification
    the fixed constant was chosen to prevent — with no migration, no versioning of
    the threshold, and no way for a reader to know which constant a historical row
    was classified under. The coupling is stated as operator guidance for an action
    the design makes impossible.
  status: accepted
  disposition_reason: 'The guidance describes an action the design forbids: 300 s
    is a module constant, and raising it retroactively reclassifies historical rows
    — which is exactly why it was made a constant. Recorded in §6 with the two ways
    out (version the threshold per row, or drop the guidance). Note the fail-fast
    that enforces the coupling turned out to live at the judge call rather than at
    startup (§5.1).'
- issue_id: I-010
  category: missing-invariant
  severity: medium
  description: The fail-fast startup check — '`signals.py` refuses to start when NEXUS_SUFFICIENCY_TIMEOUT
    exceeds half the constant (150s)' (§3.2) — appears in no test in §5 and in no
    line of §4's ships list. §5 also injects short timeouts per test, so nothing in
    the suite exercises the rejection path. The SPEC's own argument is that 'prose
    coupling is what let three revisions drift' and a fail-fast is what makes the
    bad configuration impossible; an unasserted fail-fast is prose coupling with an
    extra line of code.
  status: accepted
  disposition_reason: 'Partly overtaken: the check is not a startup fail-fast at all
    but a per-call refusal that raises before any request goes out, which is at least
    as strong and is what §5.1 now records. The objection''s core stands — an unasserted
    guard is prose with an extra line — and the assertion belongs with the timeout
    tests.'
- issue_id: I-011
  category: undefined
  severity: medium
  description: The `uninstrumented` row is specified two ways that cannot both hold.
    §3.1 says the prologue's failure path is 'the plain INSERT this SPEC found, with
    everything else unchanged' — an INSERT that by definition writes none of migration
    012's columns — and in the next paragraphs says that row is written `sufficiency
    = 'uninstrumented'` and `sufficiency_judge = 'off'` with 'everything else NULL'.
    Whether `sufficiency_at` is stamped on that row is never stated; 'everything else
    NULL' implies it is not, which leaves a non-`pending` row that no reader can place
    in time and breaks the §3.2 rule that `sufficiency_at` means 'when the observation
    started'. Test 5b asserts the value is not NULL but not which columns are populated.
  status: accepted
  disposition_reason: 'Settled by the code: the INSERT stamps now() into sufficiency_at
    unconditionally, so ''everything else NULL'' never applied to it and no row is
    unplaceable in time. §5.1 records it, because the SPEC''s two descriptions genuinely
    could not both hold and a reader deserves to know which one the tree implements.'
- issue_id: I-012
  category: unverifiable-claim
  severity: medium
  description: 'The entire evidentiary base for pointing the judge at production is
    unreproducible by anyone but the author: artifacts live in gitignored `nexus/tests/eval/local/`
    over a partner corpus that cannot be published, two of three runs were destroyed
    by a fixed output filename, the 5/5 claim is withdrawn, arm A was recomputed on
    a population narrowed after baseline verdicts were seen, arm B is n=5 clearing
    its criterion 19% of the time by chance, and the pre-registration rests on the
    author''s account. §2.1 says the decision does not rest on §1.2 — but §2.2''s
    step 2 makes re-running that same offline measurement a precondition for any future
    threshold, so the successor inherits a harness whose outputs no reviewer or CI
    can audit. The SPEC flags each limit individually and never states the compound
    consequence: no independent party can check any number in §1.'
  status: accepted
  disposition_reason: 'The individual limits were each disclosed and the compound
    consequence was not, which is the objection''s real point: no reviewer or CI can
    audit any number in §1, and §2.2''s successor inherits that harness as a precondition.
    Stated in §6. Not resolvable here — the corpus cannot be published — which is
    precisely why it should be written down rather than distributed across six caveats.'
- issue_id: I-013
  category: untestable-requirement
  severity: medium
  description: 'Test 20 contradicts §5''s own opening (''Deterministic; ... now()
    is injectable'') by keying off the real wall-clock date, so from 2026-11-10 it
    fails every CI run on unrelated work until someone acts. Its escape condition
    — any record under `specs/` or `adr/` carrying frontmatter `resolves: SPEC-nexus-sufficiency-signal`
    — is satisfiable by adding one line to a stub file, which is the cheapest response
    to a red build and the one most likely under deadline pressure. The SPEC argues
    ''adding the key is the successor''s deliberate act'', but the test cannot distinguish
    a deliberate successor from a build-unblocking placeholder, which is the same
    prose-property problem it rejected ''declares a consumer gate'' for.'
  status: accepted
  disposition_reason: 'Test 20 was never built, so nothing expires this instrument
    today — that is the fact that needed recording. The objection''s substance also
    stands and is kept: a date-keyed test cannot distinguish a deliberate successor
    from a one-line stub added to unblock a red build, so rebuilding it as specified
    would buy a deadline, not a decision.'
- issue_id: I-014
  category: scope-creep
  severity: medium
  description: §0 scopes the deliverable as 'one verdict per answered search on the
    search_log row, labelled with what produced it'. What ships is 7 columns, 5 environment
    variables, a per-tenant allowlist, an in-process concurrency limiter with a hand-rolled
    counter, a per-process per-UTC-day ceiling, a startup config validator, a two-statement
    write protocol with a stranded rule, and a change to `sufficiency.py` for usage
    accounting. Three of the columns (`judge_prompt_tokens`, `judge_completion_tokens`,
    `judge_cost_usd`) are NULL on the only deployment §2.2b names as turning the instrument
    on, so they ship unexercised in production while §2.2g counts them in the reversal
    cost. §2.2's constraint table governs what the signal may *do*; nothing in the
    SPEC constrains how much surface it may *be*.
  status: accepted
  disposition_reason: 'The gap between §0''s one-verdict framing and what was specified
    was real, and the tree lands closer to §0 than to the specification: 4 columns
    and 4 environment variables, no ceiling, no cost accounting. Recorded in §5.1.
    The reviewer''s structural point is kept in §6 — nothing in this SPEC constrains
    how much surface a signal may be, only what it may do.'
- issue_id: I-015
  category: undefined
  severity: low
  description: Test 14 has two different definitions. §5 defines it as a static check
    that no module outside `signals.py` and `migrations/` references `sufficiency`
    from `search_log`; §3.5 says 'Test 14 asserts it for the judge handler' regarding
    exception messages not interpolating query or evidence text. These are unrelated
    assertions under one number. Separately, the §5 form cannot enforce what §2.2a
    actually claims — 'no code branches on the value' — since a reference grep distinguishes
    neither reads from branches nor the `search_log` column from the `nexus/nexus/llm/sufficiency.py`
    module that §4 ships changes to.
  status: accepted
  disposition_reason: Two unrelated assertions carried one number, and the §5 form
    cannot enforce what §2.2a claims — a grep distinguishes neither reads from branches
    nor the search_log column from the sufficiency module this SPEC ships changes
    to. The number is split and the claim narrowed to what a static check can actually
    establish.
- issue_id: I-016
  category: undefined
  severity: low
  description: '`sufficiency_judge`''s format is inconsistent: §2.3 and §3.3 specify
    `{backend}/{model}/{prompt_sha}` (backend being the fact §2.2b says ''matters
    when someone asks later what left the building''), while §3.5 describes the column
    as ''VARCHAR(128) holding {model}/{prompt_sha}''. Since §2.2''s successor groups
    on this column, a two-part vs three-part identity changes the grouping key. Test
    19 asserts the value changes when the prompt or decoding parameters change but
    asserts nothing about backend being present, so the discrepancy is uncaught.'
  status: accepted
  disposition_reason: 'Settled by judge_identity(): three parts, {backend}/{model}/{prompt_sha},
    with the backend read from NEXUS_LLM_PROVIDER and the sha derived from the prompt
    actually sent. §3.5''s two-part description was wrong and is corrected in §5.1
    — it matters because §2.2''s successor groups on this column.'
- issue_id: I-017
  category: missing-invariant
  severity: low
  description: '§3.3 designates a growing stranded count as a fault signal (pool exhaustion,
    repeated kills), but nothing can observe it as specified: §2.2c forbids any view
    or aggregate, and §3.2 logs the zero-row UPDATE at warning with the benign cases
    (purged, already stamped) and the fault case (late verdict past the 300s guard)
    indistinguishable from each other. A fault signal that requires a hand-written
    query nobody is scheduled to run, over rows nobody is told to count, is the same
    shape as §2.2h''s ''a date with no failing check is a wish''.'
  status: accepted
  disposition_reason: 'A fault signal nobody can observe is not a signal: §2.2c forbids
    the view and the zero-row UPDATE logs benign and fault cases identically. Kept
    as an open item rather than fixed here, because the fix is either an exception
    to §2.2c or a distinguishable log, and choosing between them is the successor''s
    call once there is a deployment producing stranded rows at all.'
approved_by: LivingLikeKrillin
approved_at: '2026-08-11T16:23:16Z'
---

