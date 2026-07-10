---
id: ADR-0007
type: adr
title: Component rename migration landed — ADR-0005's deferred code/directory rename
  is complete
status: accepted
date: '2026-07-11'
tags:
- naming
- components
- ecosystem
- migration
- protoss
linked_adrs:
- ADR-0004
- ADR-0005
approved_by: LivingLikeKrillin
reviewed_at: '2026-07-10T16:55:02Z'
content_hash: sha256:201ca9aa17df63ec3eb9f4653a4af9d1173a81320a6a3551f244837b9a72802b
---

# ADR-0007: Component rename migration landed — ADR-0005's deferred code/directory rename is complete

## Status

**Proposed** — records that the code/package/directory rename [[ADR-0005]] explicitly deferred to "a
later, separately-gated plan" has since **landed** in code (PRs #78, #80, #82, #83). It ships no new
product code; it is the record that a previously-deferred migration is done, and it **amends**
[[ADR-0005]] by taking precedence over its interim §3 disambiguation. It does **not** supersede
ADR-0005 — that ADR stays `accepted` and its semantic name mapping (§1–§2) remains canonical. This
is an amendment on one point (migration status), not a replacement. It follows [[ADR-0004]] (which
enumerated the components).

## Date

2026-07-11

## Context — ADR-0005's "for now" is over, but its text is frozen

[[ADR-0005]] fixed the canonical old→new component names (`specledger`→Arbiter, `ken`→Adept,
`mutqa`→Probe, old `Probe`→Observer) and, because a big-bang rename was risky, **deferred the
code/package/directory migration** to a separate gate. To survive the interim it added §3, a
date/path disambiguation rule whose load-bearing clauses were:

- "The `probe/` directory is **Observer** (new name), despite the path."
- "There is no `probe/` directory for the *new* Probe yet — it remains `mutqa/`."

That interim has ended. The deferred migration ran and merged: `specledger/`→`arbiter/`,
`ken/`+`ken-web/`→`adept/`+`adept-web/`, and the atomic `probe/`↔`mutqa/` swap that moved the review
analyzer to `observer/` and the mutation tool into `probe/` (#78/#80/#82/#83). ADR-0005's §3 clauses
are therefore **inverted** relative to the current tree, yet ADR-0005 is `accepted` and
content-hash-stamped, so its text stays frozen — it cannot be edited to say the migration landed.

This is not cosmetic. An immutable ADR that literally reads "path `probe/` = Observer, new Probe is
still `mutqa/`" is a live trap: a reviewer (human or the Arbiter critic) reading ADR-0005 §3 against
today's tree derives a **false contradiction**. It happened twice while gating SPEC-probe-cli — the
critic flagged "the design's package is what the ADR calls mutqa, not Probe" as an ADR contradiction,
when in fact the migration had simply landed since ADR-0005 was written. This ADR removes that trap.

## Decision

### 1. The migration landed — the current canonical state

The rename is complete in code. This is **checkable, not asserted**: the table below names the
shipping directory and package for each component, and none of `specledger/`, `mutqa/`, `ken/`, or
`ken-web/` remains as a directory — inspect the tree to confirm. The mapping now holds in *paths and
packages*, not only in prose:

| Old name | New name | Directory | Python package | Node package |
|---|---|---|---|---|
| `specledger` | **Arbiter** | `arbiter/` | `khala.arbiter` (`khala-arbiter`) | — |
| `ken` | **Adept** | `adept/` | `khala.adept` (`khala-adept`) | — |
| `ken-web` | **Adept (web)** | `adept-web/` | `khala-adept-web` (api) | `@khala/adept-web` (web) |
| `mutqa` | **Probe** | `probe/` | `khala.probe` (`khala-probe`) | — |
| `Probe` (review) | **Observer** | `observer/` | — | `@khala/observer` |
| `Nexus` / `Archon` / `Khala` | unchanged | `nexus/` / (in `nexus`) / — | `nexus` | — |

The falsifiable anchor for any future reader: **component identity is the import path / directory of
the shipping code.** `khala.probe` is the cosmic-ray mutation tool because that is what the package
contains; `@khala/observer` is the review analyzer for the same reason. Naming disputes resolve
against the code, not against a frozen snapshot.

### 2. ADR-0005 §3 is amended; the disambiguation rule is inverted

The interim date/path rule in ADR-0005 §3 no longer applies and should not be followed:

- **`probe/` is the new Probe** (the mutation tool, `khala.probe`) — no longer Observer.
- **`observer/` is Observer** (the review analyzer, `@khala/observer`).
- The "disambiguate by pre-2026-06-30 date / path `probe/` = Observer" heuristic is **obsolete**.
  For current code, path = name. The date heuristic only ever helped read *historical* prose and
  keeps that narrow use.

### 3. How this coexists with immutable ADR-0005

ADR-0005 is **not edited** — its content hash stays intact and the "accepted = immutable" invariant
holds, exactly the discipline ADR-0005 itself established for ADRs 0001–0003. This ADR is the
*successor record*, not a patch:

- For the **semantic old→new name mapping**, [[ADR-0005]] §1–§2 remains canonical and unchanged.
- For the **state of the migration and the path/name relationship**, this ADR (0007) governs and
  takes precedence over ADR-0005 §3 and its "(for now)" / "deferred" qualifiers.

ADR-0005's status stays `accepted`, **not** `superseded` — the bulk of it (the name mapping) is
still in force; only its interim §3 is overtaken. Where the two appear to conflict about whether the
code rename has happened, ADR-0007 is newer and correct; ADR-0005's contrary clauses are historical,
describing the moment before the migration.

### 4. Guidance for readers, agents, and the Arbiter critic

Treat the component rename as **complete**. Do not derive a contradiction from ADR-0005 §3's frozen
interim language. Bind a component's identity to what its package/directory actually is today, and
cite this ADR when a document's compliance with the canonical model is questioned on naming grounds.

## Consequences

**Positive**
- The recurring false-contradiction trap (ADR-0005 §3 vs the current tree) is closed with a citable
  record; future SPECs need not re-argue it in a §0.
- The canonical current state (dirs + packages) is written down once, verifiable against the tree.
- Immutable ADRs stay immutable; no history rewrite.

**Costs / risks**
- One more ADR to consult. Mitigated by this being the *last* word on the rename — after it, path =
  name with no interim caveats.
- A reader who finds only ADR-0005 still hits §3's stale text, and ADR-0005 is immutable so it
  **cannot forward-link to this ADR**. Discoverability therefore rests on the two mechanisms that
  *can* exist: the ADR index (`adr/README.md`) lists ADR-0007 with a note that it amends ADR-0005 §3,
  and this ADR's `linked_adrs` points back to ADR-0005 so a reader arriving at 0007 sees the pair.
  Anyone landing on ADR-0005 alone is expected to consult the index, which is the standard entry
  point.

## What this ADR does NOT decide (out of scope)

- **The names themselves.** [[ADR-0005]] §1–§2 owns the semantic mapping; this ADR does not re-open
  it, only records that the migration to those names in code is done.
- **Editing any accepted ADR.** ADR-0005's text is deliberately left frozen.
- **Any remaining old-name occurrences in intentional history** (accepted ADRs 0001–0003, dated
  changelogs, run logs, archived-repo URLs) — those stay by design, per ADR-0005 §5.

## Relationship to other ADRs

- **Follows and amends [[ADR-0005]]**: keeps its name mapping (§1–§2), takes precedence over its §3
  interim disambiguation and its "deferred / for now" migration status. ADR-0005 stays `accepted`;
  this is a one-point amendment, not a supersession.
- **Follows [[ADR-0004]]** (component enumeration), whose pre-rename vocabulary (`mutqa` = the
  mutation tool) resolves through ADR-0005's table and this ADR's current-state table.
