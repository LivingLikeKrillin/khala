# Architecture Decision Records

Ecosystem-level Architecture Decision Records (ADRs) for **Khala** — decisions that
span more than one tool (Nexus, Probe, specledger, mutqa). Single-tool decisions live
in that tool's own `docs/`.

These ADRs follow the [specledger](../specledger) house format
(`ADR-NNNN-<slug>.md`, frontmatter `id/type/title/status/date`) so they can be run
through specledger's accountable-review gate (`record` → `critique` →
human disposition → `approve`).

## Index

| ID | Title | Status | Date |
|----|-------|--------|------|
| [ADR-0001](ADR-0001-adopt-a2a-inter-agent-interop.md) | Adopt A2A as Khala's agent-to-agent interoperability layer | Proposed | 2026-06-18 |

## Statuses

- **proposed** — under discussion / awaiting review
- **in_review** — critique opened, dispositions pending
- **accepted** — approved and content-hash stamped (immutable)
- **superseded** — replaced by a later ADR
- **deprecated** — no longer relevant
