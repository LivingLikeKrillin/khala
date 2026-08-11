---
target: SPEC-nexus-screenshot-text-extraction
critiqued_hash: sha256:adeaf706020bd586db7bed926b1bd357126081036445b52c0ec5e3b7d65e1427
critiqued_at: '2026-08-11T16:16:49Z'
issues:
- issue_id: I-001
  category: adr-contradiction
  severity: high
  description: 'ADR-0010 §7 makes it an invariant that "no extraction is committed
    before the tier exists" — §3''s field and all six §4 hops must be in place first.
    §7.3 records that extraction was run against the live tenant on 2026-08-10 and
    that four defects surfaced only then, the first being "the trust flag never reached
    the chunker (extraction laundered as authored)". That is hop 1 failing: machine-read
    text entered the live corpus tiered `authored`, which is precisely the outcome
    ADR-0010 §4 calls "worse than not extracting". The SPEC reports this as a discovery
    about testing rather than as a violation of the ADR invariant it is bound by,
    and states no remediation (were the mistiered chunks re-ingested? is there an
    assertion that no `authored` chunk in the live corpus originated from an image?).'
  status: accepted
  disposition_reason: 'Correct, and the SPEC understated it by filing a violated ADR-0010
    §7 invariant under ''defects found by running it''. §7.5 now names it as the violation
    it was, records the remediation (re-ingest), and replaces the assumption with
    a measurement: 0 active chunks are tiered authored while carrying a vision marker
    (2026-08-11). The mistiered rows are superseded, which is where the base filter
    leaves them.'
- issue_id: I-002
  category: risky-assumption
  severity: high
  description: §4.2 claims the three ADR-0010 §6 constraints are satisfied "structurally…
    a consequence of the transport rather than a rule someone must follow", but the
    default transport is the `claude-code` bridge, where no-tools is a CLI flag (`--allowed-tools
    ""`) interpreted by an authenticated host CLI that also loads host-side configuration
    — user/project settings, MCP servers, hooks, and system prompts the SPEC never
    constrains. On that path the reader is a full agent runtime with a restricting
    flag, not a request with no tool definitions. Since §4.6/ADR-0010 §6 place this
    reader *ahead* of the quarantine gate on attacker-controllable bytes, a host config
    that re-enables any tool reinstates exactly the file-exfiltration primitive §3
    withdrew the `--allowed-tools Read` design for. The SPEC needs an invariant on
    what the bridge may load, not just on what flags it passes.
  status: accepted
  disposition_reason: The strongest issue in the round. 'Structural' was true of the
    API request and false of the bridge, where the other end is an agent runtime and
    the properties are flags — sitting ahead of the quarantine gate on attacker-controllable
    bytes. §4.2 now states the bridge's own invariant, names the four flags, and points
    at the test that pins the argv rather than leaving it to intention. Note the reader
    of record has since moved off this transport (§7.5), so today's exposure is dev-only;
    the invariant still binds wherever the bridge runs.
- issue_id: I-003
  category: untestable-requirement
  severity: high
  description: §7.2.3/§7.2.4 assert "no tool definitions" and "exactly one image block"
    on the outgoing payload, but §7.2's preamble stubs the reader at the `LLMService`
    boundary so no test needs an authenticated CLI. That means the two primary security
    controls are asserted only against the API transport's request object, while the
    *default and actually-used* transport (§3.0, §7.3's live run) is the bridge, whose
    surface is process argv plus host CLI state and is never exercised. This is the
    same failure §7.2.3 congratulates itself for avoiding — a control whose test cannot
    reach the attack it targets.
  status: accepted
  disposition_reason: 'Partly already untrue and the SPEC failed to say so: tests/test_claude_llm_bridge.py
    fixes the doors-closed argv, which is the bridge''s actual surface. §4.2 now cites
    it. The stub-at-LLMService boundary stays for the reader tests — that is what
    keeps them runnable without an authenticated CLI — so the two surfaces are tested
    by two different means, which the SPEC now states instead of implying one covers
    both.'
- issue_id: I-004
  category: missing-invariant
  severity: high
  description: '§3.1 makes recording `stop_reason` a load-bearing control — it is
    the only thing that detects a table half-transcribed because the model ran out
    of output budget, and the SPEC narrates at length how the earlier 2048/8000 pairing
    made that truncation invisible. §3.0 then concedes the bridge does not provide
    `stop_reason` and `read_image` records it as unknown. The bridge is the default
    and is what produced all 44 live rows, so on the shipped path the control is permanently
    inert: a half-transcribed spec table travels all six hops marked `machine_read`
    and complete. No invariant is stated for what happens on an `unknown` stop_reason
    (is the extraction stored? marked? refused?), and no §7.2 test asserts truncation
    marking for either transport or the 20,000-character cap.'
  status: accepted
  disposition_reason: 'Real, and the fix is partly historical: the reader of record
    moved to Gemini REST, which returns finishReason, so the truncation control is
    live on the shipped path — 0 of 44 rows are marked truncated. §7.5 records that
    it was inert on the bridge that produced the first run, which is a control that
    read as present and was not. What an unknown stop reason should DO is still unstated
    and is carried in §8 with the transport that has the gap.'
- issue_id: I-005
  category: adr-contradiction
  severity: high
  description: '§4.4 asserts a deletion exception to ADR-0010 §5 and openly calls
    it "a narrowing this SPEC makes", noting the ADR "names no exception" — a SPEC
    amending an accepted ADR, which ADR-0010''s own Status paragraph says a SPEC may
    not do. The remove-vs-rewrite argument does not close the hole it opens: after
    deletion a later ingest re-runs a reader measured at 3.6% run-to-run divergence,
    so different stored text ends up serving the same (bytes, extractor identity)
    pair. Because §4.3 puts extracted text inside `content_hash`, that flips the document
    hash with no edit, which is the churn ADR-0006''s spine (re-embed on `chunk_text
    IS DISTINCT FROM`, entropy signal ② cross-URI hash collisions, `doc_reingest_events`)
    is built to keep meaningful. Either the exception belongs in a successor ADR or
    the deleted row must be tombstoned so re-extraction is blocked under the same
    identity.'
  status: accepted
  disposition_reason: 'Governance, and the reviewer is right that a SPEC cannot amend
    an accepted ADR — ADR-0010''s Status paragraph says so. The second half is also
    right: after a deletion, re-ingest re-reads with a reader that diverges run to
    run, so different text lands under the same (bytes, identity) pair and flips content_hash
    with no edit. Recorded in §8 with the two ways out — a successor ADR, or a tombstone
    that refuses re-extraction under the same identity. Not decided inside this SPEC,
    because deciding it here is the thing being objected to.'
- issue_id: I-006
  category: untestable-requirement
  severity: high
  description: '§7.1 pre-registers two gates: zero invention and fidelity ≥6 of 8
    on the pass/partial scale. §7.4 concedes the fidelity score "was never computed"
    and that the substitute method cannot produce it — "a reader that omits half a
    screen scores clean here" — and also concedes §7.1c''s ordering (director''s reading
    precedes the machine''s) is unsatisfied. No replacement fidelity criterion is
    registered anywhere in the SPEC. So the shipped system has no gate at all on whether
    the transcription is faithful, only on whether it is fabricated, and §7''s opening
    claim that nothing counts as success until acceptance is met is left unsatisfiable
    as written.'
  status: accepted
  disposition_reason: 'Correct and load-bearing: with the fidelity leg unmet and no
    replacement registered, the corpus is guaranteed against fabrication and not against
    omission. §7.5 states the gate as NOT MET rather than unmeasured, and §8 carries
    what would close it — a bound on omission, the axis §7.4 opened with 14 measured
    items. Registering that gate now, in the same document that discovered the axis,
    would be the post-hoc criterion §7.1 exists to prevent.'
- issue_id: I-007
  category: missing-invariant
  severity: high
  description: §4.4 states the tenant is in the store's primary key as a security
    boundary — a global store "would serve one tenant's extracted text to another,
    including text that the first tenant's quarantine gate rejected", and would leak
    the existence of an image across the boundary. §7.2.8, the only cache test, asserts
    the key is "(bytes, extractor identity)" and says nothing about tenant. No test
    asserts that byte-identical images in two tenants extract independently, or that
    a quarantine deletion in tenant A does not affect tenant B. The stated boundary
    is therefore unenforced by the test suite, and §7.2.8's wording reproduces exactly
    the two-part key the section says was the earlier defect.
  status: accepted
  disposition_reason: 'The stated security boundary is untested: §7.2.8''s wording
    even reproduces the two-part key §4.4 says was the defect. A test that byte-identical
    images in two tenants extract independently, and that a quarantine deletion in
    one does not affect the other, is cheap and belongs with the cache tests. Carried
    as an accepted correction to §7.2 rather than a design change — the key is already
    right in code.'
- issue_id: I-008
  category: risky-assumption
  severity: medium
  description: '§3.1 caps extraction at `NEXUS_VISION_MAX_PER_INGEST` = 100 *per run
    of the ingest command*, and says images past the ceiling are "recorded as failure
    rows, so the run is repeatable". §7.2.9 then makes failure rows sticky by design
    — an image with a failure row stays unextracted "until a human deletes the row".
    These two combine into non-convergence: a tenant with more than 100 images can
    never fully extract by re-running ingest, because the overflow images now carry
    sticky rows that suppress the retry the ceiling assumed. The current corpus (44)
    hides this; the first larger tenant hits it silently, with only a count in the
    ingest summary to show for it.'
  status: accepted
  disposition_reason: 'A real non-convergence and nicely spotted: the ceiling records
    overflow as failure rows so the run is repeatable, and §7.2.9 makes failure rows
    suppress the very retry that repeatability assumed. 44 images is under the ceiling
    so it is latent today. Recorded in §8 with the trigger — the first tenant above
    the ceiling — rather than fixed now, because the fix (distinguishing ''not attempted''
    from ''attempted and failed'') is a schema change.'
- issue_id: I-009
  category: undefined
  severity: medium
  description: 'Retry is defined as "an explicit act — deleting the failure row" (§7.2.9)
    and quarantine remediation is defined as deleting the `vision_extractions` row
    (§4.4), but no operator surface for either is specified: no CLI command, no API
    endpoint, no MCP tool, and §6''s ships list contains none. The only documented
    remedy for a transient fetch failure or for quarantined PII is hand-written SQL
    against a production table, which is also the one path §4.4''s invariant depends
    on being performed correctly. §6 also lists migrations as `0NN_*` while §4.4 names
    "migration 013", so even the migration identity is unfixed.'
  status: accepted
  disposition_reason: 'Both remedies are hand-written SQL against a live table, and
    one of them is what §4.4''s invariant depends on being done correctly. Recorded
    in §8. Not shipped in this round: the surface should follow the tombstone decision
    in I-005, since what the operator needs to express changes with it.'
- issue_id: I-010
  category: undefined
  severity: medium
  description: The extractor identity is load-bearing for §4.3's marker, §4.4's primary
    key, and any recall scope, yet the SPEC never states its current value. §3 pins
    `NEXUS_VISION_MODEL` to the literal `claude-sonnet-4-6` and the prompt to a module
    constant; §7.3 says "the reader that produced those rows has since been withdrawn"
    and replaced under two other SPECs; §7.4 says the system prompt gained a rule
    that "moved `prompt_sha` and therefore the extractor identity". A reader of this
    document cannot determine which model id and which prompt constitute the reader
    of record, nor whether §3's pinned default still matches what the 44 live rows
    were produced under — which is precisely the enumeration ADR-0010 §3.1 says identity
    exists to make possible.
  status: accepted
  disposition_reason: 'A reader could not tell which model and prompt produced the
    live rows, and identity is what ADR-0010 §3.1 makes a recall scopable by. §7.5
    states it once: gemini-3.6-flash/06e83390, 44 rows, 41 active chunks, 0 truncated,
    and the note that §3''s pinned default must move with it.'
- issue_id: I-011
  category: unverifiable-claim
  severity: medium
  description: §7.1b claims "Step 0b passed", but §7.1's registration required a working
    re-fetch from stored `source_ref` alone "for at least one image per document"
    — five documents. The run covered 11 images of a single document, and the closure
    via SPEC-nexus-vision-source-ref rests on "3 of 3 citations resolved by hand",
    again with no per-document coverage claim. Since the four unopened documents are
    also the ones §1 and ADR-0010 flag as inference rather than measurement, the gate
    was scored on the one document least representative of the residual risk, while
    being reported as satisfied.
  status: accepted
  disposition_reason: 'The registration said one image per document — five — and both
    the original run and its replacement drew from documents already opened. §7.5
    records the gate as partially met and names the gap precisely: the four documents
    §1 flags as inference rather than measurement are the uncovered ones, which is
    the worst place for the coverage to be thin.'
- issue_id: I-012
  category: unverifiable-claim
  severity: medium
  description: The acceptance criterion is in three mutually inconsistent states and
    the document never resolves which binds. §7.1a-0 declares ADR-0010's demand-pull
    gate partly falsified and §7.1a declares the original criterion void and replaces
    it with the Ava_01 question, whose expected value is explicitly marked UNVERIFIED
    pending the director; §7.3 then withdraws the step 0 verdict entirely and says
    "the original acceptance criterion stands and it passes"; §8 still carries "ADR-0010
    owes a successor note" premised on the withdrawn falsification. A reader cannot
    tell whether §7.1a's replacement is live, dead, or still owed a verification,
    nor whether the ADR debt is real.
  status: accepted
  disposition_reason: 'Three inconsistent states in one document, and the reviewer
    is right that a reader cannot tell which binds. §7.5 resolves it in a table: §7.1a''s
    replacement is dead (it existed only because step 0 concluded the thresholds were
    in no image, and that conclusion was withdrawn), the original question is live
    and passes, and the ADR successor note is still owed but for the §7.1b reason
    rather than the withdrawn one.'
- issue_id: I-013
  category: risky-assumption
  severity: medium
  description: 'Omission is measured and unbounded. §7.4 reports 14 items in rounds
    2 and 3 where each reader recovered real in-image content the other missed, and
    §8 defers the union-of-two-readers remedy. The shipped design is a single reader,
    so an unknown fraction of every extracted screen is silently absent — and unlike
    invention, omission carries no signal at all: the chunk is tiered `machine_read`
    and reads as a complete transcription. §5''s "the honest outcome there is a short
    extraction" assumes a reader that fails visibly; the measurement shows one that
    fails quietly, and nothing in §3, §4, or the tier communicates partiality to a
    consumer.'
  status: accepted
  disposition_reason: 'The sharpest consequence of §7.4 and it deserves the emphasis:
    unlike invention, omission carries no signal — the chunk is tiered machine_read
    and reads as a complete transcription. §5''s assumption of a visibly-failing reader
    is contradicted by the measurement. Recorded in §7.4, §7.5 and §8; the remedy
    (a union of two readers) doubles the standing cost and is a different design,
    deferred to its own SPEC.'
- issue_id: I-014
  category: missing-invariant
  severity: medium
  description: §4.1 fetches image bytes from a URL supplied by the source system during
    the converter walk, and §7.3 records that an SSRF in that fetcher "was found by
    review before it ran" — yet no section of the design states any constraint on
    the fetcher (scheme allowlist, host allowlist, redirect handling, size limit,
    timeout, private-address refusal), and §7.2 contains no test for any of them.
    A defect caught once by a human review and never converted into a stated invariant
    plus a test is, by this SPEC's own standard in §3.1, a control that reads as present
    and is not.
  status: rejected
  disposition_reason: 'The premise is wrong in its second half, and that matters more
    than the first. The constraints do exist and are tested: vision_store.check_url
    refuses non-https schemes, refuses hosts resolving to private/loopback/link-local/reserved
    addresses across ALL resolved records, and _fetch_bytes refuses to follow redirects;
    tests/test_vision_wiring.py asserts each, including that a refused URL is recorded
    as a failure row rather than silently skipped. What is true is that the design
    section never stated the invariant, which is the accepted half of I-002/I-003''s
    complaint and is addressed there. Rejected as written because it asserts an absence
    that measurement contradicts — the same shape of error this SPEC has been caught
    by twice.'
- issue_id: I-015
  category: unverifiable-claim
  severity: low
  description: '§3.1 justifies the 20,000-character store cap as "sized deliberately
    above what the token cap can emit" for a 4096-token ceiling, and the withdrawn
    design is criticised on the parallel arithmetic that "2048 tokens of Korean does
    not reach 8000 characters". Neither ratio is measured or cited for the actual
    tokenizer and the actual Korean/markdown-table mix, and the safety argument depends
    on it: if the real chars-per-token exceeds ~4.9, the character cap becomes the
    binding limit again and the truncation the design intends to mark is the one it
    silently performs.'
  status: deferred
  disposition_reason: 'Fair: the character cap''s safety argument rests on an unmeasured
    chars-per-token ratio for Korean plus markdown tables. Deferred rather than accepted
    because the binding limit is now observable directly — 0 of 44 rows are marked
    truncated and the reader of record reports finishReason — so the cheap answer
    is to watch that counter rather than to derive a ratio. Trigger: the first row
    that is truncated with a stop reason of anything other than the token ceiling.'
- issue_id: I-016
  category: unverifiable-claim
  severity: low
  description: §7.3 concludes that the answer-quality drop is not caused by extraction
    and that the NULL-vector repair was the real fix, but the only post-repair number
    reported is a retrieval statistic ("gold answers outside the top ten went from
    3 to 0"); no answer-quality run after the repair is given, while the pre-repair
    series (34, 36, 35, then 36, 34, 32) is. The conclusion that quality is now accounted
    for therefore rests on a measurement the SPEC does not report — and §8 concedes
    the eval set itself "measures a corpus that no longer exists", so the ruler used
    for both series is disclaimed in the same document.
  status: accepted
  disposition_reason: 'The conclusion did rest on a number the SPEC never reported.
    Now reported in §7.3: retrieval Recall@10 40/40 and three answer runs at grounded
    39/40 — level with the best figure this SPEC ever recorded, with extraction in
    the corpus. The reviewer''s second point stands and is recorded beside it: the
    ruler is disclaimed in the same document, and the 2026-08-11 run additionally
    found the scoring marks a correct answer wrong when it cites a document other
    than the single one a label names.'
- issue_id: I-017
  category: scope-creep
  severity: low
  description: §4.3 moves marker sanitisation from the Notion converter into the chunker
    as a default-distrust flag applied to *every* intake path, present and future
    (`ingest_external_spec`, filesystem docs, anything added later). The reasoning
    is sound for tiering, but the effect is that this image-extraction SPEC now silently
    mutates authored body text on paths it does not otherwise touch, deleting any
    literal occurrence of two HTML comment strings from documents nobody extracted
    an image from. Only §7.2.15 covers the authored direction and only, by its wording,
    for one path; the cross-path behaviour change is neither enumerated in §6's ships
    list nor tested per intake path.
  status: accepted
  disposition_reason: Correct that an image-extraction SPEC now mutates authored bodies
    on paths it does not otherwise touch, and that body text feeds content_hash. The
    behaviour is right for tiering — a marker this repo writes must not be trusted
    when it appears in authored text — so what is owed is enumeration, not reversal.
    Recorded in §8 as a cross-path behaviour to be listed and tested per intake path.
approved_by: LivingLikeKrillin
approved_at: '2026-08-11T16:19:46Z'
---

