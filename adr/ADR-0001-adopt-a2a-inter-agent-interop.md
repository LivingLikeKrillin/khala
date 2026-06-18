---
id: ADR-0001
type: adr
title: Adopt A2A (Agent2Agent) as Khala's agent-to-agent interoperability layer
status: accepted
date: 2026-06-18
tags:
- interop
- agents
- a2a
- mcp
- nexus
- ecosystem
linked_adrs: []
approved_by: LivingLikeKrillin
reviewed_at: '2026-06-18T10:30:00Z'
content_hash: sha256:ba389051b2fa779d43e798dfbdb8bbf0799c666b9518cb46771b8362fa621bf8
---

# ADR-0001: Adopt A2A (Agent2Agent) as Khala's agent-to-agent interoperability layer

## Status

**Proposed** — pending a Phase 0 spike and review. This ADR proposes a *direction
and a de-risking pilot*, not an ecosystem-wide commitment. Full adoption is gated
on the pilot's evaluation (see Implementation).

## Date

2026-06-18

## Context

Khala is "an alliance of tools that calibrates the AI era… not a tool you run; it is
the link the tools share." The ecosystem already ships several agent-facing tools that
each expose an **MCP server**:

- **Nexus** — Enterprise RAG + GraphRAG; the *context provider* for AI agents
  (grounded answers = answer + evidence + provenance + confidence).
- **Probe** — platform-aware PR analyzer that **consumes Nexus**.
- **specledger** — ADR/SDD governance MCP that **publishes approved docs to Nexus**.
- **mutqa** — mutation-driven test-quality harness.

Today, inter-tool wiring is **bespoke and point-to-point** (Probe → Nexus calls,
specledger → Nexus `publish`). That is fine at today's scale but does not generalize
to (a) Khala's own tools collaborating as *agents*, nor (b) **external enterprise
agents** discovering and delegating to Khala agents.

Two industry signals make this timely:

1. **2026 enterprise RAG is going agentic.** The production pattern is "agentic
   orchestration over a graph-backed knowledge base" — multi-step reasoning, query
   decomposition, and tool loops layered above retrieval. Nexus is well-positioned as
   the grounded substrate, but the agentic/collaboration layer above it is undefined.
2. **A standard for agent-to-agent communication now exists.** Google's **A2A
   (Agent2Agent)** protocol (announced 2025-04-09; donated to the **Linux Foundation**
   2025-06; 150+ supporting organizations by its one-year mark; HTTP + JSON-RPC 2.0;
   **Agent Card**-based discovery). Crucially, A2A is a *different layer* from MCP:
   **MCP connects agents to tools; A2A connects agents to agents.**

### Problem Statement

As Khala grows an agentic layer over Nexus, and as customers run heterogeneous agent
fleets, Khala needs a **standard, discoverable way for agents to collaborate** —
both internally (Khala tool ↔ Khala tool) and externally (3rd-party org agent ↔ Khala
agent, especially consuming Nexus's grounded context) — **without bespoke
point-to-point integrations** and **without sacrificing Khala's grounding/audit
guarantees** when crossing a protocol boundary.

### Constraints

- **Grounding is non-negotiable.** Khala's core principle is "System decides, LLM
  narrates"; every answer is bound to source/trace evidence. Any cross-agent response
  must still carry Nexus's evidence packet + provenance + confidence, and Agent Cards
  must advertise these guarantees. Default-deny + classification/clearance must be
  enforced **server-side**, never delegated to a calling agent.
- **Two languages.** Nexus/specledger/mutqa are Python; Probe is TypeScript. A2A's
  multi-language SDKs accommodate this.
- **Air-gap / enterprise.** Must run self-hosted with no external dependency. A2A is
  plain HTTP + JSON-RPC 2.0 and is self-hostable — consistent with the recent Nexus
  self-host (air-gap) work.
- **Do not duplicate MCP.** Keep MCP as the tool-access layer; introduce A2A only for
  agent-to-agent collaboration. Avoid re-exposing tools as agents "just because."
- **Lean maintenance.** Solo-maintainer reality → favor a low-commitment, reversible
  pilot over a big-bang rollout.

### Requirements

- A Khala agent (starting with Nexus) can be **discovered** via an Agent Card and
  **delegated** a task by another agent.
- Grounded responses survive the A2A boundary intact (evidence + provenance + confidence).
- The change is **flag-gated and reversible**; existing MCP and bespoke paths keep working.
- No regression to determinism, classification, or quarantine guarantees.

## Decision

Adopt **A2A as Khala's agent-collaboration layer, layered above the existing MCP
tool-access layer**, and prove it with a narrowly-scoped pilot before any
ecosystem-wide commitment.

### Key Points

1. **Two-layer model:** MCP = agent ↔ tool; **A2A = agent ↔ agent**. They are
   complementary, not competing. Khala tools keep their MCP servers.
2. **Nexus leads as an A2A *server*.** Publish an Agent Card advertising a
   "grounded knowledge retrieval" skill; A2A task results carry the existing
   `NexusResponse` evidence packet (answer + evidence_snippets + provenance + confidence).
   Reuse Nexus's existing FastAPI app to host the A2A HTTP/JSON-RPC endpoint.
3. **Grounding rides the protocol — at the emission boundary.** Agent Cards declare
   grounding + clearance semantics; classification/quarantine filters remain server-side
   (a caller can never widen its own clearance). A contract test asserts every A2A answer
   includes evidence. **Scope of the guarantee:** Nexus guarantees it *emits and enforces*
   evidence + provenance + confidence; it cannot guarantee a *consuming* agent reads or
   honors them. A2A guarantees delivery, not downstream use. Defending "the human stops
   judging" past Nexus's boundary is the consumer's responsibility — Nexus makes the
   grounded data unavoidable in the payload, but not unavoidable in the reader.
4. **Clients come later, only if the pilot pays off.** Probe and specledger migrate
   from bespoke calls to A2A task delegation in subsequent phases — gated on evaluation.
5. **Reversible & flagged.** Everything ships behind a feature flag; MCP and current
   direct integrations remain the default until A2A is proven.

### Implementation Details

Phased, each phase independently valuable and a decision gate:

- **Phase 0 — Spike (this ADR's commitment).** Stand up a minimal **Nexus A2A server**
  (Agent Card + a single `retrieve_grounded` skill) behind a flag, mapping
  `NexusResponse` → A2A task artifacts. Hand-drive it from one external A2A client.
  *Exit criteria:* a 3rd-party A2A agent can discover Nexus, delegate a query, and
  receive answer **with** evidence/provenance/confidence intact; latency overhead vs.
  the MCP path is acceptable. **Quantitative go/no-go thresholds are defined in
  [SPEC-nexus-a2a-server-phase0-spike](../specs/SPEC-nexus-a2a-server-phase0-spike.md)
  §3 and are not restated here** — that spec is the measurable gate for this phase.
- **Phase 1 — First internal client.** Make **Probe** an A2A client of Nexus, replacing
  one bespoke call. Compare maintainability/observability vs. the direct path.
- **Phase 2 — External exposure + auth.** Agent Card + token auth; enforce
  classification/clearance + default-deny for external callers (reuse Nexus's existing
  policy filter). Audit every cross-agent task.
- **Phase 3 — Governance flows.** specledger `publish` / approval notifications as A2A
  tasks, if Phases 0–2 validate the model.

Pin a specific A2A protocol/SDK version; keep the A2A surface isolated behind an adapter
so protocol churn does not leak into Nexus core (mirrors the existing
`EmbeddingService` / `LLMService` wrapper discipline).

## Consequences

### Positive

- **Standards-based interop** with strong, neutral governance (Linux Foundation, 150+
  orgs, major-cloud integration) — future-proof vs. bespoke glue.
- **External agents can consume Khala's grounded context** — Nexus becomes a
  discoverable, delegatable grounding provider in any A2A-speaking fleet.
- **Decouples integrations** — removes O(n²) point-to-point wiring as the ecosystem grows.
- **Aligns with the 2026 agentic-RAG direction** and directly realizes Khala's thesis
  ("the link the tools share").
- **Reuses existing assets** — Nexus FastAPI host, evidence packet, classification filter.

### Negative

- **More surface area** to build, secure, and maintain (a solo-maintainer cost).
- **Two protocols** (MCP + A2A) to reason about and document.
- **Grounding must be deliberately preserved** across the boundary — a new failure mode.
  And even when preserved, **honoring** the evidence is the consuming agent's
  responsibility; Nexus's "human stops judging" defense does not automatically extend
  past its own emission boundary.
- A2A is a **young standard**; some churn is likely.

### Risks

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| A2A spec/SDK churn breaks the integration | Medium | Medium | Pin version; isolate behind an adapter; keep flag-gated until stable |
| Grounding/evidence lost crossing the A2A boundary | Low | High | Contract tests assert evidence+provenance present on every A2A answer; map `NexusResponse` 1:1 to artifacts |
| Security exposure when external agents call Nexus | Medium | High | Default-deny + server-side classification/clearance; token auth on Agent Card; full audit; never trust caller-asserted clearance |
| Scope creep (rebuild everything on A2A) | Medium | Medium | Phased gates; MCP + bespoke paths remain default; commit only per-phase exit criteria |
| Effort outweighs payoff at current scale | Medium | Medium | Phase 0 is a cheap, reversible spike with explicit exit criteria; abandon cleanly if value is unproven |
| A2A SDK pulls transitive deps / assumes a registry or discovery server, breaking air-gap | Medium | Medium | Audit the pinned SDK's dependency tree before adoption; require a fully self-hostable path; treat any external-call requirement as a Phase 0 fail |

## Alternatives Considered

### 1. MCP-only (re-expose collaboration as tools)

Keep a single protocol and model agent collaboration as MCP tool calls.

**Pros:** one protocol; already built; no new dependency.
**Cons:** MCP is *agent ↔ tool*, not *agent ↔ agent* — no standard peer discovery or
task delegation between agents; doesn't address external agent collaboration.

**Rejected because:** it solves the wrong layer; multi-agent collaboration and external
interop are exactly what A2A standardizes and MCP does not.

### 2. Status quo — bespoke point-to-point integration

Continue with direct Probe→Nexus and specledger→Nexus wiring.

**Pros:** simplest; no new dependency; works today.
**Cons:** O(n²) integrations as tools multiply; no external reach; no standard discovery
or capability advertisement.

**Rejected because:** it does not scale with the ecosystem and offers no path for
external agents to consume Khala's grounded context.

### 3. A different agent protocol (ACP, ANP, …)

Adopt an alternative agent-communication standard.

**Pros:** alternatives exist and are worth tracking.
**Cons:** materially less adoption, governance, and cloud integration than A2A.

**Rejected because:** A2A has decisive ecosystem momentum and neutral (Linux Foundation)
governance; betting on a less-adopted standard adds risk without benefit.

### 4. Do nothing / wait indefinitely

**Pros:** zero cost now.
**Cons:** misses the agentic-RAG window; external agents cannot discover/consume Khala
grounding; bespoke debt keeps accruing.

**Rejected because:** *full commitment* is deferred, but doing literally nothing forfeits
a cheap option to de-risk; a Phase 0 spike captures the upside at low cost.

## References

- [Announcing the Agent2Agent Protocol (Google Developers Blog)](https://developers.googleblog.com/en/a2a-a-new-era-of-agent-interoperability/)
- [A2A one-year milestone — 150+ orgs, cloud, production (Linux Foundation)](https://www.linuxfoundation.org/press/a2a-protocol-surpasses-150-organizations-lands-in-major-cloud-platforms-and-sees-enterprise-production-use-in-first-year)
- [Agent2Agent (Wikipedia)](https://en.wikipedia.org/wiki/Agent2Agent)
- [Agent-to-agent protocol comparison: A2A, MCP, ACP, ANP (Zylos Research)](https://zylos.ai/research/2026-02-15-agent-to-agent-communication-protocols/)
- [Enterprise RAG Guide 2026 — modular, GraphRAG & agentic patterns (Synvestable)](https://www.synvestable.com/enterprise-rag.html)
- Khala `README.md` — ecosystem thesis ("the link the tools share")
- Nexus `CLAUDE.md` — "System decides, LLM narrates", grounding & classification principles

## Notes

- This ADR is governed by **specledger** conventions (`adr/ADR-NNNN-<slug>.md`,
  frontmatter `id/type/title/status/date`, status `proposed`). Run it through
  `critique` → human disposition → `approve` to move it to `accepted`, per the
  accountable-review gate.
- Scope is intentionally *ecosystem-level interop*. A separate spec should detail the
  Phase 0 Nexus A2A server (Agent Card schema, skill contract, `NexusResponse` →
  artifact mapping) before implementation.

### Review log (dry-run, 2026-06-18)

A pre-registration accountable-review pass against the specledger rubric
(`risky-assumption, missing-invariant, unverifiable-claim, scope-creep,
adr-contradiction, undefined, untestable-requirement`). Dispositions:

| Issue | Category | Disposition | Note |
|---|---|---|---|
| I-001 | risky-assumption | accepted | Clarified grounding guarantee scope (emission, not downstream use) in Key Point 3 + Negative. |
| I-002 | undefined | accepted | Phase 0 exit now delegates quantitative thresholds to SPEC §3. |
| I-003 | risky-assumption | accepted | Added SDK transitive-dependency / air-gap risk row. |
| I-004 | scope-creep | **deferred** | Reason: Phases 1–3 are explicitly labelled non-committal and gated; kept for roadmap visibility. Revisit if the ADR is split. |

> This is a dry-run record. When specledger is registered, run `critique` → `approve`
> to produce the canonical sidecar and stamp the content hash.
