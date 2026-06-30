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
| [ADR-0001](ADR-0001-adopt-a2a-inter-agent-interop.md) | Adopt A2A as Khala's agent-to-agent interoperability layer | Proposed | 2026-06-18 |
| [ADR-0002](ADR-0002-reframe-system-command-debt.md) | Reframe Khala around staying in command of your own system in the AI era | Accepted | 2026-06-23 |
| [ADR-0003](ADR-0003-ai-era-artifact-lifecycle-and-debt-repayment-loop.md) | The AI-era artifact lifecycle and the debt-repayment loop | Accepted | 2026-06-26 |
| [ADR-0004](ADR-0004-component-architecture-grounding-division.md) | Component architecture — grounding division, dual-mode, and dual deployment | Accepted | 2026-06-26 |
| [ADR-0005](ADR-0005-component-naming-rename-and-forward-mapping.md) | Component naming — Protoss-unit rename and forward-mapping layer | Accepted | 2026-06-30 |

## Statuses

- **proposed** — under discussion / awaiting review
- **in_review** — critique opened, dispositions pending
- **accepted** — approved and content-hash stamped (immutable)
- **superseded** — replaced by a later ADR
- **deprecated** — no longer relevant
