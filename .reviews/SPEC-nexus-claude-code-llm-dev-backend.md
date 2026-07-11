---
target: SPEC-nexus-claude-code-llm-dev-backend
critiqued_hash: sha256:b1dea261d6497ae44b75d36bdd93d8e26cfb9cd5c9706e52636662fed04225e2
critiqued_at: '2026-07-11T16:32:50Z'
issues:
- issue_id: I-001
  category: risky-assumption
  severity: high
  description: The entire security section (§5) rests on a deny-all tools flag whose
    existence and exact semantics are deferred to implementation time ('the exact
    flag verified against the installed CLI during implementation'). If the installed
    `claude` CLI (v2.1.207, which also self-updates) has no true deny-all mode, or
    the flag's semantics change across auto-updates, the load-bearing prompt-injection
    defense collapses. A spec that calls this 'the one non-negotiable requirement'
    should verify the mechanism up front and pin the CLI version, not assume it.
  status: accepted
  disposition_reason: null
- issue_id: I-002
  category: missing-invariant
  severity: high
  description: 'Disabling built-in tools via an argv flag does not isolate `claude
    -p` from the developer''s user-level configuration: globally configured MCP servers
    re-introduce tools, user hooks (e.g. SessionStart hooks that execute shell commands)
    still fire, and CLAUDE.md/skills content is loaded into the turn. §5 asserts ''pure
    text completion with all tools disabled'' but specifies no invariant that the
    bridge run with an isolated config (clean settings dir, strict MCP config, hooks
    disabled), so the injection-to-host-execution path it exists to close may remain
    open through MCP/hooks rather than built-in tools.'
  status: accepted
  disposition_reason: null
- issue_id: I-003
  category: missing-invariant
  severity: medium
  description: The bridge has no authentication and must bind an interface reachable
    from the container network ('a host interface the container reaches'). Which interface
    is never pinned down; any other local process, any other container, or (if it
    ends up on 0.0.0.0, common for Docker Desktop reachability) any LAN peer can POST
    /v1/generate and both consume the developer's Claude subscription and inject arbitrary
    prompts. 'Binds locally, dev-only' is stated as intent but no token/allowlist
    invariant enforces it.
  status: accepted
  disposition_reason: null
- issue_id: I-004
  category: missing-invariant
  severity: medium
  description: 'No timeout or concurrency bound anywhere in the chain: a hung `claude
    -p` agent turn holds the bridge request and the Nexus API request open indefinitely,
    and N concurrent /search/answer calls spawn N parallel `claude` processes against
    a single subscription. The spec acknowledges each call ''spawns a full agent turn''
    but defines no subprocess timeout, request timeout, or max-concurrency invariant.'
  status: accepted
  disposition_reason: null
- issue_id: I-005
  category: risky-assumption
  severity: medium
  description: 'Routing server-side narration through the developer''s personal subscription
    session assumes the subscription tolerates it: rate limits are shared with the
    developer''s interactive Claude Code use (a few web-chat questions can starve
    the interactive session or vice versa), and serving an HTTP backend off consumer-subscription
    auth may conflict with usage terms even in dev. The spec treats ''no paid key''
    as pure upside and never addresses either constraint.'
  status: accepted
  disposition_reason: null
- issue_id: I-006
  category: untestable-requirement
  severity: medium
  description: The 'I-critical' security test only asserts that the deny-all flag
    appears in the argv the bridge would spawn. That pins the flag's presence, not
    its effect — it cannot detect that the flag is misspelled for this CLI version,
    ignored, or insufficient (MCP/hooks, see above). §8 explicitly scopes the live
    check to answer quality, so no test at any level verifies that tool use is actually
    impossible; the requirement as specified is verified only by proxy.
  status: accepted
  disposition_reason: null
- issue_id: I-007
  category: undefined
  severity: medium
  description: The bridge request schema includes `max_tokens?` but §4.3 never says
    how it is honored — `claude -p` has no direct max-tokens control, so the parameter
    is either silently dropped (a behavioral difference from the Anthropic backend
    that callers like llm/answer.py may rely on) or needs an unspecified mechanism.
    Similarly, `get_model_name()` for the claude-code backend is required to 'keep
    the same shape' but its return value (which model? the CLI default is unknown
    to the bridge) is never defined.
  status: accepted
  disposition_reason: null
- issue_id: I-008
  category: missing-invariant
  severity: medium
  description: '`claude -p` persists session transcripts to the host by default, so
    corpus document content fed into narration prompts accumulates in the developer''s
    local Claude history with no stated invariant to disable or scrub it. §7 guards
    against credentials leaking out of the bridge, but nothing guards document content
    leaking into host-side session state — a real concern for a bridge whose input
    is arbitrary ingested org documents.'
  status: accepted
  disposition_reason: null
- issue_id: I-009
  category: risky-assumption
  severity: low
  description: §6 mandates a hard raise at construction for an unknown NEXUS_LLM_PROVIDER,
    but LLMService is constructed no-arg inside request handlers (api.py:376, api.py:754).
    A typo in the env var therefore turns every /search/answer request into a 500,
    which sits awkwardly against the codebase's established graceful-degradation invariant
    (api.py:825 degrades to evidence-only on `configured == False`). Fail-fast is
    defensible, but the spec doesn't reconcile it with the existing degradation contract
    or move the check to startup.
  status: accepted
  disposition_reason: null
- issue_id: I-010
  category: unverifiable-claim
  severity: low
  description: §4.2 justifies the injectable-transport design as 'same pattern as
    the Slack bot / Probe CLI' — neither precedent is evidenced in the doc, and per
    ADR-0004 'Probe' is the multi-source evidence tool while the component rename
    (mutqa→Probe, old Probe→Observer) makes the referent ambiguous; a Slack bot appears
    nowhere in the linked ADR at all. The claim cannot be checked from the materials
    provided and may point at a component that no longer carries that name.
  status: accepted
  disposition_reason: null
- issue_id: I-011
  category: undefined
  severity: low
  description: 'Internal inconsistency on streaming granularity: §2 permits ''the
    whole answer once (or in coarse chunks)'' while §4.2 and the §7 test pin ''yields
    the full text once''. If coarse chunking is ever implemented under the §2 allowance,
    the pinned test breaks; the spec should commit to one behavior. Relatedly, whether
    the existing SSE endpoint''s consumers (web chat UI) render acceptably when the
    entire answer arrives as a single event is asserted, not specified or tested.'
  status: accepted
  disposition_reason: null
- issue_id: I-012
  category: adr-contradiction
  severity: low
  description: ADR-0004 §5 records the standing discipline that A2A 'stays minimal
    and is not extended until a real agent pulls it' (no active consumer today). The
    design doc lists `a2a/server.py:304` as a call site that silently gains the new
    keyless-narration capability when the env var is set. No A2A code changes, so
    this is borderline, but granting the consumer-less A2A path a new dev capability
    without noting the freeze at least deserves an explicit statement that this does
    not constitute A2A feature work.
  status: accepted
  disposition_reason: null
approved_by: LivingLikeKrillin
approved_at: '2026-07-11T16:36:29Z'
---

