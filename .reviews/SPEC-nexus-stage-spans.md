---
target: SPEC-nexus-stage-spans
critiqued_hash: sha256:bf37e6243097bef0a9b272f8744822569ccaf2da083bf62f0d10ce3301b9bea6
critiqued_at: '2026-09-04T11:51:37Z'
issues:
- issue_id: I-001
  category: missing-invariant
  severity: high
  description: §3.3/§5 never define the transaction boundary between the search_log
    insert and the span batch, and the two requirements as written conflict. The child
    FK requires the parent row to exist first; the registered test 'Capture failure
    is visible' demands that with a child CHECK deliberately violated, search_log
    is still written with a non-NULL spans_expected and zero span rows. If parent
    and children share one transaction (the natural reading of 'written in the same
    statement as search_log itself, before the span insert'), a child constraint violation
    aborts the transaction and rolls the parent back too — spans_expected never survives
    and the test cannot pass. The spec must state that the span batch runs in its
    own transaction or under a SAVEPOINT, and that record_search commits the parent
    first.
  status: accepted
  disposition_reason: null
- issue_id: I-002
  category: missing-invariant
  severity: high
  description: The reader invariant 'COUNT(child rows) = LEAST(candidates_expected,
    candidates_cap)' is contradicted by the diversify cap exemption in the same section.
    For a diversify span whose fusion input exceeds spans.max_candidates_per_span,
    the row count equals candidates_expected while candidates_cap is stamped lower,
    so LEAST() is smaller than the actual count. The enumerated exceptions cover only
    purge, the answer stage and fired=false — diversify is a fourth uncovered case,
    and a Unit 2 reader written to the stated invariant will report phantom data loss
    (or, worse, phantom extra rows) on exactly the span that carries the FP3 diagnostic
    payload.
  status: accepted
  disposition_reason: null
- issue_id: I-003
  category: undefined
  severity: high
  description: search_log.span_write_ms has no write path. It is defined as the duration
    measured around the span insert, so its value is only known after that insert
    completes — but §3.3 specifies a single search_log insert that carries spans_expected
    before the span insert, and explicitly rejects a second post-hoc statement (I-007)
    as reintroducing a crash window. Populating span_write_ms therefore requires an
    UPDATE on search_log after the child batch, which the design neither specifies
    nor reconciles with its own I-007 reasoning (including what the column holds when
    that UPDATE is the thing that crashes).
  status: accepted
  disposition_reason: null
- issue_id: I-004
  category: untestable-requirement
  severity: medium
  description: The equivalence test asserts 'identical search_log values ... excluding
    latency_ms, span_write_ms, spans_expected, completion_tokens, cost_usd', but search_log
    also carries n_citations, unverified_citations and (per §2) unverified_numbers,
    all derived from the nondeterministic LLM answer text. The exclusion list omits
    them, so the test as specified asserts equality over generation-dependent values
    and will flake for reasons unrelated to span capture. Either exclude every answer-derived
    column or run the equivalence arm retrieval-only, as the constructed case does.
  status: accepted
  disposition_reason: null
- issue_id: I-005
  category: undefined
  severity: medium
  description: The packet span is specified to cover 'what entered the prompt, including
    graph findings' and records n_graph_edges, but search_span_candidate has doc_rid
    NOT NULL and a rank keyed to 'snippet order as assembled into the prompt'. Graph
    edges attached by assemble_packet are not chunks and have no doc_rid, so the schema
    cannot represent them. It is undefined whether graph findings get candidate rows
    at all, and if they do not, the packet span's row count silently disagrees with
    n_snippets + n_graph_edges for any request with graph evidence.
  status: accepted
  disposition_reason: null
- issue_id: I-006
  category: missing-invariant
  severity: medium
  description: 'Writer invariant 3 (''leg rows number exactly 2 x search_log.fusion_channels'')
    rests on fusion_channels, whose semantics are never pinned down — channels attempted,
    channels that ran, or channels that returned at least one hit. It also has no
    failure case: fired=false is specified only for non-leg stages, so a single leg
    that errored or short-circuited while its sibling ran produces 2n-1 rows, which
    the reader must read as lost data. Legs need the same fired=false treatment as
    other stages, or the invariant is unenforceable in production.'
  status: accepted
  disposition_reason: null
- issue_id: I-007
  category: risky-assumption
  severity: medium
  description: The constructed case stubs the embedder but not the BM25 side. 'The
    answering chunk is placed by construction outside the BM25 pool' is a property
    of ts_rank_cd, the Korean tsvector configuration and search.bm25_top_k on the
    fixture corpus — real code, not fixture data. A tokenizer, dictionary or config
    change can move the chunk into the BM25 pool and silently break the gate, which
    is precisely the fragility §1.3 cites to justify stubbing the embedder. The BM25
    leg needs the same treatment (fixture scores or a pool made empty by construction)
    or the claim's determinism is asserted rather than built.
  status: accepted
  disposition_reason: null
- issue_id: I-008
  category: adr-contradiction
  severity: medium
  description: '§1.1''s second blind path — ''a vector can be recomputed with neither
    a corpus-generation change nor a reingest row'' — is stated against ADR-0006,
    which decided the opposite mechanism: embedding/tsvector invalidation happens
    only when chunk_text IS DISTINCT FROM the prior text, and a chunk text change
    on re-ingest is itself an overwrite recorded in doc_reingest_events. Under the
    accepted ADR the two events coincide, so the named blind path exists only for
    cases the spec does not identify (backfill of never-embedded chunks, an offline
    model or dimension change). As written it either contradicts ADR-0006 or describes
    an unfixed deviation from it, and Unit 2''s refusal rules are being scoped on
    the unverified version.'
  status: accepted
  disposition_reason: null
- issue_id: I-009
  category: missing-invariant
  severity: medium
  description: 'jsonb_values_all_scalar assumes detail is a JSON object. jsonb_each
    raises on a non-object jsonb value, so inserting detail = ''[]'' or ''"x"'' produces
    a runtime error rather than a clean CHECK violation, and the constraint never
    restricts the top-level type; it should be CHECK (jsonb_typeof(detail) = ''object''
    AND jsonb_values_all_scalar(detail)). Relatedly, the claim that ''a second writer,
    a migration or a manual insert cannot store nested JSON'' overstates the guarantee:
    a CREATE OR REPLACE of the helper does not revalidate existing rows or the constraint,
    so the database enforces the rule only as long as nobody redefines the function.'
  status: accepted
  disposition_reason: null
- issue_id: I-010
  category: risky-assumption
  severity: medium
  description: spans.enabled defaults to true while §7 leaves the candidate retention
    window (14 days / 3 days / doc_rid-only) as an open owner decision at sign-off.
    Capture is on by default, so merging the unit begins accumulating the very ranked-candidate
    corpus §3.4 concedes is a re-identification fingerprint correlatable with evidence_tenants,
    timing and principal, before the option that bounds that risk has been chosen.
    The reversible posture matching option 2 is to default the switch off, or to default
    candidate_retain_days to the shortest window until sign-off records a choice.
  status: accepted
  disposition_reason: null
- issue_id: I-011
  category: undefined
  severity: medium
  description: '''Truncation keeps the lowest ranks'' is ambiguous in the one place
    ambiguity is expensive: rank is 1-based input ordering, so ''lowest ranks'' reads
    equally as the best rows (ranks 1..cap) or the worst (the tail). The whole diagnostic
    value of a truncated span depends on which, and the diversify-exemption rationale
    (''truncating by input rank would discard exactly them'') implies the tail is
    discarded — but the normative sentence never says so. State it as ''keeps ranks
    1..candidates_cap and discards the tail''.'
  status: accepted
  disposition_reason: null
- issue_id: I-012
  category: undefined
  severity: medium
  description: search_span.index_generation is declared TEXT with no source, no NOT
    NULL and no stated relationship to index_generation_events (which column, what
    value when no generation has been declared, and whether TEXT matches that table's
    key type). Since it is one of only two drift anchors Unit 2 is told to rely on,
    and the A51 recorded observation is pinned to it, an unspecified type/source means
    the pinning may not be reproducible across deployments.
  status: accepted
  disposition_reason: null
- issue_id: I-013
  category: undefined
  severity: low
  description: 'The answer span''s non-candidate columns are unspecified: §3.2 gives
    it no candidate rows and the invariant carve-out sets candidates_expected = 0,
    but n_in, n_out and candidates_cap are never defined for it (NULL, 0, or the packet''s
    cardinality). A reader aggregating n_in/n_out across seq to trace carry-through
    has no defined value at the last stage.'
  status: accepted
  disposition_reason: null
- issue_id: I-014
  category: unverifiable-claim
  severity: low
  description: '§1.4''s bounded-worst-case arithmetic does not add up to its own figure:
    with a rewrite channel the legs contribute 80, fusion''s merged union up to 80
    and diversify''s inputs up to 80 — 240 before section_fill additions and the packet
    — so ''≈ 250 rows per request'' understates the stated bound unless per_doc_cap
    and top_k together are under ten. Either the per-span cap of 100 is meant to apply
    to fusion and diversify (in which case the bound is ~80+100+100+fill+top_k) or
    the arithmetic needs restating; as written the only quantified bound in the cost
    section is not derivable from its own terms.'
  status: accepted
  disposition_reason: null
- issue_id: I-015
  category: unverifiable-claim
  severity: low
  description: '''FP1 is already covered live (index/embed_health.py, search/confidence.py)''
    is asserted with no evidence and is the basis for excluding FP1 from capture.
    This repository''s own recent history is that the FP1 detector existed but its
    result never reached any consumer, and that a broken vector index failed silently.
    ''Covered'' needs to name what surface reports it and where, or FP1 should be
    listed alongside FP6 as instrumented-but-undelivered.'
  status: accepted
  disposition_reason: null
- issue_id: I-016
  category: scope-creep
  severity: low
  description: The cost deliverable pulls in a synthetic replay harness — a fixed
    fixture corpus, 100 runs per arm, two arms, plus new end-to-end request latency
    instrumentation across both — and a permanent production column (span_write_ms)
    whose output is explicitly 'reported, not asserted' with no threshold and no action
    defined for any result. That is benchmark machinery built alongside a capture
    unit, and it appears in neither §4.2's deferral list nor §7's sign-off. Either
    the replay harness is scoped as its own item or the measurement is narrowed to
    what the span rows already record.
  status: accepted
  disposition_reason: null
approved_by: LivingLikeKrillin
approved_at: '2026-09-05T06:43:06Z'
---

