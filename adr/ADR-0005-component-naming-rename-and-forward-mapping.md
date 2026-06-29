---
id: ADR-0005
type: adr
title: Component naming — Protoss-unit rename and forward-mapping layer
status: proposed
date: 2026-06-30
tags:
- naming
- components
- ecosystem
- branding
- protoss
linked_adrs:
- ADR-0002
- ADR-0004
---

# ADR-0005: Component naming — Protoss-unit rename and forward-mapping layer

## Status

**Proposed** — this ADR records a **decided-but-unimplemented** component rename and
establishes a **forward-mapping layer** so that the immutable accepted ADRs (and existing
code) keep their old names while new documents and (eventually) code adopt the new ones.
It ships **zero product code** and renames **zero files/packages**; it is purely the
canonical lookup table. It extends [[ADR-0002]] (Khala's identity) and follows
[[ADR-0004]] (which *named* the components — this ADR *fixes their names*). It is reversible.

## Date

2026-06-30

## Context — names accreted from mixed origins

The ecosystem's components were named at different times from different sources:
`Nexus`, `Archon`, and `Probe` are in-game **Protoss units** (StarCraft); `specledger`,
`mutqa`, and `ken` are not — they are descriptive or ad-hoc coinages. The roster is
therefore **half-themed and incoherent**, and the incoherence leaks into docs, the web
intro page, and conversation (an assistant cannot reliably guess which name is canonical).

Two constraints shape the fix:

1. **Accepted ADRs are immutable.** [[ADR-0002]] and [[ADR-0003]] are `accepted` and
   content-hash stamped; they use the old names (`specledger`, `ken`, `mutqa`). Rewriting
   them would break the content hash and the "accepted = immutable" invariant.
2. **Code still uses the old names.** Directories and packages (`specledger/`, `mutqa/`,
   `ken/`, `probe/`) are unchanged. A big-bang rename is out of scope and risky.

So the rename cannot be a find-and-replace. It needs a **single authoritative mapping**
that new material points to, while history and code keep old names until a deliberate,
separately-gated migration.

## Decision

### 1. Canonical name mapping (old → new)

| Old name | New name | Role | Symbol unchanged? |
|---|---|---|---|
| `specledger` | **Arbiter** | approval / governance gate (intent debt) | dir `specledger/` (for now) |
| `ken` | **Adept** | tested human comprehension (cognitive debt) | dir `ken/`, `ken-web/` (for now) |
| `mutqa` | **Probe** | mutation-driven test quality (technical debt) | dir `mutqa/` (for now) |
| `Probe` (PR/review analyzer) | **Observer** | multi-source review evidence | dir `probe/` (for now) |
| `Nexus` | **Nexus** | document index + GraphRAG | unchanged |
| `Archon` | **Archon** | live-code-constant fact-check | unchanged (`nexus/nexus/claims/`) |
| `Khala` | **Khala** | the alliance / shared link | unchanged |

### 2. The theme is **one faction**, and the mapping is **semantic, not cosmetic**

Every component becomes a Protoss unit, so the suite reads as a single coherent faction.
The choices are motivated by what each unit *is*, matched to what each tool *does*:

- **Arbiter** — the Protoss judge/caster → the **approval gate** that adjudicates intent.
- **Adept** — denotes mastery/skill → the **comprehension** instrument (can a human still
  *answer for* the artifact).
- **Probe** — the gathering/scouting worker → the **mutation prober** that pokes tests.
- **Observer** — the cloaked watcher → the **review/PR analyzer** that watches changes.
- **Nexus / Archon** already fit (the knowledge hub; the fused authority) and stay.

### 3. The `Probe` name is **reused** — flagged as a transitional hazard

The single most error-prone item: **"Probe" is reassigned.** It previously meant the
review analyzer (`probe/` directory); it now means the *mutation* tool (`mutqa/`). Until
the code migration lands:

- The `probe/` directory is **Observer** (new name), despite the path.
- There is no `probe/` directory for the *new* Probe yet — it remains `mutqa/`.
- Readers and agents MUST disambiguate "Probe" by **date/context**: pre-2026-06-30 prose and
  any path `probe/` = Observer; the renamed mutation tool = new Probe (still `mutqa/`).

This collision is the price of theme coherence; this ADR is its disambiguator.

### 4. Naming convention

- **Brand name** = capitalized Protoss unit (`Arbiter`, `Adept`, `Probe`, `Observer`).
- **Identifier / package** = lowercase under the `khala-` namespace
  (e.g. `khala-arbiter`, `khala-adept`) when packages are eventually renamed.
- In-game **Protoss units only** — the naming pool is constrained to that faction to keep
  the set closed and coherent.

### 5. Forward-mapping layer — how old and new names coexist

This ADR **is** the mapping layer:

- **Accepted/immutable ADRs (0001–0003) and existing code keep old names.** They are *not*
  edited. Any old name in them resolves through the table in §1.
- **`proposed` ADRs (incl. [[ADR-0004]]) keep their current text**; this ADR is their
  name key, not a patch.
- **New documents SHOULD use the new names**, optionally glossing the old name once
  (`Arbiter (formerly specledger)`) on first use during the transition.
- **Code, package, and directory renames are deferred** to a separate, explicitly-gated
  migration (out of scope below) — never a precondition for using the new names in prose.

## Consequences

**Positive**
- A coherent, single-faction roster; one authoritative place to resolve any name.
- Immutable accepted ADRs stay untouched (content hashes intact); no history rewrite.
- Conversation and new docs can adopt correct names immediately, code rename or not.

**Costs / risks**
- A **transitional period** where path `probe/` means Observer and `mutqa/` means Probe —
  genuinely confusing; mitigated only by this ADR being consulted.
- Drift risk: new docs may still use old names until the convention settles; the gloss
  habit (`Arbiter (formerly specledger)`) is the cheap countermeasure.

## What this ADR does NOT decide (out of scope)

- The actual **code/package/directory rename** migration (`specledger/` → `khala-arbiter`,
  `probe/` → Observer paths, `mutqa/` → Probe paths, etc.) — a later, separately-gated plan.
- The **web intro page** refresh to the new names (already queued separately).
- Any identifier/namespace migration in published artifacts.

These are implementation, deliberately deferred; this ADR only fixes the canonical names.

## Relationship to other ADRs

- **Extends [[ADR-0002]]** (Khala's identity/branding) and **follows [[ADR-0004]]** (which
  enumerated the components; this ADR names them). Supersedes none. Per §5, accepted ADRs
  retain old names **by design** — this mapping, not an edit, reconciles them.

## Review log (dry-run, 2026-06-30)

Self-critique pass before human review.

| id | sev | type | finding | disposition |
|----|-----|------|---------|-------------|
| I-001 | high | hazard | `Probe` reuse (old review tool vs new mutation tool) is a live ambiguity that could mislead readers/agents | **accepted** — promoted to its own section (§3) with explicit date/path disambiguation rule |
| I-002 | medium | scope | risk of implying a code rename is now mandated | **accepted** — §5 + out-of-scope state code/dir rename is deferred and never a precondition for prose use |
| I-003 | low | unsupported | "mapping is semantic not cosmetic" asserted | **accepted** — §2 gives the per-unit rationale (unit meaning ↔ tool role) |
| I-004 | low | consistency | old names appear in accepted ADRs | **accepted** — §5 forward-mapping: immutable ADRs keep old names, this ADR is the key, no edits |
