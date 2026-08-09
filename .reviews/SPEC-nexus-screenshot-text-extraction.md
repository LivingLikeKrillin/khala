---
target: SPEC-nexus-screenshot-text-extraction
critiqued_hash: sha256:d19b6a9e32e69ae24702e4b7a8242f603a8d467171f38758dd740b92bf2ccf30
critiqued_at: '2026-08-09T09:45:55Z'
issues:
- issue_id: I-001
  category: adr-contradiction
  severity: high
  description: '§4.4 changes what a Nexus citation promises — an LLM now *authors*
    document body text rather than narrating over retrieved text — which cuts against
    ADR-0002''s principle ''Grounded answers only / system decides, LLM narrates''
    as the integrity layer. The doc concedes it ''widens ADR-0002''s ground'' but
    discharges that by *linking* the ADR. A SPEC cannot amend an ADR: this needs an
    ADR that extends/supersedes ADR-0002 with a recorded director disposition, gated
    before implementation, not a paragraph inside the design.'
  status: open
  disposition_reason: null
- issue_id: I-002
  category: missing-invariant
  severity: high
  description: §4.6 opens the `Read` tool but states no enforcement that only the
    downloaded image is readable. '--allowed-tools Read' permits reading any path
    the ingest host user can read; 'one file, named explicitly, per invocation' is
    a prompt convention, not a control. No sandbox, no path allowlist, no working-directory
    jail, no unprivileged/ephemeral user is specified — so the blast radius claimed
    in §4.6 is asserted, not established.
  status: open
  disposition_reason: null
- issue_id: I-003
  category: untestable-requirement
  severity: high
  description: Test 5 asserts 'no tool call other than the single named Read occurs'
    — but the attack it is meant to catch (injected text causing the model to read
    ~/.ssh) *is* a Read call, so the test passes while the attack succeeds. The control
    must assert the *argument* (only the named image path was read) and that no unexpected
    path appears, not the tool name.
  status: open
  disposition_reason: null
- issue_id: I-004
  category: missing-invariant
  severity: high
  description: 'No invariant that extracted text derives solely from the image''s
    pixels. §4.6 argues the output ''is never interpreted as an instruction'', which
    addresses the wrong half: the exfiltration path is injected text causing the model
    to read a secret and emit it as extracted content, which then becomes indexed,
    quarantine-scanned-only-for-PII document body and is later cited as grounded.
    Nothing bounds output to image-derived content.'
  status: open
  disposition_reason: null
- issue_id: I-005
  category: untestable-requirement
  severity: high
  description: Tests 1, 2 and 5 all require an authenticated `claude` CLI, which §3
    says exists only on a dev host and must never be in team/prod compose. The doc
    never says how these run in CI. Under this repo's own rule that a skipped test
    is no test, the three primary controls (fidelity, no-invention, injection) would
    be permanently skipped. No recorded-transcript/replay fixture or deterministic
    stub strategy is defined.
  status: open
  disposition_reason: null
- issue_id: I-006
  category: risky-assumption
  severity: high
  description: 'The entire model selection rests on n=1: ''One screenshot was read
    by a human first''. From that single sample the doc concludes ''claude CLI 5/5
    pass'', ''local 3/5 partial'', and — most load-bearing — ''Neither local model
    invented anything''. A no-hallucination property cannot be established from one
    image; there is no per-document sampling, no second reader, and no acceptance
    threshold that the actual 44-image run must clear before its output is committed
    to the corpus.'
  status: open
  disposition_reason: null
- issue_id: I-007
  category: missing-invariant
  severity: high
  description: §4.3 keys the cache on image bytes alone, and test 6 cements that ('keyed
    by bytes, not by block id'). The key omits model id, prompt version, and extraction
    settings — so changing or upgrading the vision model silently serves extractions
    produced by the old one, while the §4.2 marker records `model=<id>` that no longer
    matches the stored content. No invalidation or re-extraction path is specified.
  status: open
  disposition_reason: null
- issue_id: I-008
  category: risky-assumption
  severity: high
  description: §7.1 proposes committing the §2 screenshot as the fixture, and §4.5
    states that screenshot contains a work email address. That places real partner
    PII and an organisational fingerprint into a repo whose CI runs a fingerprint
    scan on every commit. No redaction, synthetic-fixture, or out-of-tree-fixture
    plan is given, and the no-invention test (7.2) additionally requires the human-recorded
    contents of that image to be checked in alongside it.
  status: open
  disposition_reason: null
- issue_id: I-009
  category: untestable-requirement
  severity: high
  description: There is no acceptance criterion tied to the failure that prompted
    the work. The §1 question (per-avatar unlock thresholds) is never restated as
    a test, a label, or a measurement; §5 and §8 concede answer quality on image-carried
    policy stays unmeasured until labels exist. Every test in §7 can pass with the
    motivating question still unanswered, so nothing determines whether the SPEC succeeded.
  status: open
  disposition_reason: null
- issue_id: I-010
  category: missing-invariant
  severity: medium
  description: '§3 declares this dev-only, but §4.1 puts it inside the shared `ingest-notion`
    converter, so a dev host and a team host produce different bodies — and different
    content hashes — for the same Notion page. The doc does not state how content-hash
    idempotency, supersession, or re-ingest behave when vision is off: a team-host
    re-ingest could silently erase vision-derived text, or create coexisting divergent
    versions, which this repo''s own ingestion model names as the top entropy source.'
  status: open
  disposition_reason: null
- issue_id: I-011
  category: missing-invariant
  severity: medium
  description: §4.4 requires the derivation flag to survive chunking, search results,
    the evidence packet, citations, and the corpus view, but §6 ships only the converter,
    a vision client, pipeline wiring, and a cache migration — no chunk/document column,
    no search, evidence, or web change. Derivation therefore lives only in-band in
    markdown text, which chunking can split from its blockquote, which an authored
    document can forge, and which any text transform can strip. Test 3 asserts the
    property the ships list does not build.
  status: open
  disposition_reason: null
- issue_id: I-012
  category: undefined
  severity: medium
  description: 'The §2 scoring notation is never defined: ''3/5 partial'' and ''5/5
    pass'' could be 5 elements or 5 trials, and the pre-registered criteria block
    names four things (screen id, version, rule sentence, both table attribute names),
    not five. ''Small print'' (§2, §8) and ''non-trivial line'' (§7.2) are likewise
    undefined, and test 2 gives no matching rule — exact string, fuzzy, or Korean-normalized
    — against the human''s recorded contents.'
  status: open
  disposition_reason: null
- issue_id: I-013
  category: undefined
  severity: medium
  description: The interaction between test 4 (PII in an image is quarantined) and
    test 7 (extraction failure degrades, does not abort) is unspecified. Quarantining
    vision-derived text could mean quarantining the whole document, dropping only
    that image region while indexing the rest, or blocking the ingest — and opposite
    implementations satisfy both tests as written. §4.5's 'same terms as any other
    document content' does not resolve it, because prose PII has no per-region fallback.
  status: open
  disposition_reason: null
- issue_id: I-014
  category: risky-assumption
  severity: medium
  description: §4.1 requires extraction to happen 'during' the walk because presigned
    URLs expire in one hour, while §2 measures 19 s per image serially (~14 m for
    44). The doc does not separate the fast fetch (which genuinely must be in-walk)
    from the slow extraction (which need not be), states no concurrency or rate-limit
    behaviour for the CLI, and gives no bound on documents large enough that later
    URLs expire mid-walk.
  status: open
  disposition_reason: null
- issue_id: I-015
  category: unverifiable-claim
  severity: medium
  description: The cost column records 'no API credit' and §4.3 asserts steady-state
    cost 'near zero', treating an interactive subscription CLI driven in bulk from
    an ingest pipeline as free and unlimited. No rate limit, quota, concurrency ceiling,
    or statement that automated non-interactive bulk use is a supported mode is given
    — and §8 lists the subscription only as an availability dependency, not a capacity
    or entitlement one.
  status: open
  disposition_reason: null
- issue_id: I-016
  category: scope-creep
  severity: low
  description: §4.4's third bullet — 'the corpus view counts vision-derived characters
    separately from authored characters' — adds a reporting/web surface that appears
    in neither §6's ships list nor any test in §7. Either it is out of scope for this
    SPEC or the ships list is incomplete.
  status: open
  disposition_reason: null
approved_by: null
approved_at: null
---

