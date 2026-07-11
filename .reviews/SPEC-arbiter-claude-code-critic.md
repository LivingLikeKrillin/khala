---
target: SPEC-arbiter-claude-code-critic
critiqued_hash: sha256:e85c078169927fddedad28fdbcc12f420d105b6d95b6f55a48885601b9e6d2b7
critiqued_at: '2026-07-11T17:09:59Z'
issues:
- issue_id: I-001
  category: missing-invariant
  severity: high
  description: §5 frames the doors-closed flags as the injection mitigation, but they
    only prevent host execution — not verdict corruption. An artifact carrying an
    injection can still steer the critic to return a clean/empty issues array, and
    the gate treats a well-formed empty array as a successful review. Fail-closed
    covers errors, not manipulated content; no invariant (canary rubric item, cross-check,
    mandatory human disposition on zero-issue reviews) protects review integrity.
  status: accepted
  disposition_reason: null
- issue_id: I-002
  category: untestable-requirement
  severity: high
  description: §8 acceptance is 'returns real issues from the host claude' — nondeterministic
    LLM output with no criterion for 'real'. A legitimate zero-issue review, a degraded
    model response, and an injection-suppressed review are indistinguishable under
    this acceptance test, and the 'live check' go-live gate is a one-off manual run
    that cannot be re-executed as a regression test.
  status: accepted
  disposition_reason: null
- issue_id: I-003
  category: risky-assumption
  severity: medium
  description: §3 pins the doors-closed invocation as verified on claude CLI v2.1.207,
    and §7's unit suite never spawns the real CLI. Flag renames, semantic changes
    (e.g. --allowed-tools "" meaning), or output-format changes in future CLI versions
    are only discovered at live gate time; there is no version check, no contract/smoke
    test against the installed CLI, and no stated minimum CLI version requirement.
  status: accepted
  disposition_reason: null
- issue_id: I-004
  category: risky-assumption
  severity: medium
  description: §1 calls the backend 'keyless' but it assumes a host claude CLI that
    is authenticated with available subscription quota. Behavior when the CLI is unauthenticated,
    its session expired, or the subscription is rate-limited is unspecified — the
    CLI may emit an interactive login prompt or non-JSON text, surfacing only as a
    generic timeout/parse CritiqueError with no actionable message distinguishing
    'not logged in' from 'bad output'.
  status: accepted
  disposition_reason: null
- issue_id: I-005
  category: undefined
  severity: medium
  description: §4.1/§6 rely on 'a timeout' but never define its value, whether it
    is configurable, or who sets it. Similarly no --model pin is specified for the
    claude -p invocation, so the critic's model — and thus review quality and reproducibility
    of gate outcomes recorded in the sidecar — silently depends on each host's CLI
    default.
  status: accepted
  disposition_reason: null
- issue_id: I-006
  category: unverifiable-claim
  severity: medium
  description: '§3 and §8 ground the design in self-referential evidence: ''already
    used to gate this SPEC — a throwaway ClaudeCodeCritic produced real issues with
    no key''. The throwaway script is not in the repo, the run is not reproducible,
    and the SPEC''s own gate being the acceptance evidence for the mechanism it proposes
    is circular — the claim cannot be verified by a reviewer or CI.'
  status: accepted
  disposition_reason: null
- issue_id: I-007
  category: unverifiable-claim
  severity: low
  description: §5 claims --no-session-persistence 'keeps artifact text off the host
    session logs'. That covers transcript persistence only; whether the CLI writes
    other local caches, debug logs, or telemetry containing the prompt is outside
    the SPEC's control and not verified — the privacy claim is stronger than the flag
    guarantees.
  status: accepted
  disposition_reason: null
- issue_id: I-008
  category: adr-contradiction
  severity: low
  description: Linked ADR-0004 names the component 'specledger' and cites specledger/src/specledger/critique.py
    and review.py as the grounding symbols, while the SPEC cites arbiter/src/khala/arbiter/critique.py
    and 'Arbiter' throughout, with no note reconciling the rename — the ADR's point-in-time
    citations no longer resolve against the tree the SPEC describes, weakening the
    'linked ADR' grounding.
  status: accepted
  disposition_reason: null
- issue_id: I-009
  category: undefined
  severity: low
  description: §3/§4.2 assert the MCP server.py 'constructs a critic similarly' and
    will switch to make_critic(), but unlike cli.py:124 no construction site, signature,
    or test is specified for the MCP path — the second of the two claimed construction
    sites is left vague, so the acceptance criteria never exercise the MCP surface
    keyless.
  status: accepted
  disposition_reason: null
approved_by: LivingLikeKrillin
approved_at: '2026-07-11T17:12:24Z'
---

