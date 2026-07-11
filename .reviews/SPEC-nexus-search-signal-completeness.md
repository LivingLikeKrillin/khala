---
target: SPEC-nexus-search-signal-completeness
critiqued_hash: sha256:1e449459ecf4e9d0b7d11a4df6b42cfc61b1f2c0005e6b5e866061b35823cc81
critiqued_at: '2026-07-11T19:08:27Z'
issues:
- issue_id: I-001
  category: missing-invariant
  severity: high
  description: 'The ''citation fabrication rate'' (Goal, §4.4, §7) is not computable
    from what is persisted: only the unverified count is stored, with no denominator
    (total citations per answer). Worse, entire row classes validate to 0 by construction
    — no-snippet answers (canned text), the keyless-dev LLM_NOT_CONFIGURED path, and
    the llm_failed fallback text all yield unverified_citations=0 — so avg_unverified_citations
    moves with citation volume and the mix of answerless rows, not fabrication propensity.
    The SPEC''s headline metric (''first faithfulness metric'') is delivered in name
    but not in measurement semantics; it needs at least a total-citations field or
    a view predicate restricting to rows where an LLM answer with citations was actually
    produced.'
  status: accepted
  disposition_reason: null
- issue_id: I-002
  category: undefined
  severity: high
  description: '§4.3/§5 pass ''<the stream''s own error flag>'' as llm_failed — but
    no such flag exists: event_stream (api.py:758) sets no error variable; the inner
    LLM exception handler (api.py:847) swallows the exception anonymously, and the
    outer except (api.py:862) yields an error event and never reaches the done/record
    point. The SPEC neither defines where this flag is set nor its semantics relative
    to the two distinct failure paths, so ''§5: llm_failed=True is recorded'' is not
    implementable as written.'
  status: accepted
  disposition_reason: null
- issue_id: I-003
  category: unverifiable-claim
  severity: high
  description: 'Acceptance §7 claims ''Every /search/answer and every streamed answer
    lands a search_log row'' — contradicted by the design''s own mechanics: record_search
    persistence is best-effort with failures swallowed (§5 keeps this unchanged),
    the stream''s outer exception path (api.py:862) exits before the record point,
    and a client disconnect closes the SSE generator so the post-done record never
    runs. ''Every'' is both false under normal web-chat behavior (user navigates away
    mid-answer) and untestable given fire-and-forget persistence; acceptance should
    be stated as best-effort coverage with the known loss modes named.'
  status: accepted
  disposition_reason: null
- issue_id: I-004
  category: risky-assumption
  severity: medium
  description: §4.3 places record_search 'after the terminal done event is prepared/yielded',
    assuming the async generator resumes past its final yield. Under ASGI cancellation
    or client disconnect, GeneratorExit is raised at that yield and the signal is
    silently dropped — on exactly the flagship surface the SPEC exists to instrument,
    and biased toward the most interesting sessions (aborted/slow answers). Recording
    before yielding done, or in a finally block, avoids the fragile ordering; the
    SPEC pins the fragile one as the design.
  status: accepted
  disposition_reason: null
- issue_id: I-005
  category: untestable-requirement
  severity: medium
  description: §6 exempts the only genuinely new wiring — the stream's record_search
    call — from automated testing ('verified live... rather than via a DB-heavy unit
    harness'). 'Verified live' has no pass criterion, no artifact, and does not run
    in CI, so a regression that silently re-opens the exact measurement blind spot
    this SPEC closes would go undetected. The stream generator can be exercised in
    a test via the ASGI test client with a fake LLM; the signal-emission path is assertable
    without a live deployment.
  status: accepted
  disposition_reason: null
- issue_id: I-006
  category: missing-invariant
  severity: medium
  description: 'NOT NULL DEFAULT 0 plus the explicit no-backfill non-goal makes ''not
    measured'' indistinguishable from ''measured, zero fabrications'': pre-migration
    rows still inside the 7-day v_search_health window, and all rows from paths/periods
    where citation validation didn''t run, are averaged into avg_unverified_citations
    as zeros. A NULLable column (NULL = not measured) or a view-level predicate is
    needed to preserve the measured/unmeasured distinction the metric depends on.'
  status: accepted
  disposition_reason: null
- issue_id: I-007
  category: undefined
  severity: medium
  description: '§4.3''s latency_ms ''<from a start stamp>'' is undefined for the stream:
    neither the start point (handler entry vs. first yield) nor the stop point (done
    event prepared vs. yielded) is stated, and total SSE duration includes LLM token
    streaming and client consumption pace. These rows land in the same p95_latency_ms
    aggregate as non-stream request latencies with incomparable semantics; the distinct
    path value separates the groups but the SPEC never defines what the stream''s
    latency measures.'
  status: accepted
  disposition_reason: null
- issue_id: I-008
  category: unverifiable-claim
  severity: low
  description: 'The motivating claim ''the deferred reranker is demand-pull-gated
    on exactly these signals'' is not established by either linked ADR: ADR-0006 gates
    its Slice 2 on v_entropy_signals (a different view), and ADR-0004 discusses the
    A2A consumer gate. No source for the reranker↔search_log gate is cited, so the
    SPEC''s ''this makes the improvement pullable'' framing rests on an unreferenced
    decision.'
  status: accepted
  disposition_reason: null
- issue_id: I-009
  category: risky-assumption
  severity: low
  description: §5 relies on 'the view is CREATE OR REPLACE' for the v_search_health
    change, which in PostgreSQL only succeeds if new columns are appended at the end
    with all existing columns' names/types/order unchanged. The SPEC doesn't state
    this ordering constraint; a natural placement of avg_unverified_citations among
    the other avg_* columns would make migration 005 fail on an existing database
    while passing on a fresh init.sql, splitting dev/prod behavior.
  status: accepted
  disposition_reason: null
approved_by: LivingLikeKrillin
approved_at: '2026-07-11T19:10:43Z'
---

