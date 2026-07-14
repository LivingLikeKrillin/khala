---
target: SPEC-nexus-llm-usage-capture
critiqued_hash: sha256:5b7cbdf27f4fd665ccb7cee6b091a0309d9b805c5bec8065ec8472d1c059d718
critiqued_at: '2026-07-14T02:18:37Z'
issues:
- issue_id: I-001
  category: risky-assumption
  severity: high
  description: 'The Goal (§1) opens with "Every LLM call already returns token usage"
    — but §2 states `_ClaudeCodeBackend` returns `{"text": …}` only, and §3 maps claude-code
    to `Usage(None, None, None, model)`. Per project memory the keyless dev backend
    defaults to `NEXUS_LLM_PROVIDER=claude-code`, so under the default dev/CI backend
    the entire feature yields all-None usage and zero cost. The premise is false for
    the default backend, and the SPEC never states that cost capture is effectively
    inert until a live Anthropic key is configured.'
  status: accepted
  disposition_reason: null
- issue_id: I-002
  category: undefined
  severity: high
  description: The `model` string stored in `Usage.model` and used as the `compute_cost`
    pricing-lookup key is never defined. Anthropic's response typically carries a
    date-suffixed model id (e.g. `claude-sonnet-4-6-YYYYMMDD`) while `config.yaml`
    pricing is keyed by a bare `<model>` (e.g. `claude-sonnet-4-6`). If the returned
    id does not match a pricing key, `compute_cost` silently returns `None`, so cost
    is always `None` in production while every unit test (using a chosen mock model
    string) passes. The mapping between the provider-returned model id and the pricing
    key must be specified.
  status: accepted
  disposition_reason: null
- issue_id: I-003
  category: risky-assumption
  severity: medium
  description: §3 claims `generate()` = `(await generate_full(...)).text` makes "behaviour
    identical, one code path," and §4/§6 promise `generate() -> str` is unchanged/non-breaking.
    But routing the plain text path through `generate_full` newly injects pricing-config
    loading and `compute_cost` into the shared path used by text-only callers (`a2a/server.py`,
    `cli.py`). A missing/malformed `llm.pricing` block or an exception in cost computation
    would now surface through `generate()` to callers that previously had no such
    dependency. The "identical behaviour" invariant is asserted, not guaranteed.
  status: accepted
  disposition_reason: null
- issue_id: I-004
  category: missing-invariant
  severity: medium
  description: The `usage_out` list-mutation contract is only defined for successful
    stream completion ("appends exactly one `Usage` at end"). Behaviour is undefined
    when the stream raises mid-way, is abandoned, or is only partially consumed —
    in those cases the list stays empty, yet §3 says the stream path "reads it at
    the done event" with no defined value for the empty/error case. The done-event
    handler's expected behaviour on an empty `usage_out` must be specified.
  status: accepted
  disposition_reason: null
- issue_id: I-005
  category: untestable-requirement
  severity: medium
  description: Acceptance (§6) requires that `generate_full`/`stream(usage_out=…)`
    "surface real input/output tokens," but every test in §5 injects a fake client/transport
    and the dev environment is keyless (no `ANTHROPIC_API_KEY`), so no test exercises
    real provider-reported usage. "Real" is unverifiable in CI; the requirement should
    be reworded to "passes through provider-reported tokens" or backed by a live-key-gated
    integration test.
  status: accepted
  disposition_reason: null
- issue_id: I-006
  category: undefined
  severity: medium
  description: Behaviour when `config.yaml` has no `llm.pricing` section, a malformed
    entry, or a partial entry (only `input_per_mtok`) is unspecified beyond "cost
    None if model absent." Additionally, a `usage` dict with `cost_usd = None` cannot
    be distinguished between "model called but unpriced" and "model called but tokens
    unknown (claude-code)" — both collapse to the same surface with no reason field,
    undermining the stated "unknown ≠ 0" discipline for downstream consumers.
  status: accepted
  disposition_reason: null
- issue_id: I-007
  category: risky-assumption
  severity: low
  description: '`compute_cost` assumes `config.yaml` pricing is populated, current,
    and expressed per-million-tokens (`input_per_mtok`). There is no validation or
    staleness guard: stale or hand-edited pricing silently yields wrong cost figures
    (not `None`), which is more dangerous than the None-on-absent case the SPEC carefully
    handles.'
  status: accepted
  disposition_reason: null
- issue_id: I-008
  category: unverifiable-claim
  severity: low
  description: The SPEC hardcodes brittle line references (`providers/llm.py:52`,
    `answer.py:113`) that will drift as the file changes and cannot be relied upon
    at review or implementation time, and uses the rhetorical "Cost is a total blind
    spot" as if it were a precise premise. These should be symbol/function references
    rather than line numbers.
  status: accepted
  disposition_reason: null
approved_by: LivingLikeKrillin
approved_at: '2026-07-14T02:20:22Z'
---

