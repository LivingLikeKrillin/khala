---
target: SPEC-nexus-vision-source-ref
critiqued_hash: sha256:752f247c5b8b6b58407ae5021ae6caa1d1e6b09b4ebf0ba23f36404627f3740a
critiqued_at: '2026-08-11T15:01:14Z'
issues:
- issue_id: I-001
  category: risky-assumption
  severity: high
  description: §2.1/§2.4 model the image→reference relation as 1:1, but ADR-0010 §5
    keys storage by (byte hash, extractor_identity) — one row per *bytes*. The same
    image bytes pasted into two Notion blocks or two documents collapse to a single
    row that can hold only one (block_id, source_uri). The cache-hit fill in §2.4
    is first-walk-wins and the spec never says whether a later walk overwrites or
    leaves it, so a citation in document B can resolve to document A's block — silently
    returning the wrong provenance, the exact 'worse than unresolvable' failure §2.1
    invokes to justify the unique index. §4's 'One image, one row, two chunks' covers
    chunker splits only, not the same bytes in two blocks. No invariant requires the
    stored block_id to belong to the document the citing chunk came from.
  status: accepted
  disposition_reason: 'Real: byte-keyed storage means the same image in two blocks
    is one row with one reference, and the fill is first-walk-wins. Recorded as a
    limit in §4 with what a surface may and may not claim, and the per-occurrence
    alternative is priced in §7 rather than taken — it means re-reading the same image
    once per block, which is the cost ADR-0010 §5 exists to avoid.'
- issue_id: I-002
  category: untestable-requirement
  severity: high
  description: §5.5's round trip — the test the SPEC calls load-bearing — runs against
    a stub fetcher, and nothing requires the stub to be keyed by the returned block_id/source_uri,
    nor is there a negative control asserting that a wrong or empty reference fails
    to produce the bytes. A stub that returns the fixture image regardless of the
    reference passes this test with a corrupt reference stored. As written the assertion
    'bytes hash to the same image_sha256' can be satisfied without the reference being
    used at all; the only evidence that references actually resolve is §6.1's 3 hand-run
    observations, which §6 explicitly excludes from the test suite.
  status: accepted
  disposition_reason: Correct that the round trip could pass without the reference
    being used. §5.12 now requires two distinct images in the stub source plus a mangled-handle
    negative control, so the assertion depends on selection rather than on there being
    one fixture.
- issue_id: I-003
  category: missing-invariant
  severity: high
  description: §2.1's unique index converts a 16-hex prefix collision from a resolution
    problem into an *ingest* failure, and no behaviour is defined for it. §2.2 defines
    only the read side (AmbiguousHandle) and §5.8 asserts only that the constraint
    rejects the second row. What happens to the second image's extraction — insert
    error propagates and aborts the whole walk, or is swallowed and the reading lost
    — is unspecified, as is whether the handle then widens. Given §2.4 also makes
    the save path *refuse* rows, the save path now has two distinct hard-failure modes
    with no stated disposition.
  status: accepted
  disposition_reason: 'Worse than described: ON CONFLICT DO NOTHING carries no conflict
    target, so it absorbs the index violation, no row is written, and the chunk''s
    handle then resolves to the other image — the wrong-provenance outcome the index
    exists to prevent, arriving through the index. §2.7 makes it raise; §5.13 tests
    it. Improbable is not handled.'
- issue_id: I-004
  category: adr-contradiction
  severity: high
  description: resolve_source() takes chunk_text and parses the marker out of it,
    but ADR-0010 §4 requires provenance to survive six hops including the snippet,
    the citation, the API response and MCP results, and ADR-0010 §1 records a snippet-boundary
    limit that already truncated content in the prompt. A reader (or agent) holding
    a rendered citation holds a snippet, not chunk_text, and the marker sits on the
    block's first line (§4) — so the reference is unreachable at precisely the surface
    §1 says the SPEC exists to serve. §5 contains no per-hop test that the handle
    survives search hit → evidence packet → citation → API/MCP, which ADR-0010 §4
    makes a conformance condition.
  status: accepted
  disposition_reason: A citation renders a snippet, and ADR-0010 §1 already records
    snippet truncation — the marker is on the block's first line, exactly what a truncating
    renderer drops. §2.2 now specifies resolve_chunk(tenant, chunk_rid) so a surface
    carries the rid it already has instead of the marker through six hops; §5.14 tests
    it. Building the affordance stays out of scope, being able to call it does not.
- issue_id: I-005
  category: risky-assumption
  severity: high
  description: §2.4 makes an empty block_id a hard refusal on the save path, justified
    by 'the walk always has it'. block_id is explicitly a Notion-shaped identifier
    (§2.1), while ADR-0010 §Open items records that the corpus has several intake
    paths (ingest-notion, ingest_external_spec, filesystem docs). Any image arriving
    from a non-Notion path has no block id, so this rule silently converts 'no reference'
    into 'no extraction at all' for those sources — content loss chosen by a rule
    whose premise is only true of one connector. Neither an alternative reference
    form nor an exemption is defined.
  status: accepted
  disposition_reason: The rule is written against one connector's identifier shape.
    Today only ingest-notion produces images, so nothing is losing content, but the
    refusal is stated in §4 as being on 'no reference at all' rather than on a Notion
    id, and the trade a future connector would face is named there instead of being
    inherited silently.
- issue_id: I-006
  category: adr-contradiction
  severity: medium
  description: §2.5 concedes the marker embeds extractor=<model>/<prompt_sha>, which
    ADR-0010 §5 *requires* to change on every extractor migration (and which changed
    twice on 2026-08-11). Because the marker lives in the hashed body, every future
    extractor migration rewrites content_hash for every image-bearing document and
    adds a doc_reingest_events row per document — a recurring perturbation of ADR-0006
    entropy signal ①. §2.3 budgets this as a one-time cost ('changes once for the
    five documents') and §7's mitigation records only this run's timestamp and five
    rids, leaving the recurring case unaddressed.
  status: accepted
  disposition_reason: 'The cost recurs: extractor=<model>/<prompt_sha> was already
    in the marker and ADR-0010 §5 requires it to change on every reader swap, so every
    swap rewrites every image-bearing document. §2.3 no longer claims it is paid once.
    Note this predates the SPEC and img= neither causes nor worsens it; the ADR-0006
    signal ① item in §7 already covers the mitigation.'
- issue_id: I-007
  category: missing-invariant
  severity: medium
  description: '§5.11 states the counter exists to answer ''can a reader holding a
    citation get back to the image?'', yet §5.9 fixes the population as extraction
    rows, explicitly not chunks. Chunks are where the failure lives: a pre-migration
    marker with no img= (§2.2), a marker naming an identity whose rows were pruned,
    or a fragment that lost its handle (the §4 defect) are all unresolvable citations
    that the row-based counter reports as zero. §5.11''s supporting claim — ''every
    active machine_read chunk carries the current identity in its marker, so no citation
    points at a retired row'' — is a point-in-time observation with no enforcing invariant;
    a future identity migration that does not rewrite chunk text breaks it, and the
    counter is blind by construction.'
  status: accepted
  disposition_reason: The strongest issue in the round. The counter names citations
    but counts rows, and the three ways a citation goes unresolvable — no img=, pruned
    identity, lost fragment handle — are all invisible to the row leg. The supporting
    claim that every active chunk carries the current identity was a point-in-time
    observation with nothing enforcing it. §5.11 adds the chunk leg and §5.15 tests
    that the two legs disagree.
- issue_id: I-008
  category: undefined
  severity: medium
  description: §5.11 splits the counter into 'the current reader's rows' (warn) and
    retired ones (plain line), but 'current' is never defined. Whether it is read
    from configuration, from the most recently written row, or from a declared identity
    record determines the output, and a deployment running a different configured
    extractor would flip 44 rows between the alarm line and the quiet line with no
    state change. §2.6's 'stated end state' for retired rows depends entirely on this
    undefined predicate.
  status: accepted
  disposition_reason: '''Current'' is vision.extractor_identity() — deployment state,
    not a stored fact. §5.11 says so, and says that rows moving between the two lines
    on a configuration change is the intended reading rather than a bug: the question
    the counter answers is whether this deployment''s readings can be traced.'
- issue_id: I-009
  category: undefined
  severity: medium
  description: '§2.3 requires the counter to treat the four chunk-less empty extractions
    as ''unresolvable-by-design rather than as a defect'', but §5.9 and §5.11 define
    the counter''s only partition as extractor identity — there is no has-a-chunk
    dimension, so the requirement cannot be met by the specified counter. The same
    split is inconsistent across the document: §6 excludes the four from acceptance
    (''counted separately''), while §6.1 reports 44/44 with the four included.'
  status: accepted
  disposition_reason: 'The inconsistency was real and the resolution is that the premise
    was wrong: the four empty extractions are written on the fetch path, which holds
    the block id whether or not the reader returned text, so they carry references
    like everything else. §2.3 withdraws ''unresolvable-by-design'' and §6 no longer
    excludes them — measured 44/44 including those four.'
- issue_id: I-010
  category: unverifiable-claim
  severity: medium
  description: §2.3 presents a reconciled census — 44 images → 44 rows → 40 machine_read
    chunks 'each carrying exactly one marker', gap explained by 4 empty extractions
    — but §4 and §6.1 report 41 active machine_read chunks because one block splits
    and the chunker now re-emits the marker on each fragment. The arithmetic that
    §2.3 offers as the corrected, direct measurement no longer closes, and the 44
    images → 44 rows leg additionally assumes a bijection that byte-keyed storage
    does not guarantee (identical bytes dedupe to one row).
  status: accepted
  disposition_reason: 'The arithmetic did not close. Corrected in §2.3 with both gaps
    stated: 44 rows − 4 empty + 1 split fragment = 41 active machine_read chunks.
    The earlier 40 counted before the split fix and did not separate active from superseded
    chunks. The 44→44 leg is also no longer presented as a bijection (§4).'
- issue_id: I-011
  category: missing-invariant
  severity: medium
  description: §2.1 argues uniqueness must be 'enforced, not measured' and puts it
    in the database, but the companion invariant — new rows must carry a reference
    (§2.4) — is enforced only in the save path, while the schema is TEXT NOT NULL
    DEFAULT ''. Any other writer (migration, backfill script, repair path, a second
    save site added later) can store an unresolvable row, and the tier's precondition
    rots in exactly the way §2.4 warns about. No CHECK constraint or partial index
    conditioned on the current identity is specified, and §5.2 tests only the one
    application path.
  status: deferred
  disposition_reason: 'The invariant is ''rows of the current identity carry a reference'',
    and ''current'' is deployment state (§5.11) — a CHECK or partial index would have
    to freeze today''s identity string into DDL and would reject the retired rows
    §2.6 deliberately keeps. There is exactly one writer today. Recorded in §7 with
    its trigger: a second writer to vision_extractions. The compensating detector
    is the counter, which is why I-007''s chunk leg matters.'
- issue_id: I-012
  category: undefined
  severity: low
  description: 'The return contract of resolve_source() is three-valued — None, Unresolvable(reason),
    and a raised AmbiguousHandle — but Unresolvable is never defined as a type (sentinel,
    dataclass, exception-not-raised), its reason strings are not declared as stable
    or matchable, and §5.6 asserts against the table without a stated equality contract.
    The prose also contradicts itself: ''none of them is a silent None'' immediately
    precedes a row that returns exactly None.'
  status: accepted
  disposition_reason: 'The prose contradicted itself one line apart. §2.2 now says
    the outcomes are distinguishable rather than ''none is a None'', names None as
    one of them, and states the contract: Unresolvable is a frozen dataclass whose
    reason strings are diagnostic, matched by tests, and not for any surface to parse.'
- issue_id: I-013
  category: missing-invariant
  severity: low
  description: '§2.5 pins the marker grammar between two components, build_block()
    (writer) and resolve_source() (parser), but §4''s fix makes the chunker a third
    participant: it must recognise a vision block and re-emit the marker on every
    fragment. That component is outside the grammar contract and outside §5''s writer-produces/parser-reads
    pinning test, so a grammar change can silently break fragment re-emission — reintroducing
    the handle-less-fragment defect §4 was written to close.'
  status: accepted
  disposition_reason: The chunker became a third participant in the grammar when §4's
    fix made it re-emit the marker per fragment. §2.5 says so, and §5.7 is the pinning
    test for that edge because it runs writer → chunker → parser rather than writer
    → parser.
- issue_id: I-014
  category: unverifiable-claim
  severity: low
  description: 'The acceptance evidence in §6.1 that CI cannot reproduce is self-reported
    and unartifacted: 3/3 hand round trips (from 41 candidate chunks, sample size
    unstated as a rationale), and §4''s ''fixed for the CLI on 2026-08-11'' with no
    reference to the change. §6 explicitly records the hand run as ''a one-off observation,
    not as a test'', which makes the SPEC''s central promise rest permanently on an
    observation nothing re-checks.'
  status: accepted
  disposition_reason: 'Partly: the hand run is re-runnable rather than anecdotal,
    and §6.1 now names scripts/vision_roundtrip_probe.py and says it takes any N and
    exits non-zero on failure. It stays out of CI for the reason §5 already gives
    — live Notion access, a valid per-root token and an unexpired URL are three things
    §4 says can vanish, and a test that goes red for those reasons teaches the suite
    to be ignored.'
approved_by: LivingLikeKrillin
approved_at: '2026-08-11T15:04:38Z'
---

