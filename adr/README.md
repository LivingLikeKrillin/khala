# Architecture Decision Records

Ecosystem-level Architecture Decision Records (ADRs) for **Khala** — decisions that
span more than one tool (Nexus, Observer, Arbiter, Probe). Single-tool decisions live
in that tool's own `docs/`.

These ADRs follow the [Arbiter](../arbiter) house format
(`ADR-NNNN-<slug>.md`, frontmatter `id/type/title/status/date`) so they can be run
through Arbiter's accountable-review gate (`record` → `critique` →
human disposition → `approve`).

## Index

| ID | Title | Status | Date |
|----|-------|--------|------|
| [ADR-0001](ADR-0001-adopt-a2a-inter-agent-interop.md) | Adopt A2A as Khala's agent-to-agent interoperability layer | Accepted | 2026-06-18 |
| [ADR-0002](ADR-0002-reframe-system-command-debt.md) | Reframe Khala around staying in command of your own system in the AI era | Accepted | 2026-06-23 |
| [ADR-0003](ADR-0003-ai-era-artifact-lifecycle-and-debt-repayment-loop.md) | The AI-era artifact lifecycle and the debt-repayment loop | Accepted | 2026-06-26 |
| [ADR-0004](ADR-0004-component-architecture-grounding-division.md) | Component architecture — grounding division, dual-mode, and dual deployment | Accepted | 2026-06-26 |
| [ADR-0005](ADR-0005-component-naming-rename-and-forward-mapping.md) | Component naming — Protoss-unit rename and forward-mapping layer | Accepted | 2026-06-30 |
| [ADR-0006](ADR-0006-nexus-entropy-spine.md) | Nexus entropy spine — version-aware supersession, retrieval containment, residual measurement | Accepted | 2026-07-01 |
| [ADR-0007](ADR-0007-component-rename-migration-landed.md) | Component rename migration landed — amends ADR-0005 §3 (path `probe/` is now the mutation tool, not Observer) | Accepted | 2026-07-11 |
| [ADR-0008](ADR-0008-keep-nexus-substrate-defer-onyx-adoption.md) | Keep Nexus's own substrate; defer the Onyx adoption question with named resume conditions | Accepted | 2026-08-01 |
| [ADR-0009](ADR-0009-the-embedding-model-block-of-adr-0008-is-lifted-what-the.md) | The embedding-model block of ADR-0008 is lifted — what the director declared, and what stays open | Accepted | 2026-08-05 |

> **Note on ADR-0005 §3:** ADR-0005's interim path/name disambiguation ("path `probe/` = Observer;
> new Probe is still `mutqa/`") is **stale** — the code rename has since landed. [ADR-0007](ADR-0007-component-rename-migration-landed.md)
> records the current state (`probe/` = the mutation tool `khala.probe`; `observer/` = the review
> analyzer `@khala/observer`). Read ADR-0005 §3 as history; ADR-0007 governs the current tree.

> **Note on ADR-0008 §6:** its block on **an embedding-model change** was lifted by the director on
> 2026-08-05 and the KURE-v1 swap shipped; [ADR-0009](ADR-0009-the-embedding-model-block-of-adr-0008-is-lifted-what-the.md)
> records the declaration, the evidence, and what stays open — resume condition (b), the mecab-ko
> third of the block, and two procedural defects in how the swap was gated. ADR-0008 is immutable and
> cannot forward-link, so this index is the pointer. Read ADR-0008 §6 and §2.6 together with ADR-0009.

## Statuses

- **proposed** — under discussion / awaiting review
- **in_review** — critique opened, dispositions pending
- **accepted** — approved and content-hash stamped (immutable)

> **Which status is authoritative.** The **ledger's frontmatter** is — this index reflects it. An
> ADR's *body* carries the status it was written with, and because accepted bodies are frozen the two
> cannot be reconciled by editing: most accepted ADRs still say "Proposed" (or "In review") in their
> body text. Arbiter enforces the immutability mechanically — editing an accepted artifact makes it
> report `tampered`, which is how an in-place amendment of ADR-0008 was caught on 2026-08-05.
> Amendments are carried by a successor record (ADR-0007 → ADR-0005, ADR-0009 → ADR-0008).
- **superseded** — replaced by a later ADR
- **deprecated** — no longer relevant
