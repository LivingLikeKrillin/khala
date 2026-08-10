---
target: SPEC-nexus-screenshot-text-extraction
critiqued_hash: sha256:f2aa234b3836ebce28d2bcb70053d9ac6d2dd1e22351820795a84be8daeb4abc
critiqued_at: '2026-08-10T09:09:26Z'
issues:
- issue_id: I-001
  category: missing-invariant
  severity: high
  description: §4.4 specifies `ON CONFLICT DO NOTHING` for the durable write but never
    says what the losing writer does with its own extraction. Two concurrent ingests
    of the same byte-identical image both miss the store, both run the non-deterministic
    reader, and both get different text; the first insert wins the row, but the second
    ingest goes on to assemble §4.3's marker block from *its own* text and writes
    it into the document body. The stored row and the served chunk then disagree under
    the same `extractor_identity`, which is exactly the drift ADR-0010 §5 forbids
    ('stored text for unchanged bytes never changes'), and it is invisible because
    the identity did not move. The spec needs a read-back-after-conflict rule (INSERT
    ... ON CONFLICT DO NOTHING RETURNING, then re-SELECT and use the winner's text)
    and a test.
  status: accepted
  disposition_reason: Fixed in text. ON CONFLICT DO NOTHING left the losing writer's
    behaviour unstated; it discards its own extraction and reads the stored row back,
    so content_hash cannot depend on which process won a race.
- issue_id: I-002
  category: missing-invariant
  severity: high
  description: '§4.4''s cache and §7.2.9''s failure rows are keyed by `image_sha256`,
    which can only be computed after a successful fetch — so a *fetch* failure has
    no key and cannot be recorded or resolved. §4.1 concedes the URL is presigned
    with a one-hour expiry. Scenario: first ingest extracts 44 images and writes the
    blocks into the body; a later re-ingest hits an expired/500 URL for image 7, cannot
    compute its hash, cannot look up the stored extraction, and emits a bare `![]()`.
    The body loses a vision block, `content_hash` flips, the document reads as edited
    when nothing was edited, ADR-0006''s signal ② is poisoned, and the whole document
    re-embeds. §7.2.9 explicitly claims failure rows prevent precisely this (''fetch
    failure and extraction failure alike''), but the schema''s primary key makes that
    impossible for the fetch case.'
  status: accepted
  disposition_reason: Fixed in code and now in text. A fetch failure has no bytes
    and so no key, and that is the most likely failure since the URL expires within
    the hour. The key derives deterministically from the block id with an 'unfetched:'
    prefix so no reader mistakes it for a content hash.
- issue_id: I-003
  category: missing-invariant
  severity: high
  description: '§4.3 makes the chunker split at `<!-- khala:vision:begin/end -->`
    *unconditionally* and derive the tier from those markers, but the authored-side
    stripping is specified only ''at convert time'' and §6''s ships list touches only
    `notion_convert.py`. Nexus has other intake paths (ADR-0006 names `ingest_external_spec`
    and filesystem docs; ADR-0004 adds Arbiter''s `promote_external`). Scenario: an
    external spec or filesystem markdown file whose body contains `<!-- khala:vision:begin
    -->` is ingested through a non-Notion path, reaches the shared chunker unstripped,
    and its authored prose is split off and tiered `machine_read` — the defamation
    §4.3 says it exists to prevent, and a tier-forgery primitive available to anyone
    who can get a document ingested. §7.2.15 as written would pass while the hole
    stays open.'
  status: accepted
  disposition_reason: Fixed in code and now in text. Stripping authored markers only
    in the Notion converter left filesystem docs and external-spec payloads able to
    have their author's prose tiered machine_read. The chunker now distrusts markers
    by default; only a caller that wrote the block declares trust.
- issue_id: I-004
  category: risky-assumption
  severity: high
  description: 'ADR-0010 records the ADR-0002 demand-pull gate as fired on the strength
    of one specific observation: ''a real question was asked, the answer was unavailable,
    and the cause was counted (44 images…)''. §7.1''s step 0 falsified the causal
    half of that — no unlock condition or point value appears in any of the eleven
    images, and every `포인트` match in the corpus is `엔드포인트`, so the answer was unavailable
    because the organisation never wrote the rule down. The SPEC swaps in a new acceptance
    question (§7.1a) but never revisits whether the gate itself still holds. The one
    measured instance of ''policy trapped in pixels'' evaporated, and the remaining
    justification is the un-sampled inference over the other four documents that ADR-0010''s
    Generalisation limit explicitly refuses to state as fact. Under ADR-0002''s own
    rule the gate should be re-declared on surviving evidence, or the build re-justified,
    before code ships.'
  status: accepted
  disposition_reason: Accepted, and it is the most important finding of the round.
    ADR-0010's gate was declared fired partly on 'the cause was counted', and step
    0 shows the cause of that specific failure was not the images. §7.1a-0 records
    the falsification, states what survives (44 images carrying spec tables absent
    from all corpus text, confirmed by opening five), and notes the ADR is hash-stamped
    so a successor note is owed rather than an edit.
- issue_id: I-005
  category: adr-contradiction
  severity: medium
  description: '§3.1 says the per-ingest ceiling is enforced by leaving remaining
    images ''unextracted and recorded as failure rows, so the run is repeatable'',
    while §7.2.9 declares failure rows ''sticky by design'' — an image with a failure
    row stays unextracted ''until a human deletes the row''. These cannot both hold.
    Scenario: a tenant with 250 images ingests; images 101–250 get failure rows; the
    second run extracts none of them because their rows already exist, and a human
    must hand-delete 150 rows to make progress. The run is not repeatable, and the
    ceiling silently becomes a permanent cap. One of the two behaviours (ceiling-skip
    rows must be non-sticky, or the ceiling must not write rows at all) needs to be
    chosen and tested; today neither the ceiling nor the stickiness has a test in
    §7.2.'
  status: accepted
  disposition_reason: Accepted; addressed together with the round's other corrections
    at implementation, and recorded in the SPEC where it changes what ships.
- issue_id: I-006
  category: missing-invariant
  severity: medium
  description: '§3.1 requires `stop_reason` and per-extraction token counts to be
    recorded on the durable row, but §4.4''s schema is `vision_extractions(tenant,
    image_sha256, extractor_identity, text, error, truncated, at)` — no `stop_reason`,
    no token columns — and §6''s migration line repeats only the PK. The spec''s own
    argument (''§3.1 criticised the sufficiency signal for shipping without a spend
    instrument and an earlier draft of this SPEC then did the same'') is defeated
    by its own schema: after the first run there is no way to answer ''what did it
    cost'', and `max_tokens` truncation is detectable only through the `truncated`
    boolean, losing the distinction between the token cap and the 20,000-character
    cap that §3.1 spent a paragraph separating.'
  status: accepted
  disposition_reason: Accepted; addressed together with the round's other corrections
    at implementation, and recorded in the SPEC where it changes what ships.
- issue_id: I-007
  category: missing-invariant
  severity: medium
  description: '§3.1 says a truncated extraction ''marks the chunk'', but the only
    truncation field defined anywhere is `vision_extractions.truncated` (§4.4), and
    §4.5''s six hops carry `provenance_tier`, `extractor_identity` and `source_ref`
    — not truncation. Scenario: the reader hits `max_tokens` mid-table; the block
    is stored with `truncated=true`; the chunk, the SearchHit, the evidence packet,
    the prompt, the citation, the API response and the MCP result all show a `machine_read`
    chunk that looks complete. That is verbatim the failure §3.1 introduced the flag
    to stop (''A half-transcribed spec table would have travelled all six hops looking
    complete''), just relocated from the reader to the transport. Either truncation
    joins the travelling fields or the claim in §3.1 must be withdrawn.'
  status: accepted
  disposition_reason: Accepted; addressed together with the round's other corrections
    at implementation, and recorded in the SPEC where it changes what ships.
- issue_id: I-008
  category: adr-contradiction
  severity: medium
  description: '§4.4 introduces deletion as ''the one named exception'' to the stored-text
    invariant and states plainly that it is ''a narrowing this SPEC makes, not something
    ADR-0010 §5 already allowed''. ADR-0010''s own Status paragraph exists because
    a SPEC was told, correctly, that ''a SPEC cannot amend an ADR'', and §5 states
    the invariant with no exception. The reasoning for the exception may well be right,
    but the vehicle is wrong: this is an ADR-0010 amendment being made in a SPEC.
    It should be an accepted edit to ADR-0010 §5 (or a superseding ADR) before implementation,
    not a paragraph in the design that depends on it.'
  status: accepted
  disposition_reason: Accepted; addressed together with the round's other corrections
    at implementation, and recorded in the SPEC where it changes what ships.
- issue_id: I-009
  category: missing-invariant
  severity: medium
  description: '§4.4 orders the scanner before the durable write so that only passing
    text is stored — but nothing is recorded when text *fails* the gate. Scenario:
    an image containing a work email address (§4.6 says one exists in the examined
    corpus) is extracted, quarantined, and not stored. Every subsequent ingest of
    that document misses the store, re-runs a non-deterministic reader on the same
    bytes, and produces a slightly different extraction; whether the body ends up
    with a block, a bare placeholder, or differently-worded quarantined text is unspecified,
    so `content_hash` may churn on every ingest and the paid extraction is re-paid
    every run. The design needs a gated-outcome marker row (distinct from the §4.4
    rows that hold servable text) with a defined body representation, or §3.1''s ''a
    re-ingest of unchanged documents extracts nothing'' is false for exactly the documents
    the gate touches.'
  status: accepted
  disposition_reason: Accepted; addressed together with the round's other corrections
    at implementation, and recorded in the SPEC where it changes what ships.
- issue_id: I-010
  category: unverifiable-claim
  severity: medium
  description: §7.1's step 0b requires a re-fetch demonstrated 'from a stored `source_ref`
    alone for at least one image per document' — five documents. §7.1b declares step
    0b passed on eleven images of a single document (the avatar-policy one), from
    'its stored block id alone', and §4.3 defines `source_ref` as source URI + block
    id + byte hash while §8 concedes `canonical_uri` is basename-only. So the demonstration
    covered one fifth of the required scope, used the block id rather than the `source_ref`
    the criterion names, and ran against a store that does not exist yet. §7.1b's
    headline ('Step 0b passed, so the recourse is real') overstates what was run;
    per the criterion's own terms extraction cannot ship on this evidence.
  status: accepted
  disposition_reason: Accepted; addressed together with the round's other corrections
    at implementation, and recorded in the SPEC where it changes what ships.
- issue_id: I-011
  category: untestable-requirement
  severity: medium
  description: '§7.1''s fidelity bar is ''≥ 6 of 8 at pass or partial'' on §2''s scale,
    but that scale is written against one specific screenshot''s anatomy — `pass`
    requires ''screen id, version, the rule sentence, and both table attribute names'',
    `partial` requires ''rule sentence and table attributes''. §7.1 simultaneously
    drops any requirement on what the sampled images contain (''No requirement about
    what the images contain''). An image with no version strip, no rule sentence,
    or no attribute table cannot be scored `pass` or `partial` at all, and by construction
    scores `fail`. Scenario: four of the eight drawn images are UI-state screens without
    a rule box; the sample fails on 5/8 for reasons unrelated to transcription fidelity.
    The scale needs a per-image ''what this image contains'' step recorded by the
    director before scoring, or an explicit N/A disposition.'
  status: accepted
  disposition_reason: Accepted; addressed together with the round's other corrections
    at implementation, and recorded in the SPEC where it changes what ships.
- issue_id: I-012
  category: undefined
  severity: medium
  description: '§7.1''s invention rule is ''one non-trivial line of extracted text
    that does not appear in the image'', but the operational comparison is against
    the director''s recorded reading, not against the image. The adjudication procedure
    for the gap between the two is undefined. Scenario: the machine reads the small
    grey header strip that §2 records both local models losing and that a human transcribing
    under time pressure may also skip; the line is non-trivial (carries an ID and
    a version), does not appear in the recorded reference, and by the letter of the
    rule fails the sample outright and blocks the ship — punishing the reader for
    reading better than the reference. The spec fixes a tie-break for triviality but
    not for presence; it needs one (e.g. re-open the image on any disputed line, and
    score invention only against the pixels).'
  status: accepted
  disposition_reason: Accepted; addressed together with the round's other corrections
    at implementation, and recorded in the SPEC where it changes what ships.
- issue_id: I-013
  category: undefined
  severity: medium
  description: 'ADR-0010 §3.1 requires three durable fields per chunk, and §6''s migration
    line is ''tier + extractor identity + source ref; backfill authored'' — but the
    SPEC never states nullability, the enum type, or what `extractor_identity` and
    `source_ref` hold for `authored` chunks, which are the overwhelming majority (289
    of 289 today). ADR-0010 §3 fixes only `provenance_tier` as NOT NULL enum. Scenario:
    the migration is written with all three NOT NULL and the backfill of 289 authored
    chunks needs an `extractor_identity` value it cannot have; or all three are nullable
    and §7.2.7''s six-hop assertions have no defined behaviour for a null tier arriving
    from an older row. §7.2.10 tests only that a pre-ADR chunk reads `authored`.'
  status: accepted
  disposition_reason: Accepted; addressed together with the round's other corrections
    at implementation, and recorded in the SPEC where it changes what ships.
- issue_id: I-014
  category: risky-assumption
  severity: medium
  description: '§7.1a''s acceptance question (''Ava_01 화면에서 NFT 크기/위치 조정 범위'') requires
    retrieval to find the machine_read chunk, but §8 concedes ADR-0010 §3''s separate-chunk
    rule strips the 100–171 characters of authored heading that name what the image
    depicts, and calls a context prefix ''unmeasured''. The query''s discriminating
    token is `Ava_01`, which most plausibly lives in the authored heading, not in
    the extracted 속성 table. Scenario: extraction works perfectly, the table text is
    stored and tiered correctly, and the acceptance query still fails because the
    chunk carrying `1/2` and `마스킹` has nothing in it that matches `Ava_01`. The sole
    ship criterion would then be failed by a referent problem the SPEC has already
    identified and deferred, and the failure would be indistinguishable from an extraction
    failure.'
  status: accepted
  disposition_reason: Accepted; addressed together with the round's other corrections
    at implementation, and recorded in the SPEC where it changes what ships.
- issue_id: I-015
  category: untestable-requirement
  severity: medium
  description: §3.1 makes four limits load-bearing and closes with 'A limit nothing
    enforces is worse than no limit… the per-ingest ceiling was defined and never
    wired' — yet §7.2's sixteen tests cover none of the four. There is no test that
    `max_tokens` truncation sets the flag, none that the 20,000-character cap marks
    rather than silently shortens, none that `NEXUS_VISION_MAX_PER_INGEST` stops at
    the ceiling, and none that token counts are recorded. By this SPEC's own standard
    those are limits nothing enforces, in a document whose §7.2 preamble insists controls
    that cannot run in CI 'would not exist'.
  status: accepted
  disposition_reason: Accepted; addressed together with the round's other corrections
    at implementation, and recorded in the SPEC where it changes what ships.
- issue_id: I-016
  category: unverifiable-claim
  severity: low
  description: '§7.2.5 (''an injected instruction inside the image becomes content,
    not direction'') is run against a reader stubbed at the `LLMService` boundary,
    so the stub returns the injected string because the test author made it do so,
    and the ''next request unchanged'' assertion holds because no model is in the
    loop. §7.2.2 carefully disclaims exactly this limitation for transcription (''This
    does not establish no-invention… its name must not suggest it does'') but §7.2.5
    carries no equivalent disclaimer, and §4.2''s structural argument (no tool definitions
    in the payload, asserted by §7.2.3) is what actually carries the property. #5
    should be renamed to what it proves — that the pipeline does not branch on extracted
    content — or the injection claim will read as tested when it is not.'
  status: accepted
  disposition_reason: Accepted; addressed together with the round's other corrections
    at implementation, and recorded in the SPEC where it changes what ships.
- issue_id: I-017
  category: scope-creep
  severity: low
  description: §4.3's authored-side stripping mutates authored document bodies for
    every ingested document, including the 111 that carry no images, and since the
    body feeds `content_hash` it can flip the hash of documents this feature is not
    otherwise touching. No ADR authorises Nexus to rewrite authored text, and the
    trigger string is a khala-internal marker no author would knowingly type. The
    blast radius is small in practice but the rule as written is unbounded ('stripped
    from authored body text at convert time as well'); it should be scoped to the
    marker's exact literal form, applied at every intake path (see the notion_convert-only
    gap), and its effect on `content_hash` for previously-ingested documents stated.
  status: accepted
  disposition_reason: Accepted; addressed together with the round's other corrections
    at implementation, and recorded in the SPEC where it changes what ships.
approved_by: LivingLikeKrillin
approved_at: '2026-08-10T09:10:36Z'
---

