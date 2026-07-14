---
target: SPEC-nexus-llm-usage-persistence
critiqued_hash: sha256:d61bafb443e5785b185e7e82b6b0d59682c7ee0c2c61825c09148933e7545e03
critiqued_at: '2026-07-14T02:53:45Z'
issues:
- issue_id: I-001
  category: untestable-requirement
  severity: high
  description: 'Acceptance requires ''The three schema locations agree (startup DDL,
    init.sql, migration 006)'', but the only proposed guard (§5) asserts the 3 columns
    exist ''after ensure_search_log()''. That code path exercises ONLY db.py SEARCH_LOG_DDL
    — it never runs init.sql or migration 006. The stated invariant that all three
    locations agree is therefore not actually verified by any test, so the exact #136
    three-location-drift trap the SPEC names can still land undetected.'
  status: accepted
  disposition_reason: null
- issue_id: I-002
  category: risky-assumption
  severity: high
  description: Stream wiring (§3) says 'read usage_out[0] (present only on a successful
    priced call)'. On any non-priced / failed / claude-code-bridge call, usage_out
    is empty and usage_out[0] raises IndexError. No guard (empty-check / fallback
    to None) is specified, so the intended NULL path throws instead — and although
    §6 promises 'No request path can be broken', an unhandled IndexError in the stream
    wiring would break the stream answer path.
  status: accepted
  disposition_reason: null
- issue_id: I-003
  category: risky-assumption
  severity: medium
  description: extract_signals derives via subscript access usage["input_tokens"]
    / usage["output_tokens"] / usage["cost_usd"] (§3). This assumes every non-None
    AnswerResult.usage dict always contains all three keys. If a provider path emits
    a partial usage dict (e.g. tokens without a cost key), this KeyErrors instead
    of yielding NULL. Should specify .get()-style defaulting to preserve the NULL≠0
    contract.
  status: accepted
  disposition_reason: null
- issue_id: I-004
  category: undefined
  severity: medium
  description: 'Precedence ''explicit args win, else derive from AnswerResult, else
    None'' is stated per the citation-arg pattern, but behavior for PARTIAL explicit
    args is undefined: if the caller passes prompt_tokens explicitly but not cost_usd
    while an AnswerResult is present, is cost_usd derived from answer.usage (mixing
    an explicit token count with a derived cost) or forced None? This can silently
    produce inconsistent rows (explicit tokens + unrelated derived cost).'
  status: accepted
  disposition_reason: null
- issue_id: I-005
  category: undefined
  severity: medium
  description: The metric is named avg_cost_per_query but is defined as avg(cost_usd),
    which ignores NULL rows — i.e. it is the average over PRICED queries only, not
    per query. The name implies a denominator of all queries; a reader/operator will
    misread the number (e.g. many NULL/unpriced queries won't dilute it). Either rename
    (avg_cost_per_priced_query) or define the denominator explicitly.
  status: accepted
  disposition_reason: null
- issue_id: I-006
  category: risky-assumption
  severity: medium
  description: The Goal is 'Cost is still invisible over time' → make it visible,
    yet both new aggregates (avg_cost_per_query, total_cost) are scoped to 'the same
    7-day window' (§3/§6). A rolling 7-day view gives no cumulative/lifetime cost,
    so the stated goal of over-time cost visibility is only partially met by the delivered
    view. Either accept and note the limitation explicitly or justify why 7 days suffices.
  status: accepted
  disposition_reason: null
- issue_id: I-007
  category: untestable-requirement
  severity: medium
  description: Acceptance clause 'No request path can be broken by signal persistence'
    is a universal negative that no test in §5 exercises (the integration test only
    checks the persist/aggregate happy path). As written it is unfalsifiable — there
    is no described test that drives the failure/exception branch of the best-effort
    insert to prove request paths survive it.
  status: accepted
  disposition_reason: null
- issue_id: I-008
  category: missing-invariant
  severity: low
  description: 'The schema/derivation covers the (tokens set, cost NULL) ''unpriced
    model'' case but leaves the inverse unconstrained: nothing forbids a row with
    cost_usd set while prompt_tokens/completion_tokens are NULL. No invariant ties
    cost presence to token presence, so total_cost could sum costs whose token counts
    are unknown, weakening the interpretability of the aggregates.'
  status: accepted
  disposition_reason: null
- issue_id: I-009
  category: risky-assumption
  severity: low
  description: cost_usd is stored as DOUBLE PRECISION and aggregated with sum()/avg()
    (§3). Binary floating point accumulates rounding error over many small monetary
    values; for a cost-tracking signal that may later feed budgets/alerting (named
    as a follow-on non-goal), NUMERIC/DECIMAL would be the safer choice. Flag now
    since the column type is hard to change after data accrues.
  status: accepted
  disposition_reason: null
- issue_id: I-010
  category: unverifiable-claim
  severity: low
  description: §5 defers the schema guard to 'the existing DDL parity test, if any'
    — the SPEC does not establish whether such a parity test exists. This 'if any'
    leaves the guard's actual existence unverified; the SPEC should confirm the test
    is present or mandate creating one, otherwise the schema-sync acceptance criterion
    rests on an unconfirmed artifact.
  status: accepted
  disposition_reason: null
approved_by: LivingLikeKrillin
approved_at: '2026-07-14T02:55:26Z'
---

