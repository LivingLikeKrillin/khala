---
target: SPEC-nexus-screenshot-text-extraction
critiqued_hash: sha256:b2649c29211ff9dde23ee9992fd6faf5c1ad2a47a93bdd22966b2c7efa1edb4e
critiqued_at: '2026-08-10T05:34:50Z'
issues:
- issue_id: I-001
  category: adr-contradiction
  severity: high
  description: §4.4's quarantine exception breaks the very invariant it claims to
    preserve. It asserts deletion "removes rather than rewrites, so no drifted text
    can appear under an unchanged identity" — but after the row is deleted, the next
    ingest of the same bytes finds no stored result, re-runs a non-deterministic reader,
    and stores *new* text under an *unchanged* extractor_identity. That is exactly
    the failure ADR-0010 §5 names ("a miss re-runs a non-deterministic reader, and
    drifted text lands under an unchanged extractor identity — invisible because the
    identity did not move"). Worse, since the reader is non-deterministic, the re-extraction
    may not trip the scanner the second time, so quarantined PII can land in the index
    on a later ingest of unchanged bytes. Also breaks §4.3's content_hash safety argument,
    which is explicitly conditioned on "unchanged bytes under an unchanged extractor
    never produce different text".
  status: accepted
  disposition_reason: Right that deletion is not free. The invariant's purpose is
    that stored text is never silently replaced by drifted text under an unchanged
    identity; deletion removes the row rather than rewriting it, and the next ingest
    re-extracts and is re-quarantined by the same gate — so no drifted text can be
    served as if it were the original. Implementation states this as the single named
    exception, with the quarantine test asserting the row is absent afterwards. Leaving
    quarantined PII in an unreachable durable store was the worse option.
- issue_id: I-002
  category: missing-invariant
  severity: high
  description: §4.3 claims marker sanitisation in "both directions", but the chunker
    splits at the markers "unconditionally" for every document while §6's Ships list
    places marker stripping only in `ingest/sources/notion_convert.py`. Documents
    entering by any other intake path named in ADR-0004 §4 and ADR-0010 Open items
    — `ingest_external_spec`, governed-frontmatter filesystem docs, direct injection
    — are never stripped, so authored prose containing `<!-- khala:vision:begin -->`
    is tiered `machine_read` (or, with a stray end marker, laundered `authored`) on
    those paths. §7.2.15 tests only the converter path, so the gap is invisible to
    CI.
  status: accepted
  disposition_reason: 'Ordering must be explicit: authored markers are stripped at
    convert time, before the converter writes any vision block, and the chunker''s
    unconditional split therefore only ever sees converter-written markers. Implementation
    fixes the order in one place and asserts it.'
- issue_id: I-003
  category: missing-invariant
  severity: high
  description: Fetch failure is unhandled and defeats §7.2.14. §4.1 requires bytes
    to be fetched during the walk (presigned, one-hour expiry) and §4.4 keys the store
    on `image_sha256`, which cannot be computed without the bytes. So on every re-ingest
    the fetch must succeed just to reach the cache. §7.2.9 covers *extraction* failure
    with a failure row keyed on (tenant, bytes, identity) — a key that is unavailable
    when the *fetch* is what failed. A transient 403/expiry therefore yields a bare
    `![]()` body, flips `content_hash`, and makes an untouched document read as edited
    — the churn ADR-0010 §5 exists to prevent.
  status: accepted
  disposition_reason: Fetch failure and extraction failure are different and only
    the second was handled. Both record a failure row for (tenant, bytes, identity)
    — a presigned URL that expired mid-walk must not produce a body that silently
    differs from the next successful ingest. Implementation covers the fetch path
    with the same test.
- issue_id: I-004
  category: untestable-requirement
  severity: high
  description: §7.2 stubs the reader at the `LLMService` boundary, and §7.2.2 ("Nothing
    is invented — every non-trivial extracted line appears in the fixture's recorded
    contents") then asserts a property of the stub's canned output, not of the shipped
    reader. The no-invention property is the SPEC's load-bearing control (§7.1 zero
    tolerance, ADR-0010 §2's central failure mode) and has no automated test at all.
    §7.1 concedes the n=1 measurement does not transfer to the shipped path, leaving
    the property covered only by a one-time 8-image manual gate.
  status: accepted
  disposition_reason: 'Correct and important: a stubbed reader cannot demonstrate
    no-invention — that test proves the pipeline transcribes what the reader returned,
    nothing more. No-invention is established only by §7.1''s human-read sample against
    the shipped transport. The CI test''s name and docstring must say what it does
    and does not prove, or it reads as a guarantee it cannot give.'
- issue_id: I-005
  category: missing-invariant
  severity: high
  description: 'The cross-tenant boundary in §4.4 is stated but untested, and the
    section contradicts itself on the key: the heading and first line say the key
    is `(image_sha256, extractor_identity)`, the body says the primary key is the
    triple including `tenant`. §7.2.8 tests only "same bytes under a new identity
    re-extract; same bytes under the same identity never do" — no test asserts that
    tenant B''s ingest of byte-identical bytes does not resolve tenant A''s row, which
    is the scenario §4.4 says would serve text "that the first tenant''s quarantine
    gate rejected".'
  status: accepted
  disposition_reason: 'Mechanical inconsistency after adding tenant: the prose still
    calls the primary key a pair in one place. Key is (tenant, image_sha256, extractor_identity)
    throughout, and the cross-tenant boundary gets its own test — two tenants ingesting
    byte-identical images extract twice and never read each other''s rows.'
- issue_id: I-006
  category: risky-assumption
  severity: medium
  description: '§7.1''s "the tier is the containment" is required rather than recommended,
    yet it rests on consumer behaviour that ADR-0010 §3.1 explicitly says cannot be
    enforced: "a consumer that receives the tier and discards it has made its own
    choice, and that is the honest limit of what this decision can promise." For the
    36 unread images the SPEC''s only guarantee against invention is a label whose
    effect on any reader — human or agent — is unmeasured and unenforceable.'
  status: accepted
  disposition_reason: '''The tier is the containment'' does rest on consumers honouring
    a label, which ADR-0010 concedes Nexus cannot force (ADR-0001''s boundary). What
    Nexus owes is that all six hops carry it; what a consumer does with it is the
    consumer''s. Restated as the honest limit rather than as containment.'
- issue_id: I-007
  category: missing-invariant
  severity: medium
  description: Ordering between the durable write and the quarantine gate is unspecified.
    §4.4 stores extracted text in `vision_extractions` (no eviction) at extraction
    time; §4.6 sends it through the scanner later, at chunking/pipeline time. Nothing
    states the store write is transactional with, or subsequent to, the gate. An ingest
    that crashes, is killed, or aborts between the two leaves unscanned PII sitting
    in a durable, no-eviction table whose only deletion trigger (§7.2.16) is a quarantine
    event that never fires.
  status: accepted
  disposition_reason: 'Ordering between the durable write and the quarantine gate
    is load-bearing and unstated. The gate runs first: text is scanned before it is
    stored, so quarantined content never reaches vision_extractions and I-001''s deletion
    path is a backstop for content quarantined later, not the primary control.'
- issue_id: I-008
  category: untestable-requirement
  severity: medium
  description: 'Step 0b demonstrates a re-fetch "from a stored `source_ref` alone"
    once, for one image per document, before commit — but ADR-0010 §3.1 requires re-resolvability
    as a durable property ("without a reference that can be re-resolved at the source,
    the lower tier is a label with nothing behind it"). A one-time demonstration cannot
    establish it: §8 concedes Notion URLs expire within the hour and `canonical_uri`
    is basename-only, and blocks can be moved or deleted after commit. No test in
    §7.2 covers source_ref resolution, so the property is never checked again after
    the gate.'
  status: accepted
  disposition_reason: 'One re-fetch per document proves the reference resolves today,
    not that it resolves for the life of the chunk — which is what ADR-0010 §2''s
    recourse actually promises. The gate stays (it is the cheapest way to falsify
    the design early) and the residual is recorded in Open items: durable recourse
    depends on the source system keeping the block, which Nexus does not control.'
- issue_id: I-009
  category: scope-creep
  severity: medium
  description: §6's Ships list (4 files) does not cover the work §4.5 and §7.2.7 require.
    The six hops touch the chunker (§4.3's unconditional marker split), `SearchHit`,
    the evidence-packet builder, the citation constructor, `/search` and `/search/answer`
    responses, the web client, and the MCP server — none of which appear. Either the
    change set is materially larger than scoped or the six-hop conformance ADR-0010
    §4 makes mandatory is unimplemented; the SPEC does not say which.
  status: accepted
  disposition_reason: 'The ships list understates the work: six hops touch the chunker,
    hybrid search, the evidence packet, citations, the API response and MCP. Implementation
    expands §6 to name every file it actually edits, since a ships list that omits
    half the change is how a hop gets dropped.'
- issue_id: I-010
  category: undefined
  severity: medium
  description: The scoring vocabulary of the acceptance gate is undefined. §7.1's
    zero-tolerance invention criterion turns on "one non-trivial line" (repeated in
    §7.2.2) with no definition of non-trivial. Separately, §2's table records scores
    as "3/5 partial" and "5/5 pass" — a five-point count — while §2's pre-registered
    scale is a three-value category (pass/partial/fail), and §7.1's "≥ 6 of 8 at pass
    or partial on §2's pre-registered scale" gives no mapping between the two. A pre-registered
    threshold that cannot be applied without post-hoc interpretation is not pre-registered.
  status: accepted
  disposition_reason: '''Non-trivial line'' carries the zero-invention gate and is
    undefined. It must be fixed before the sample is read, per the same pre-registration
    rule the gate itself is written under.'
- issue_id: I-011
  category: risky-assumption
  severity: medium
  description: §7.2.9's failure rows are sticky by design ("a retry is an explicit
    act — deleting the failure row"), so a single transient API timeout, rate limit,
    or 5xx permanently pins that image to unextracted until a human deletes a database
    row. No CLI, endpoint, owner, alerting, or operational procedure for that deletion
    is defined anywhere, and no distinction is drawn between retryable and terminal
    failures. The failure row also has undefined semantics in the schema — `vision_extractions.text`
    for a failure row is not specified as nullable or sentinel-valued.
  status: accepted
  disposition_reason: Sticky failure rows mean one transient fetch error leaves an
    image permanently unextracted until a human deletes the row. That is deliberate
    — the alternative is a body that changes whenever the network cooperates — but
    it needs to be visible rather than silent, so failure rows are counted and reported
    alongside the extraction count.
- issue_id: I-012
  category: adr-contradiction
  severity: medium
  description: '`vision_extractions` makes Nexus the system of record for text that
    cannot be re-derived, against ADR-0004''s placement of Nexus as "the index, not
    the store" (reaffirmed in ADR-0006''s constraint 1 and ADR-0010 §3.1). Because
    §4.4 forbids re-extraction under the same identity and the source bytes are not
    retained, the row is the only authoritative copy of that text; losing it cannot
    be a "performance event" as §4.4 claims, since re-population requires either a
    forbidden same-identity re-read or an identity bump that ADR-0010 §5 classes as
    a migration.'
  status: deferred
  disposition_reason: 'Genuine and unresolved: vision_extractions makes Nexus the
    only holder of text that cannot be re-derived, against ADR-0004''s ''index, not
    store''. The mitigations are partial — the source image remains at the source,
    and the extraction is reproducible only in the weak sense that a re-read may differ.
    Whether that crosses ADR-0004''s line, or needs its own successor record, is a
    decision above this SPEC and is deferred to the director with the tension stated
    rather than argued away.'
- issue_id: I-013
  category: undefined
  severity: medium
  description: No bound is placed on the reader's output or on cost. There is no max
    output token limit, no cap on extracted text length, and no per-document or per-tenant
    extraction budget — while §4.3 explicitly anticipates "a vision block larger than
    the chunk bound". An adversarial or pathological image can inflate one document
    into arbitrarily many `machine_read` chunks at unbounded paid cost, on bytes that
    by §4.6 are attacker-controllable and reach the reader ahead of the quarantine
    gate. §3.1's cost claim ("paid API credit, per image, once") carries no figure,
    so the decision has no verifiable cost basis.
  status: accepted
  disposition_reason: No output bound and no cost bound. A max output token limit
    per image, a cap on extracted characters, and a per-ingest ceiling on images extracted
    are added at implementation — the sufficiency signal shipped without a spend instrument
    and that was the right criticism there too.
- issue_id: I-014
  category: untestable-requirement
  severity: medium
  description: '§7''s headline acceptance — `nexus query "각 아바타별 해금 포인트 수치"` "returns
    the thresholds" — has no stated pass condition: how many avatars, which thresholds,
    and what counts as returned are all left to be settled by Step 0''s human survey
    after the fact, and the answer path is non-deterministic LLM generation. §7 asserts
    "nothing here counts as success until the §1 question is answered" while making
    the criterion self-voiding (§7.1: if the survey finds no image carrying thresholds,
    the criterion "is void and must be replaced"), so the gate can be satisfied or
    discharged by redefinition either way.'
  status: accepted
  disposition_reason: '''Returns the thresholds'' has no pass condition. It becomes
    a label in the Korean eval set with the expected values recorded from the human
    survey in step 0, scored by the existing deterministic harness — so the motivating
    question is judged by the same ruler as everything else rather than by reading
    the answer and nodding.'
- issue_id: I-015
  category: undefined
  severity: low
  description: '§3 pins `NEXUS_VISION_MODEL` to a literal default specifically to
    decouple the extractor''s lifecycle from `LLMService.DEFAULT_MODEL`, but then
    defines no lifecycle for it: no procedure or owner for model EOL, no behaviour
    when the pinned id is retired by the provider, and no statement of what happens
    to the 44 stored extractions at that point (a forced identity bump and mass re-read,
    per ADR-0010 §5, with no budget or trigger recorded). The decoupling argument
    identifies the problem and leaves the extractor''s own instance of it unanswered.'
  status: accepted
  disposition_reason: Pinning the vision model to its own literal decouples the lifecycles,
    and the cost is that its EOL is now a separate thing someone must remember. Recorded
    in Open items so the decoupling does not silently become an unmaintained default.
approved_by: LivingLikeKrillin
approved_at: '2026-08-10T05:52:47Z'
---

