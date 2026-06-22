---
id: ADR-0002
type: adr
title: Reframe Khala around staying in command of your own system in the AI era
status: accepted
date: 2026-06-23
tags:
- identity
- debt
- ai-era
- ecosystem
- reframe
linked_adrs:
- ADR-0001
approved_by: LivingLikeKrillin
reviewed_at: '2026-06-22T18:45:59Z'
content_hash: sha256:893e3565a423c6349a3bc172b874075670bd4a480c08a65ced7b31c3e32015ed
---

# ADR-0002: Reframe Khala around staying in command of your own system in the AI era

## Status

**Proposed** — this ADR records a *positioning decision*, not an engineering
commitment. It ships **zero new product code**. Every capability it names is gated on a
real pulling signal (see *Follow-on backlog*). It is reversible: a later ADR may supersede
the framing if it proves wrong.

## Date

2026-06-23

## Context — why now

Khala was founded to answer the **two failure modes of the AI era**: *the machine lies*,
and *the human stops judging* (`README.md`). That second mode — output rubber-stamped
without understanding — already named, in plain language, what the wider discourse now
calls a **debt**.

This is sharpened by **Martin Fowler's "three debts of the AI era"** (2026-04-02), which
distinguishes **technical debt** (artifacts pile up faster than they can be maintained),
**cognitive debt** (the team no longer understands the system it ships), and **intent
debt** (why a thing was built — its constraints and trade-offs — becomes unrecoverable).

As AI becomes the *producer*, output arrives in bulk and the comprehension that used to
come for free from building by hand evaporates. Left untreated, these debts push a team
through a value trough before any payoff, and the human's centre of gravity has to move
from **production** to **verification** — and to actively recapturing intent.

The reframe's load-bearing claims — the module→debt mapping and the empty leg — rest on
Fowler's framework and Khala's own code.

Khala's users are, fundamentally, **people trying to understand their own service or
system better**. The three debts are precisely the forces that erode that understanding.
Khala already fights two of them. It has no window for the third.

## Decision — the mission

Khala's identity is restated as a **mission**:

> **Keep humans in command and comprehension of their own system in the AI era.**

Committed one-line identity (the others were considered and set aside):

- ✅ **"AI가 짓고, 당신이 이해한다." — *AI builds it. You understand it.***
- ⨯ "당신의 시스템을 끝까지 장악하라. / Stay in command of your own system." (strong, but
  command-only; understates comprehension)
- ⨯ "이해를 잃지 않게. / Never lose understanding." (true, but defensive in tone)

**Framing.** The mission is positive — *understanding and command*. The three debts are
its **enemy**. Khala is the **debt-servicing window (세금 납부 창구)**: the place that makes
paying down the AI era's unavoidable *verification tax* cheap. This deliberately does **not
demote** Nexus's grounded retrieval: grounding, governance, and verification are no longer
separate tools — they are all expressions of the one mission (understanding). It also
extends, rather than replaces, the founding "two failure modes" — *the human stops
judging* is simply cognitive debt named in 2026 vocabulary.

## The enemy — three debts ↔ Khala modules

Each cell cites a real symbol, checked against code as of 2026-06-23 (citations are
point-in-time and may drift as files move or rename).

| Debt | What it is | Khala's servicing window | Grounding (real code) |
|---|---|---|---|
| **Technical** | Artifacts pile up faster than they are maintained; next work slows | **mutqa** + **probe** | mutqa: mutation testing surfaces **survivors** = behavior no test covers; verdicts/waivers recorded in a **ledger** (`mutqa/src/mutqa/ledger.py`, `models.py` `Survivor`/`Verdict`) — the blocking gate (M3) is future. probe: PR-boundary **scope/concern-drift** detection (`probe/src/core/concern-drift.ts`, `scope-analyzer.ts`) + **API contract** lint/diff (`probe/src/api/oasdiff-runner.ts`, `spectral-runner.ts`, `spec-differ.ts`) |
| **Intent** | Why a thing was built — constraints, trade-offs — becomes unrecoverable | **specledger** | **`content_hash`** sign-off (`art.meta["content_hash"]`, stamped in `review.py`; carried to Nexus as approval provenance via `publish.py`) + critique → human disposition → approve (`review.py`) + PreToolUse gate (`hooks/pretooluse_gate.py`) that blocks edits until a spec is approved |
| **Cognitive** | *Nobody understands the system the org ships* | **— EMPTY LEG —** | Nexus supplies the *substrate* (grounded retrieval; evidence + provenance + confidence; `search_log` / `v_search_health` demand signals in `nexus/init.sql`) but **nothing measures or enforces human comprehension** |

Two supporting roles are not debts themselves:

- **Nexus** is the **Queryable substrate** — every answer carries evidence, provenance, and
  confidence; `search_log` / `v_search_health` already collect demand signals.
- **The Workflow adversarial sub-agent pattern** — parallel critical review × N, repeated —
  is the engine for **paying the verification tax cheaply** — parallel critical review by
  independent sub-agents, repeated until findings converge.

## The empty leg — cognitive debt

- **Definition.** The team — or, since Khala itself is built AI-native, the single human
  director — can no longer understand or *vouch for* the system being shipped.
- **Why no window exists.** Every other debt has a servicing point: specledger's approval
  gate, mutqa's survivor ledger, probe's PR checks. Comprehension has **none** — it is
  assumed, never measured. Being *Queryable* (you *can* look it up) is not the same as
  *understanding*. A comprehension instrument would, minimally, emit a per-artifact signal
  of whether a *named human* can correctly explain or vouch for a change — a signal sourced
  from the human, not retrieved from the document. No such signal exists in Khala today;
  that absence is what makes the empty-leg claim falsifiable.
- **Why it is the center of the mission.** Cognitive debt is the purest form of the enemy —
  *losing command of your own system*. Closing this leg is what completes the reframe.
- **Scope here.** This ADR names the direction only — **comprehension / command
  instrumentation (이해도·장악도 계측)**. It does **not** design it.

## Principles, re-placed under the mission

The existing principles still hold; they are now subordinated to the mission:

- **Grounded answers only / "system decides, LLM narrates"** → the *integrity layer* that
  makes recaptured understanding trustworthy.
- **Default-deny + quarantine** → protecting the substrate that understanding rests on.
- **demand-pull, not build-push** → restated as: *gate each debt-servicing feature on "is
  this debt actually accumulating? show the signal."* This is how Nexus already gated
  GraphRAG behind `search_log`, and it is the discipline that stopped A2A (ADR-0001) at the
  point it outran a real consumer.

This does **not** reclaim what ADR-0001 disclaimed. Nexus still only *emits* evidence and
cannot force a consumer to read it; the cognitive-debt window likewise does not *force*
comprehension — it *measures and surfaces* it so a human can choose to act. ADR-0002 makes
the debt visible and cheap to service; it does not guarantee that any individual judges.

## Taste = subtraction (self-discipline)

The value of this ADR is naming what Khala *is* and what it will *not* build yet. By Khala's
own demand-pull rule — *taste is subtraction* — this document adds **zero** maintenance
surface, and the cognitive-debt window is not built until a signal pulls it.

## Follow-on backlog — gated, not designed here

Three candidate directions for the cognitive-debt window. Each lists the **signal that must
pull** before any design work begins. **None is designed in this ADR.** Each gate is
declared fired by the director and recorded in that direction's first SPEC.

| # | Direction | Gate signal (must observe first) |
|---|---|---|
| ⓐ | **Comprehension meter (이해도 계측)** — emit a per-artifact signal of whether a responsible human can explain/vouch for a shipped change (illustrative form: a periodic quiz) | An observed, logged rate of AI-built merges the responsible human cannot, on re-read, correctly explain (behavior or rationale) crosses a set threshold in a rolling window. The observation mechanism — a lightweight comprehension log, analogous to `search_log` — is itself ⓐ's first sub-step; nothing downstream is built until it exists and crosses threshold |
| ⓑ | **System-understanding map (시스템 이해 맵)** — who/what understands which parts of the system (illustrative form: an org-level heatmap) | A multi-person consumer exists; single-director Khala does not pull this yet |
| ⓒ | **Run-time verification layer** — continuous verification of non-deterministic AI agents in production | Khala (or a consumer) ships an AI *agent product* whose run-time behavior needs guarding |

**Khala is where the signal would first appear.** Because Khala is built AI-native,
cognitive debt accumulates here first — so Khala is the natural *observation post*. This is
**not** a licence to build: per demand-pull (and the lesson that paused A2A), construction
still waits for gate ⓐ to fire against the observed threshold above. Dogfooding is where we
watch for the signal, not a substitute for it.

## Consequences

- **Changes:** the root `README.md` identity line and the docs-site landing gain the mission
  ("AI builds it. You understand it.") and the three-debts framing, **additively**. The
  founding "two failure modes" copy MUST be preserved verbatim (additive edits only,
  verified by `git diff`).
- **Does not change:** no product code, schema, endpoint, or skill; no module is renamed or
  removed; Nexus's standalone retrieval value is untouched.
- **Reversibility:** this is a positioning decision; a future ADR may supersede it.
- **Next:** the cognitive-debt window is opened only when a gate signal above fires.

## Review log (dry-run, 2026-06-23)

A pre-registration accountable-review pass against the specledger rubric
(`risky-assumption, missing-invariant, unverifiable-claim, scope-creep, adr-contradiction,
undefined, untestable-requirement`), dogfooded via an adversarial critic sub-agent because
the specledger MCP server is disabled in-session (`.claude/settings.local.json`).
Dispositions:

| Issue | Category | Severity | Disposition | Note |
|---|---|---|---|---|
| I-001 | unverifiable-claim | high | **accepted** | probe scope/concern-drift re-cited to `core/concern-drift.ts` + `scope-analyzer.ts`; `api/*` kept for API lint/diff only |
| I-002 | unverifiable-claim | low | **accepted** | mutqa cell now says verdicts/waivers recorded; M3 blocking gate marked future; "enforcement point" → "servicing point" |
| I-003 | unverifiable-claim | low | **accepted** | specledger stamps/emits `content_hash`; the `approved_hash` mapping is Nexus-side — reworded |
| I-004 | missing-invariant | medium | **accepted** | mapping promise changed to point-in-time ("checked as of 2026-06-23; may drift"); a CI check would add code (out of scope) |
| I-005 | undefined | medium | **accepted** | added a minimal falsifiable definition: a human-sourced per-artifact comprehension signal |
| I-006 | risky-assumption | medium | **accepted** | dogfooding reframed as *observation post*, not a licence to build; construction still waits for gate ⓐ |
| I-007 | untestable-requirement | medium | **accepted** | gate ⓐ given an observed threshold + named the comprehension log (analogous to `search_log`) as ⓐ's first sub-step |
| I-008 | untestable-requirement | low | **accepted** | gates declared fired by the director, recorded in the direction's first SPEC |
| I-009 | scope-creep | low | **accepted** | backlog mechanisms marked illustrative; "built on Nexus" commitment removed |
| I-010 | adr-contradiction | low | **accepted** | reconciled: window measures/surfaces, does not *force* comprehension; preserves ADR-0001's emission-only boundary |
| I-011 | missing-invariant | low | **accepted** | additive edit stated as a checkable constraint (two-failure-modes copy preserved verbatim; verified by `git diff`) |
| I-012 | risky-assumption | low | **accepted** | load-bearing claims grounded on Fowler's framework + Khala's own code; external talk material removed for copyright caution |

> This is a dry-run record (mirroring ADR-0001). When specledger is registered, run
> `critique` → `approve` to produce the canonical sidecar and re-stamp the content hash.
