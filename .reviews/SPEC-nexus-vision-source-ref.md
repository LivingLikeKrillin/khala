---
target: SPEC-nexus-vision-source-ref
critiqued_hash: sha256:4f80897a9b647ed5294a9a0c9561870290e06319e15bdab5c99a257d3299be20
critiqued_at: '2026-08-11T13:51:31Z'
issues:
- issue_id: I-001
  category: adr-contradiction
  severity: high
  description: ADR-0010 §3.1 requires a re-resolvable source reference to *travel
    with* the tier ("Two more facts have to travel with it"), and §4 names six hops
    the tier must survive (SearchHit, evidence packet, citation, API response, MCP
    results). This design stores block_id/source_uri only in the vision_extractions
    side table, puts only a 16-hex handle in chunk_text, and then declares "No citation-surface
    change" as a non-goal (§3). resolve_source() is also exposed nowhere — no CLI,
    API, or MCP surface is specified — so the motivating scenario in §1 ("a reader
    holding a citation cannot reach the image") remains true after this SPEC ships
    for every consumer that is not a Python caller. The acceptance criterion "source_ref()
    has at least one caller" is satisfiable without the reader ever gaining the recourse
    ADR-0010 §2 promises.
  status: accepted
  disposition_reason: null
- issue_id: I-002
  category: adr-contradiction
  severity: high
  description: '§2.4 backfills block_id "by the same re-ingest that adds the marker,
    because the walk has the block ids in hand", but ADR-0010 §5 fixes the opposite
    invariant: "Unchanged bytes are never re-extracted. Re-ingest resolves the stored
    result by (byte hash, extractor identity)." If the save path at vision_store._one()
    is skipped on a stored-result hit — which is what §5 mandates for all 44/40 existing
    images, whose bytes are unchanged — then source_ref() never fires, block_id stays
    '''', and §6''s acceptance ("After re-ingest, zero extractions have an empty block_id")
    is unreachable. The SPEC does not say how the stored-result path is made to write
    the two new columns without re-running the reader, which is the one thing ADR-0010
    §5 forbids.'
  status: accepted
  disposition_reason: null
- issue_id: I-003
  category: missing-invariant
  severity: high
  description: 'The 16-hex handle is the only join key from chunk to extraction row,
    yet nothing enforces its uniqueness: no unique index, no CHECK, no constraint
    on (tenant, left(image_sha256,16), extractor_identity). §2.1 claims §5 "asserts
    uniqueness rather than assuming it", but §5.5 is a point-in-time measurement over
    the current live corpus — it says nothing about the next image ingested. The behavior
    of resolve_source() when the prefix match returns two or more rows is undefined;
    the natural implementations (first row, or LIMIT 1) silently return the wrong
    image''s source_uri/block_id, i.e. a citation that resolves to a *different* image,
    which is worse than the unresolvable state this SPEC exists to end.'
  status: accepted
  disposition_reason: null
- issue_id: I-004
  category: untestable-requirement
  severity: medium
  description: 'The two load-bearing checks are specified against live, mutable state:
    §5.5 asserts prefix uniqueness "over the live corpus''s shas", and §6 requires
    "the round trip of §5.3 passes against a real image from the live corpus" — which
    needs a live Notion block, the correct per-root token, and an unexpired signed
    URL (§4 concedes all three can vanish). Neither is reproducible in CI against
    a disposable test DB, so both will either be skipped or will fail for reasons
    unrelated to the change. The SPEC does not specify a fixture-based equivalent,
    so the assertion it calls "the assertion that the reference is real" has no repeatable
    form.'
  status: accepted
  disposition_reason: null
- issue_id: I-005
  category: missing-invariant
  severity: medium
  description: block_id/source_uri are added as NOT NULL DEFAULT '' and §2.4 assigns
    '' the meaning "this extraction cannot be resolved to its source", but no invariant
    stops *new* rows from being written with ''. There is no CHECK (block_id <> ''),
    no failure on the save path when the walk lacks a block id, and no rule that an
    extraction whose reference is missing must not be admitted as machine_read. Since
    §2.4 itself states an unresolvable machine_read chunk is "a tier whose justification
    is not met", the design leaves the tier's own precondition unenforced going forward
    and detectable only by a counter someone chooses to read.
  status: accepted
  disposition_reason: null
- issue_id: I-006
  category: undefined
  severity: medium
  description: '§5.6''s reporting boundary does not match the population it counts:
    nexus status is to report "the count of extractions with an empty block_id" but
    to report "nothing for a tenant with no machine_read chunks". Extraction rows
    and machine_read chunks are exactly the two unjoined populations §1 says had to
    be reported separately — a tenant can hold extraction rows whose chunks were never
    produced, superseded, or re-chunked, and those unresolvable rows would be suppressed
    by a chunk-side test. The SPEC does not define which population the suppression
    predicate reads, so the counter can report zero while unresolvable extractions
    exist.'
  status: accepted
  disposition_reason: null
- issue_id: I-007
  category: undefined
  severity: medium
  description: 'resolve_source(tenant, chunk_text) has no specified behavior for the
    cases it will actually meet: a machine_read chunk ingested before this migration
    (marker present, no img= field), an authored chunk with no marker at all, a chunk
    whose extractor identity no longer has a matching row after an ADR-0010 §5 extractor
    migration, and a row found with block_id = ''''. Return value versus raised exception
    is unstated for all four, so callers cannot distinguish "no reference exists"
    from "lookup failed" — the same conflation §4 flags for ObjectNotFound reading
    as deletion.'
  status: accepted
  disposition_reason: null
- issue_id: I-008
  category: unverifiable-claim
  severity: medium
  description: 'The cost estimates are stated as exact counts with no query or provenance,
    and they do not reconcile with the linked ADR: ADR-0010''s census counted 44 image
    placeholders over five documents, while §2.3 asserts "the 40 machine_read chunks
    change text". §4 also says one extraction may split into two chunks, which makes
    chunks ≥ extractions, so 40 chunks for 44 images implies some images produced
    no chunk — an unexplained gap that is directly material, since those are precisely
    the images whose extractions can never be reached by the re-ingest backfill of
    §2.4.'
  status: accepted
  disposition_reason: null
- issue_id: I-009
  category: risky-assumption
  severity: medium
  description: §6 requires "zero extractions have an empty block_id for the operating
    tenant" after re-ingest, while §4 concedes the reference resolves only while Notion
    keeps the block and the token retains access. Any image whose block was deleted,
    moved out of the walked roots, or is under a root whose token changed will never
    be revisited by the walk, so its row keeps block_id = '' permanently with no remediation
    path and no rule for retiring it. The acceptance criterion is therefore contingent
    on external state the SPEC explicitly says it does not control, and offers no
    disposition for the residue.
  status: accepted
  disposition_reason: null
- issue_id: I-010
  category: scope-creep
  severity: low
  description: §3 lists "No citation-surface change" as a non-goal while §2.1 simultaneously
    reasons that a block id "would sit in every citation a user reads" — conceding
    the marker is user-visible text — and then adds img=<16 hex> to that same visible
    string. Adding a field to text rendered in citations is a citation-surface change;
    calling it a non-goal removes it from review and from the §5 test list (no test
    asserts how the handle renders to a human, only that it matches the row). Either
    the marker is user-visible, in which case the rendering is in scope, or it is
    not, in which case §2.1's argument for excluding the block id collapses.
  status: accepted
  disposition_reason: null
- issue_id: I-011
  category: missing-invariant
  severity: low
  description: §2.1 argues the marker cost is paid "once and must never change again",
    but the marker already embeds extractor=<model>/<prompt_sha>, which ADR-0010 §5
    requires to change on every extractor or prompt migration — so the hashed body
    churns again by design. The marker has no version field and no stated grammar,
    yet resolve_source() must parse it forever across those migrations. Nothing fixes
    the field set, ordering, or escaping, so the parser and the writer can drift with
    no test that pins the format.
  status: accepted
  disposition_reason: null
approved_by: LivingLikeKrillin
approved_at: '2026-08-11T14:04:02Z'
---

