---
target: SPEC-nexus-citation-validation
critiqued_hash: sha256:8778f6518281efef0f4585dffd7da7066a50baa16f2ad101b0281fd0cace4f8a
critiqued_at: '2026-07-11T18:25:12Z'
issues:
- issue_id: I-001
  category: undefined
  severity: high
  description: §4.2 claims 'the streaming path' includes citations/unverified_citations
    'in its final/answer event', but the stream endpoint (api.py:745-859) never calls
    generate_answer — it calls llm_svc.stream() directly and emits only evidence/graph/answer_delta/done
    events, with no 'final/answer event' that carries the answer text. Wiring the
    validator into generate_answer (the only wiring the spec designs) covers /search/answer
    but cannot cover the stream; the stream needs its own accumulate-full-text-then-validate
    step and an event contract change (e.g. extend the 'done' event), none of which
    the spec specifies.
  status: accepted
  disposition_reason: null
- issue_id: I-002
  category: risky-assumption
  severity: medium
  description: '§4.1 parses the citation title as ''text up to the first comma or
    ]'', but the prompt format is ''[출처: 문서 제목, 섹션]'' and real doc titles (Notion
    pages, filenames) can legitimately contain commas. A comma-bearing real title
    gets truncated at the comma, fails normalization against packet.snippets[*].doc_title,
    and is falsely reported as unverified — polluting the very fabrication-rate signal
    the spec introduces. The design assumes titles are comma-free without stating
    or enforcing it, and §6 has no test for this case.'
  status: accepted
  disposition_reason: null
- issue_id: I-003
  category: missing-invariant
  severity: medium
  description: §4.2 adds the unverified-citation count to the search signal, but signals.py
    persists SearchSignals via an INSERT into search_log with a fixed explicit column
    list (signals.py:94-99). Adding the field requires a search_log schema migration
    (new column, plus keeping extract_signals/_persist/structlog fields in sync) —
    the spec never mentions the migration or how old rows (NULL vs 0) are interpreted
    by v_search_health-style aggregation, which affects the correctness of the 'fabrication
    rate over time' metric.
  status: accepted
  disposition_reason: null
- issue_id: I-004
  category: unverifiable-claim
  severity: medium
  description: §4.2/§7 claim 'fabrication rate becomes measurable over time', but
    §3 concedes the stream path records no signals at all ('a separate finding, not
    this SPEC'). Since the 2.0 web UI — the primary human surface — uses /search/answer/stream,
    the metric will systematically exclude most human-facing answers; the acceptance
    criterion 'the first faithfulness metric now exists' is true only for the non-stream
    minority of traffic, and the spec neither quantifies nor flags this coverage gap
    in the acceptance section.
  status: accepted
  disposition_reason: null
- issue_id: I-005
  category: unverifiable-claim
  severity: medium
  description: §1 frames the problem as 'a fabricated or mis-attributed citation ships
    as if grounded' and §7 claims 'a model that invents a citation is caught by the
    system', but the design only checks title existence in the packet. A mis-attributed
    citation (claim X cited to real packet doc A when the support is in doc B, or
    an invented section under a real title) passes as verified. §4.1 says the legitimate
    set is doc_title '(+ their section_path)' yet the matching rule is defined for
    title only — whether section is validated is left ambiguous, and §6 has no test
    for a real-title/wrong-section citation. The acceptance overclaims relative to
    what title-existence checking can catch.
  status: accepted
  disposition_reason: null
- issue_id: I-006
  category: untestable-requirement
  severity: medium
  description: '§4.2 requires the streaming path to include citations and unverified_citations,
    but §6''s test list covers only the pure validator and the non-stream generate_answer
    wiring. There is no test for the stream emitting the fields (or for the stream''s
    LLM-failure branch, which yields a canned answer_delta with the evidence appended
    — text that may itself contain literal ''[출처: …]'' strings from ingested docs
    about the citation convention). The stream requirement as written has no acceptance
    test.'
  status: accepted
  disposition_reason: null
- issue_id: I-007
  category: missing-invariant
  severity: low
  description: 'Normalized title matching (trim, collapse whitespace, case-insensitive)
    treats doc_title as a unique key, but nothing guarantees uniqueness: ADR-0006
    documents that document identity is tenant:basename and that distinct docs can
    share names/title stems (signal ③, title-stem collisions). Two packet snippets
    from different documents with normalization-equal titles make a citation ''verified''
    without identifying which document it actually cites, silently weakening the attribution
    guarantee the report implies.'
  status: accepted
  disposition_reason: null
- issue_id: I-008
  category: undefined
  severity: low
  description: §4.2 justifies the signal with 'an actual faithfulness metric, which
    the review found entirely absent' — 'the review' is an unresolvable referent inside
    the spec (no link, no date, no artifact). Similarly §3's 'a separate finding'
    is uncited. A reader or approver cannot verify these load-bearing motivational
    claims.
  status: accepted
  disposition_reason: null
- issue_id: I-009
  category: adr-contradiction
  severity: low
  description: §4.2 names A2A as a consumer that 'can mark which citations are grounded',
    implying the A2A answer payload is extended with the new fields. ADR-0004 §5 (and
    the standing Phase-4 decision) requires A2A to 'stay minimal and not be extended
    until a real agent pulls it' — there is no active A2A consumer today. If the fields
    flow through automatically via AnswerResult this is fine, but the spec should
    say so explicitly; as written it reads as extending the A2A contract without a
    puller.
  status: accepted
  disposition_reason: null
approved_by: LivingLikeKrillin
approved_at: '2026-07-11T18:28:07Z'
---

