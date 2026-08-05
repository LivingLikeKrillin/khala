---
target: SPEC-nexus-embed-tokenizer-race
critiqued_hash: sha256:285e24c5ff0c1f171b2113e745bc413bd281635dbd688e32dbc535a01461833f
critiqued_at: '2026-08-05T02:08:54Z'
issues:
- issue_id: I-001
  category: adr-contradiction
  severity: high
  description: '§1.1 leaves ADR-0008 §5''s backstop trigger unresolved: it concedes
    the clause covers "a tokenizer or embedding-model change", declines to argue it
    away, and then says "If the director reads that clause as firing here, this SPEC
    stops until the re-read happens" — while §3/§7 proceed to specify implementation.
    ADR-0008 §3 item 3 fixes the opposite procedure: a gate is "declared fired by
    the director and recorded in that direction''s first SPEC — it is not argued into
    existence by the SPEC." A conditional self-suspension is neither a recorded declaration
    nor a resolution; the SPEC''s own precondition is left in an undefined state,
    and nothing in §6 acceptance requires it to be settled before merge.'
  status: accepted
  disposition_reason: null
- issue_id: I-002
  category: missing-invariant
  severity: high
  description: 'The stated invariant is one-directional — "no event-loop code path
    calls the tokenizer object owned by the model" — and §5 tests only that direction
    plus the handler''s coroutine-ness. The symmetric invariant is never stated or
    checked: no worker-thread / `asyncio.to_thread` / threadpool path may call `guard_tokenizer`.
    The fix''s safety rests entirely on the guard copy having "exactly one user",
    so a future caller that touches the guard copy from inside the `to_thread` block
    (or any executor) reproduces the exact same `Already borrowed` defect against
    the new object, and every §5 check passes.'
  status: accepted
  disposition_reason: null
- issue_id: I-003
  category: risky-assumption
  severity: high
  description: The whole design rests on `copy.deepcopy(model.tokenizer)` producing
    a Rust tokenizer with an independent borrow state. No mechanism is given for why
    deepcopy of a `tokenizers` PyO3 object yields a genuinely separate backing object
    rather than a wrapper sharing it (behaviour depends on the library's `__deepcopy__`/pickle
    support and version). The only support offered is 3 rounds × 660 calls of zero
    errors — the same doc warns in §1 that a race's absence at low exposure is not
    evidence. No `tokenizers` / `sentence-transformers` version is pinned or recorded,
    so a dependency bump that changes deepcopy semantics silently reverts the fix
    while all §5 unit checks (which use a fake tokenizer, never a real one) still
    pass.
  status: accepted
  disposition_reason: null
- issue_id: I-004
  category: untestable-requirement
  severity: medium
  description: §6 accepts on "tests fail if the model's tokenizer is called on the
    event-loop path", but §5 admits the actual check is an AST call-node scan over
    one module that cannot see aliasing (`tok = model.tokenizer`), access via a helper
    or another module, or `getattr`. The acceptance criterion as written asserts a
    property the stated instrument cannot decide; either the acceptance should be
    narrowed to "direct `model.tokenizer(...)` call nodes in `embed_service/app.py`",
    or it is unfalsifiable in the general form it claims.
  status: accepted
  disposition_reason: null
- issue_id: I-005
  category: untestable-requirement
  severity: medium
  description: 'The first §5 unit test is self-defeating as specified: "A fake model
    whose `.tokenizer` raises on any call; the guard must still pass, using its copy."
    The guard''s copy is `copy.deepcopy(model.tokenizer)`, so the deep copy of a fake
    that raises on any call also raises on any call, and the test cannot pass unless
    the fake carries a bespoke `__deepcopy__` returning a different, benign object
    — which is unstated and, if added, means the test verifies only that the code
    calls *some* copy, not that deepcopy isolates a real tokenizer. Combined with
    "no network, no model", no CI test exercises the property the fix depends on.'
  status: accepted
  disposition_reason: null
- issue_id: I-006
  category: undefined
  severity: medium
  description: '`embed_errors` is defined only as "the number of requests that failed
    inside `/embed` since start", which does not resolve whether a 413 over-length
    rejection (§4 calls it "a counted failure") or a 503 not-ready response increments
    it, whether it resets on reload, or how a borrow-error 500 is distinguished from
    any other 500. Since §3 justifies the counter as making "recurrence" of *this*
    defect visible, an undifferentiated integer that may also count client-side 413s
    cannot serve that purpose, and §6 accepts on the counter''s existence without
    pinning which conditions increment it.'
  status: accepted
  disposition_reason: null
- issue_id: I-007
  category: adr-contradiction
  severity: medium
  description: 'ADR-0008 §6 states the Korean measurement gap "blocks three separate
    decisions: mecab-ko retention, an embedding-model change, and resume condition
    (b)", and §2.6 concludes "an embedding-model change is equally unevaluable". §1.1
    handles this by citing a director declaration recorded in `SPEC-nexus-embedding-cutover-seam`
    §1.1 rather than any amendment to the ADR, and ADR-0008''s own Status is "In review.
    Binding on acceptance." The result is a SPEC building on a lift of a block from
    a document that is not yet binding and whose §6 text still reads as blocking;
    the ADR-side record of the override is missing, so a future reader of ADR-0008
    alone sees an unlifted block.'
  status: deferred
  disposition_reason: 'The ADR-side record of the lift is missing, and correcting
    it means re-recording ADR-0008 — whose body §Status still reads ''In review''
    while the ledger stamps it accepted. Arbiter has no amend verb, so that is a re-record
    and re-approval of an approved artifact: a governed action of its own, already
    named as an open item in SPEC-nexus-embedding-cutover-seam §1.1. Bundling it into
    a defect repair would put a governance edit inside an implementation PR.'
- issue_id: I-008
  category: missing-invariant
  severity: medium
  description: The startup parity assertion covers only `model_max_length` equality,
    but §3's claim is behavioural parity — "return identical token counts" and "the
    413 fires on exactly the same inputs as before". Equal `model_max_length` does
    not imply equal tokenization (truncation defaults, added special tokens, padding
    side, `add_special_tokens` behaviour all affect `len(input_ids)`). The invariant
    that actually protects the 413 contract — identical `input_ids` length for identical
    input — is measured once by hand at three boundary lengths and never asserted
    at startup or in CI.
  status: accepted
  disposition_reason: null
- issue_id: I-009
  category: risky-assumption
  severity: medium
  description: 'The guard copy is created "at load time", in "the same load step"
    as the model, and readiness gating is derived from that co-location. Nothing states
    the invariant for a runtime model reload/swap (revision change, lazy reload after
    failure, hot-reload): if `model` is rebound without re-running the copy step,
    the guard silently validates against a stale tokenizer from the previous checkpoint
    while the encoder uses the new one — precisely the silent-divergence failure mode
    the design rejects the second-`from_pretrained` alternative for. No test or invariant
    covers the reload path.'
  status: accepted
  disposition_reason: null
- issue_id: I-010
  category: risky-assumption
  severity: medium
  description: §3 claims the design "does not turn a rare per-request failure into
    a total outage, the risk the review raised against the earlier one", but §4 specifies
    that a failed deepcopy leaves the service not ready with `/embed` at 503, and
    §5 makes a parity mismatch "a not-ready condition" — i.e. this design does introduce
    a total-outage failure mode, just a different one. The claim holds only under
    the unstated assumption that `copy.deepcopy` on this object is effectively infallible
    and deterministic across restarts; that assumption is never argued, and if it
    fails (e.g. an unpicklable component in some version) the result is a hard boot
    failure on a service that previously served ~99.5% of requests correctly.
  status: accepted
  disposition_reason: null
- issue_id: I-011
  category: risky-assumption
  severity: medium
  description: The false-pass arithmetic for the §5/§6 burst pools four errors observed
    across C=4, C=8, and C=16 into a single per-request Poisson rate (~0.5%, interval
    0.15%–1.3%) and then applies that rate to a differently-shaped run (2,000 at C=4
    + 400 each at C=8/C=16). A borrow-collision rate is a function of overlap between
    loop-side guard calls and worker-side encodes, so it is concurrency-dependent
    by construction; pooling assumes it is not. If the rate is materially lower at
    C=4 than at C=16, the burst's power is concentrated at the wrong load and the
    stated ~10⁻⁶ / ~1.5% false-pass bounds do not hold.
  status: accepted
  disposition_reason: null
- issue_id: I-012
  category: untestable-requirement
  severity: medium
  description: 'The throughput-regression check — "Peak throughput within 15% of the
    recorded peaks (8.82 rps `/embed`, 7.62 rps `/search`)" — has an escape hatch
    with no criteria: "a breach does not automatically block the merge, it blocks
    *closing this SPEC* until explained." What counts as an adequate explanation,
    who judges it, and what happens if the explanation is "we don''t know" are all
    unspecified, and the baseline is admitted to be single runs with no variance estimate.
    As written the criterion cannot fail, which makes §2''s in-scope claim that a
    throughput regression is checked ("a claim like that has to be checked") unenforceable.'
  status: accepted
  disposition_reason: null
- issue_id: I-013
  category: unverifiable-claim
  severity: low
  description: §1's concurrency numbers cite a specific artifact (`nexus/tests/eval/reports/2026-08-05-sidecar-concurrency.md`),
    but §3's parity measurements — identical `model_max_length` of 8192, identical
    token counts at 8188/8193/8198, `name_or_path == 'nlpai-lab/KURE-v1'` "verified
    on the running service" — cite no report, script, or run record. These carry the
    argument that the 413 contract is unchanged, yet a reviewer has no way to reproduce
    or check them, and §5's live 413 test samples only two points (over/under 8,192).
  status: accepted
  disposition_reason: null
- issue_id: I-014
  category: scope-creep
  severity: low
  description: §2 declares "Not an alerting or metrics system", then §3 adds an `embed_errors`
    counter to `/health`, §4 extends the health contract with a new named error condition,
    and §6 makes both acceptance criteria. The counter fixes nothing about the borrow
    race and is justified only by a general observability argument ("a defect found
    only by a follow-up measurement should leave *something* behind"); it expands
    a published health contract inside a defect-repair SPEC whose §2 explicitly disclaims
    that territory.
  status: accepted
  disposition_reason: null
- issue_id: I-015
  category: undefined
  severity: low
  description: §3 asserts the design introduces "no new fail-to-boot condition for
    a deployment running with `EMBED_REVISION` unset", but `EMBED_REVISION` appears
    nowhere else in this SPEC and is not defined, sourced, or linked to the SPEC that
    introduces it. A reader cannot tell whether such deployments exist, whether the
    variable is currently unset in production, or how large the avoided risk actually
    was — which is the entire weight of that bullet.
  status: accepted
  disposition_reason: null
approved_by: LivingLikeKrillin
approved_at: '2026-08-05T03:40:28Z'
---

