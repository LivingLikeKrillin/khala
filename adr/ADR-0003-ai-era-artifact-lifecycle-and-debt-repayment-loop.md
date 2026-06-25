---
id: ADR-0003
type: adr
title: The AI-era artifact lifecycle and the debt-repayment loop
status: proposed
date: 2026-06-26
tags:
- debt
- ai-era
- lifecycle
- cognitive-debt
- ken
- ingest
- accountability
linked_adrs:
- ADR-0002
---

# ADR-0003: The AI-era artifact lifecycle and the debt-repayment loop

## Status

**Proposed** — this ADR records *how Khala operates in the AI era*: the artifact
lifecycle it assumes and the loop by which the named cognitive-debt enemy is actually
serviced. It **extends ADR-0002** (it *designs how to fill* the *empty leg* that ADR-0002
named but did not design); it does **not** supersede it — the mission framing of ADR-0002
stands. It
ships **zero new product code**; it names a direction whose implementation is gated on a
real pulling signal (the PFPlay team dogfood — see *Demand-pull*). It is reversible.

## Date

2026-06-26

## Context — why now

ADR-0002 named cognitive debt as the **empty leg** — *"nobody understands the system the
org ships"* — and deliberately stopped at naming it: *"This ADR names the direction only.
It does NOT design it."* Two things have since become concrete and force the design:

1. **`ken` exists and is exactly that instrument.** `ken/README.md`: it *"measures whether
   a named human can currently **vouch** for an artifact — not via a rubber-stamp click,
   but by passing graded, grounded comprehension questions generated from the artifact's
   actual content."* A passing vouch binds to the artifact's `content_hash` and goes
   **stale** when the artifact changes; per-question mastery rides a spaced-repetition
   ladder (`ken/src/ken/schedule.py`); the org metric is **cognitive-debt coverage** plus
   the **orphan list** (artifacts with no current voucher). It never consults git history,
   so it is **AI-authorship-safe**. This is, near-verbatim, ADR-0002's definition of the
   missing instrument.

2. **The artifact lifecycle itself changed shape under AI.** Pre-AI, design artifacts were
   *few, large, and milestone-gated* — written expensively by hand, so they were scarce,
   long-lived, and canonical. With AI producers (Claude Code), decision documents are
   *frequent, fine-grained, and continuous* — a stream of point-in-time records with a
   short half-life, superseded session to session. The unit shrank, the frequency
   exploded, and the comprehension that used to come free from hand-authoring evaporated
   (the mechanism Storey, arXiv:2603.22106, formalizes as cognitive debt).

The honest consequence — stated here as a **working assumption**, not yet a measured fact:
**almost no human reads the plans an AI proposes**, so designing as if a human will
manually curate the stream is a fiction. (This premise is falsifiable and should be
confirmed against a real signal — e.g. a logged rate of un-read / un-explainable AI
artifacts — before construction; cf. ADR-0002's "observed, logged rate" standard.) On that
assumption, the lifecycle is now **bimodal**, and Khala's ingest, governance, and
comprehension story must be bimodal too.

## Decision — the operating loop

Khala's behavior in the AI era is one loop:

> **auto-ingest the 99% stream → AI proposes load-bearing candidates → an accountable human
> promotes (declares accountability) → `ken` verifies via vouch (enforces accountability)
> → coverage / orphan.**

### 1. Bimodal artifact lifecycle

| Tier | What it is | How it is handled |
|---|---|---|
| **Stream** | High-frequency, AI-authored decision docs (session output); short half-life | **Auto-ingested as *memo*** — cheap, ungoverned, point-in-time, queryable substrate, prunable. **Not individually governed or vouched.** |
| **Canonical** | The rare load-bearing decisions (real ADR / DESIGN) | **Promoted** into the governed tier — approval gate, `content_hash`, **vouched via `ken`**. |

This is not new machinery: it is the explicit shape of the existing intake. The
`ingest-notion` command exists (`nexus/nexus/cli.py`) and routes through the external
intake; the **memo** property itself lives in the A2A `ingest_external_spec` skill
(`nexus/nexus/a2a/external_ingest_skill.py`), which indexes documents as *memo* with no
`approved_hash` provenance and anchors trust on `source_hash`. Promotion to a governed
type is a **separate, deliberate human act** (`promote_external`,
`specledger/src/specledger/promote.py`). ADR-0003 elevates this existing memo-default /
selective-promote pattern to the canonical operating principle.

### 2. Auto-ingest is a contract change, not a reading aid

The stream is auto-ingested **because humans will not read it** — not so that they will.
Auto-ingest swaps the failing contract *"a human reads up front"* for *"the system
retrieves the relevant fragment at point of need and grounds the answer in it."* This is
legitimate **only because** Nexus retrieval is grounded: it cites its evidence and refuses
when no evidence exists (the founding *grounded-answers-only* rule). For the stream,
"unread" is therefore acceptable: retrieval substitutes for reading.

### 3. Concentration raises debt *density* — the precondition for repayment

Diffuse debt is unmeasurable: cognitive debt smeared across 500 unread documents is
invisible, and **what cannot be measured cannot be repaid**. Concentrating the
load-bearing few raises debt **density**, which is precisely what makes `ken`'s
coverage/orphan metric function — it requires a **bounded critical set**. Auto-ingesting
the 99% as substrate is what shrinks the remainder enough for `ken` to grip it. The two
halves are one mechanism.

The concentration target is **importance × human vouch capacity**, not importance alone. A
vouch is real cognitive labor (re-vouch on `content_hash` staleness; spaced repetition).
If the "1%" is still larger than a named human can carry, the orphan list never converges
and you have only produced *denser unpaid debt*. The filter has a budget.

### 4. Promotion is an accountable human act; `ken` gives it teeth

The 99%→1% filter is the loop's single point of failure. It is split asymmetrically:

- **AI proposes** candidates ("this looks load-bearing") — cheap, handles the frequency.
- **An accountable human promotes** — the named person who can *answer for* the artifact.
  This is **not** the AI or the Claude Code session: an AI cannot be accountable, so the
  binding act requires a person's name. (Pattern: specledger's `critique`
  (`specledger/src/specledger/critique.py`) → human disposition → `approve`
  (`specledger/src/specledger/review.py`).)

Promotion and `ken` form one accountability chain on the **same named human**:

- **Promotion** = *"this is canonical and I answer for it"* — a *claim* of accountability.
- **`ken` vouch** = *"prove it — can you actually explain it?"* — *enforcement* of that claim.

Promotion alone is just a nicer rubber stamp: a drowning owner can declare accountability
without comprehension. **`ken` is what makes the claim honest.** Promotion and vouch must
therefore be **coupled** — by design (not yet by code), a promoted artifact with no current
voucher should land on the orphan hotlist. This promote→ken coupling does **not** exist
today (`ken` orphan-hood is computed only over artifacts already registered in `ken`,
`ken/src/ken/coverage.py`); wiring it is part of the unbuilt pipeline named in
*out of scope* below.

### 5. Identity implies named accountability

Promotion and vouch both require a *named, accountable person* — so identity is not merely
access control (anonymous → PUBLIC; token → INTERNAL) but the binding of *who answers for
what*. A unified cross-product identity (one account across Nexus and `ken`) is a natural
*implication* of this loop, but ADR-0003 does **not** decide or design that platform layer
— it is forward-pointed here and left to the dogfood-platform spec (*out of scope* below).

## The empty leg, now designed

ADR-0002's three-debt ↔ module table left the **cognitive** cell as *"— EMPTY LEG —"*.
This ADR **designs** how that cell is filled: `ken` is the intended servicing instrument,
and the loop above is how it is *to be* serviced. The empty-leg claim was falsifiable on
the absence of a per-artifact, human-sourced comprehension signal — and `ken`'s vouch +
coverage + orphan **is** that signal. But the leg is not yet *closed* in code: the
connective halves (the concentration heuristic and the promote→`ken` coupling) are unbuilt
(*out of scope* below). The leg is designed; closing it is the follow-on work.

## Consequences

**Positive**
- Human attention is concentrated on the load-bearing 1% instead of diffused across the
  stream — *attention concentration*, not just automation.
- Cognitive debt becomes **measurable** (coverage) and therefore **repayable**.
- A single accountability chain (promote → vouch) on a named human; no rubber-stamp exit.

**Costs / risks**
- The concentration filter is load-bearing; a bad filter repays the wrong debt or
  re-admits the rubber stamp at the promotion step (mitigated by `ken` coupling).
- Assigning ownership must be cheap, or promotion stalls when authorship is fuzzy
  ("Claude and I wrote this at 2am").
- Vouch is ongoing human labor; the critical set must be budgeted to a person's capacity.

## What this ADR does NOT decide (out of scope)

- The concrete concentration heuristic (how AI proposes candidates).
- The Claude Code auto-push pipeline implementation (the bimodal "stream → memo,
  promote → governed" pipeline) — a later spec/plan.
- Hosting / deployment of the shared team platform — gated on the dogfood pull.

These are implementation, gated on the demand-pull signal below.

## Demand-pull

The **anticipated** puller for this loop is the PFPlay team — who already feel the
accumulated-AI-debt risk — dogfooding the ecosystem on a shared hosted instance. This is a
stated intent, not yet a logged signal; it should be anchored to a concrete commitment
(the dogfood instance going live and producing usage) before construction begins.

**Design now, build on the gate.** Designing the loop now is cheap and reversible (this ADR
ships zero code). *Construction* of the out-of-scope items still honors ADR-0002's
discipline: ADR-0002 gated the cognitive-debt window on **gate ⓐ** — an observed, logged
rate crossing a threshold. The PFPlay dogfood is the *qualitative* pull that motivates the
design; it does not retire gate ⓐ. Build proceeds when the dogfood produces that observed
pull (the quantitative signal), not merely on the intent to dogfood.

## Relationship to other ADRs

- **Extends ADR-0002** (fills its empty leg; mission framing unchanged — not superseded).

## Review log (dry-run, 2026-06-26)

Adversarial critique pass. All seven load-bearing code citations resolved to real symbols
(7/7); the ADR-0002 relationship (extends, not supersede; no edit to the immutable accepted
record) was confirmed accurate. Verdict: **approve-with-fixes** — the blocking issues were
rhetorical over-claim, not factual fabrication. Dispositions below.

| id | sev | type | finding | disposition |
|----|-----|------|---------|-------------|
| I-001 | high | overreach | "The empty leg, now **closed**" asserted as done while the connective halves are unbuilt | **accepted** — retitled "now **designed**"; body now states the leg is designed, not closed in code |
| I-002 | medium | unsupported-claim | "almost no human reads the plans an AI proposes" stated as fact | **accepted** — reframed as a falsifiable *working assumption*, to be confirmed against a signal per ADR-0002's standard |
| I-003 | medium | risky-assumption | PFPlay dogfood (sole "real puller") uncited/unverifiable | **accepted** — downgraded to *anticipated* pull; flagged to anchor to a concrete commitment before build |
| I-004 | medium | contradiction | "design now" via PFPlay never reconciled with ADR-0002's gate ⓐ + threshold | **accepted** — added "design now, build on the gate": PFPlay is qualitative motivation; gate ⓐ still governs construction |
| I-005 | medium | overreach | "by construction, on the orphan hotlist" — no code couples promotion→ken | **accepted** — softened to "by design (not yet by code)"; named as unbuilt wiring |
| I-006 | medium | scope-creep | §5 cross-product "identity = spine / structural" forward-declares an unbuilt platform | **accepted** — trimmed to named-accountability principle + forward-pointer; unified identity left to the platform spec |
| I-007 | low | nit | citation paths imprecise (`review.py`/`critique.py`/`promote.py` under `src/`) | **accepted** — paths corrected, `critique`/`approve` split across the two files |
| I-008 | low | nit | `cli.py` "lands as memo" — memo property is in the injected ingest fn | **accepted** — `cli.py` now cited only for the command's existence; memo property cited to the A2A skill |
