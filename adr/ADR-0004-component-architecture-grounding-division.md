---
id: ADR-0004
type: adr
title: Component architecture — grounding division, dual-mode, and dual deployment
status: proposed
date: 2026-06-26
tags:
- architecture
- components
- ecosystem
- grounding
- archon
- nexus
linked_adrs:
- ADR-0002
- ADR-0003
---

# ADR-0004: Component architecture — grounding division, dual-mode, and dual deployment

## Status

**Proposed** — this ADR records the canonical *component model* of the Khala ecosystem:
what each component is, why none are redundant, and one repositioning decision (Archon).
It ships **zero new product code**. It extends [[ADR-0002]] (the debt mission) and builds on
[[ADR-0003]] (the operating loop) by naming the parts the loop runs on. It is reversible.

## Date

2026-06-26

## Context — "why does each of these exist, and do they overlap?"

The ecosystem accumulated six tool-shaped things (Nexus, Archon, Probe, specledger, mutqa,
ken) plus an interop layer (A2A). A fair, recurring question: are some redundant, and why
is each a separate component? This ADR answers it with the organizing principle that
actually distinguishes them, corrects an over-stated overlap claim about Archon, and
records the resulting structure.

## Decision

### 1. The organizing principle is **grounding division**, not feature partition

Each component grounds its answer in a **distinct truth source**. They do not overlap in
function; they divide the labor of grounding. Citations are point-in-time (2026-06-26).

| Component | Grounds its answer in | Real symbol |
|---|---|---|
| **Nexus** | derived **document index** (chunks/embeddings); a snapshot that can drift | `nexus/nexus/index/`, `search/hybrid.py` |
| **Archon** | **live code constant**, re-read at query time + drift hash | `nexus/nexus/claims/value_query.py`, `claims.yaml` (`value_source`, `value_ref_kind: code_constant`) |
| **specledger** | recorded **human approval** | `specledger/src/specledger/review.py` (`approve`), `critique.py` |
| **ken** | tested **human comprehension** (vouch) | `ken/src/ken/vouch.py` (`is_vouched`), `coverage.py` |
| **mutqa** | deterministic **mutation execution** (surviving mutants) | `mutqa/src/mutqa/` (cosmic-ray runner, `ledger.py`) |
| **Probe** | **multi-source evidence** (platform cohesion, API contract, org guidelines) | `probe/src/core/`, `probe/src/api/` |

Because each grounds in a different truth source, "they overlap" is false. The only real
near-boundary is **specledger vs ken**, and it is complementary by design: specledger
grounds in *approval* (intent debt — was it signed off), ken in *comprehension* (cognitive
debt — can a named human still explain it). Approval ≠ understanding; that gap is exactly
why both exist (see [[ADR-0003]]).

### 2. Archon is a **distinct engine**, not a Nexus duplicate — unify only the entry point, keep engine + grounding signal distinct

Earlier framing called Archon a near-redundant variation of Nexus. **That was wrong.** Nexus
grounds in a *document index* (can go stale); Archon grounds in a *live code constant*,
resolved at query time with drift detection (`value_query.py`: `resolver.resolve(value_source)`,
`drifted = value_symbol_hash != r.symbol_hash`). Their staleness properties are **opposite**.
This is why decision-grade fact-check (a value being debated in a meeting) needs Archon: Nexus
may return a stale planning-doc number; Archon returns the *currently enforced* constant, or
warns that its binding drifted.

**Decision — a partial merge across three layers, not a dissolution.** "Merge vs keep
distinct" is not one decision but three, and the answer differs by layer:

1. **End-user entry point — merge (may be hidden).** One knowledge entry point; the user need
   not know "Archon" is a separate tool. Archon stops being marketed as a co-equal fifth
   pillar (it currently lives as the `nexus/nexus/claims/` sub-package, not a standalone
   product — verified; any separate branch is not point-in-time-resolvable from the repo).
2. **Answer grounding signal — kept distinct *and visible to the user*.** Even behind one
   entry point, an Archon answer must still surface *as* a live-code-constant fact-check
   (current value + authority + drift warning), visibly distinct from a Nexus
   document-retrieval answer. This is **not** an implementation detail to hide: that
   freshness/authority signal *is* Archon's value (decision-grade calibration). Hiding the
   *tool name* is fine; hiding the *grounding character* would erase the very distinction
   that justifies the engine, collapsing it back into possibly-stale doc retrieval.
3. **Engine + internal representation — kept distinct.** The live-constant engine stays its
   own module (`nexus/nexus/claims/`, `value_query.py`); answers are typed by grounding
   source internally (`code_constant` vs document index). Not dissolved into the RAG pipeline.

So Archon is **not** fully absorbed: only the entry point unifies, while the engine, the
internal answer typing, and the user-facing grounding signal stay distinct. The intent
distinction (casual info access vs decision-grade fact-check; the name "집정관/Archon") maps
onto the mechanism distinction (index retrieval vs live evaluation) — principled, not
cosmetic. (`claims.yaml` is already seeded with real sample-app constants, e.g.
`PlanPolicy.BASIC_MAX_PROJECTS`.)

### 3. Interaction modality and deployment differ by class

| Class | Components | Surface | How it is deployed |
|---|---|---|---|
| **UI-served** | Nexus web, ken-web, Archon (as Nexus mode — *target state*, §2) | human web UI (`nexus/nexus/web/`, `ken-web/web/`) | **hosted + served** (local + tunnel + tokens) |
| **Agent-wired** | specledger, Probe, mutqa | **no UI** (verified: 0 web files) — agent operates them | **wired into Claude Code** (MCP server / PreToolUse hook / CI CLI) |

**Dual-mode:** Nexus and ken are *both*. Nexus answers humans via the web UI **and** agents
via `nexus/nexus/mcp/server.py` + A2A. ken is vouched by a human via ken-web **and** its
comprehension questions are generated/graded by a Claude Code session (the agent-driven loop
needs no API key — see `ken/README.md`). The same tool serves both modalities.

**Consequence for dogfooding:** "dogfood all features" is **not one mechanism**. UI-served
tools are *hosted* for everyone (planners + engineers); agent-wired tools are *configured
into* each engineer's Claude Code (engineers only). Different audience, different deploy.

### 4. Flow: two tiers, multiple sources — specledger input, ken consumption

specledger is the natural **capture point for the AI-decision-document stream**: Claude Code
uses it directly, so each session's spec/ADR lands in its ledger (`record`). ken is the
**consumption** side (vouch on canonical). Documents live in two governance tiers (per
[[ADR-0003]] / org-doc-governance): **memo** (ungoverned, accumulating, queryable substrate)
and **governed/canonical** (approved, content-hashed, ken-vouched). Promotion memo →
governed is the accountable-human act ([[ADR-0003]]).

**Canonical is multi-source — not only the promoted stream.** Governed docs enter by either:
1. **Stream → promote**: the AI-decision stream lands as memo; an accountable human
   periodically promotes the load-bearing few to canonical (the [[ADR-0003]] loop).
2. **Direct injection from other sources**: already-authoritative docs arrive as (or are
   promoted directly to) canonical — external specs/ADRs authored elsewhere,
   governed-frontmatter filesystem docs, or the external-spec gateway's `promote_external`.
   These bypass the stream entirely.

**Status of the stream→memo link — decided, not yet coded.** The destination is **not** an
open question: [[ADR-0003]] decided the stream lands in Nexus at the **memo** tier and is
periodically promoted. What is missing is only the *mechanism*. Today specledger publishes via
`specledger/src/specledger/publish.py` **only at approve time** (carrying the approval
`content_hash` as `approved_hash` provenance); `record()` does **not** push the stream to
Nexus's memo path (`ingest_external_spec`). Wiring specledger to publish *recorded* docs as
memo at record time is follow-on implementation, gated on the dogfood — not a decision to
revisit.

**Caveat (verified):** even the canonical publish does not *enforce* approval — `publish()`
forwards the artifact's current `status` with no `APPROVED` check, and the Nexus governed
path gates on *capability*, not status. "Canonical-only" is today a **convention, not an
enforced invariant** (a status guard is follow-on work).

(Note: the partner team's human-authored Notion planning docs are a different intake from the AI stream
— they enter Nexus directly via `nexus ingest-notion`, classified by the deterministic
engine. Multiple intake paths converge on the same two tiers.)

### 5. A2A is an access layer, not a grounding tool

A2A is **not** a grounding component; it is the **entry point for end-user-operated agents**
to reach Khala (ADR-0001). Its justification is anticipatory — the industry trend is
"tools *for* agents," so a front door is kept ready. It has **no active consumer today**;
per the standing decision it stays minimal and is not extended until a real agent pulls it
(see [[khala-a2a-phase4-notify-approval]] discipline).

## Consequences

- A defensible answer to "why are these all separate": different grounding sources, not
  duplicated features. The suite is **concept-coherent**.
- Archon stops inflating the tool count; its surface unifies under Nexus while its engine
  survives.
- Dogfooding is correctly split into *hosting UI tools* vs *wiring agent tools*.

**Honest state.** Concept-coherence is not demand-validation. Only **ken** has a real puller
today (the partner-team dogfood, [[khala-operating-loop-and-partner-dogfood]]). The remaining "why
does this exist" reduces from *redundancy* (resolved: none, bar Archon-packaging) to
*demand* — the open question for specledger/Probe/mutqa is **"are they actually wired into a
real Claude Code workflow yet?"**, which the dogfood is meant to answer.

## What this ADR does NOT decide (out of scope)

- The actual Archon→Nexus surface merge work (a later spec/plan).
- The implementation that wires specledger to publish *recorded* (stream) docs to Nexus's
  memo path at record time (§4) — decided in [[ADR-0003]], not yet coded.
- Any new product code; all of the above is gated on observed dogfood pull.

## Relationship to other ADRs

- **Extends [[ADR-0002]]** (the debt mission) and **builds on [[ADR-0003]]** (the operating
  loop — this ADR names the components that loop runs on). Supersedes neither.

## Review log (dry-run, 2026-06-26)

Adversarial critique pass. Every cited file resolved (marquee mechanisms — `value_query`
drift hash, `claims.yaml` constant, `approved_hash` provenance — real); no contradiction
with ADR-0002/0003. Verdict: **approve-with-fixes** — one high over-claim, rest cosmetic.
Dispositions below.

| id | sev | type | finding | disposition |
|----|-----|------|---------|-------------|
| I-001 | high | overreach | §4 "publish sends **only approved** docs" — `publish.py` has no status gate; Nexus path gates on capability, not approval | **accepted** — reworded to "carries approval content_hash as provenance; canonical-only is a *convention, not an enforced invariant*"; status guard named as follow-on |
| I-002 | medium | unsupported-claim | Archon "lives as an **unmerged branch**" — not resolvable from repo | **accepted** — dropped the branch claim; kept the verified `nexus/nexus/claims/` sub-package fact |
| I-003 | low | contradiction | §3 table lists Archon-as-Nexus-mode as hosted UI while the merge is out-of-scope/unbuilt | **accepted** — marked *target state* in the table |
| I-004 | low | nit | `vouch.py` defines `is_vouched`, not `vouch` | **accepted** — cite tightened to `is_vouched` |
| I-005 | low | unsupported-claim | ken questions "generated/graded by Claude Code session" uncited | **accepted** — cited `ken/README.md` |
