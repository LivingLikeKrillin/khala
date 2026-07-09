# Design Specs

Ecosystem-level design specs for **Khala**. Specs detail *how* a decision recorded in
an [ADR](../adr) is implemented. They follow the [Arbiter](../arbiter) house
format (`SPEC-<slug>.md`, frontmatter `id/type/title/status/date`) and are meant to be
run through Arbiter's accountable-review gate (`record` → `critique` → human
disposition → `approve`) before implementation begins.

## Index

| ID | Title | Status | Implements | Date |
|----|-------|--------|------------|------|
| [SPEC-nexus-a2a-server-phase0-spike](SPEC-nexus-a2a-server-phase0-spike.md) | Phase 0 spike — Nexus A2A grounded-retrieval server | Draft | [ADR-0001](../adr/ADR-0001-adopt-a2a-inter-agent-interop.md) | 2026-06-18 |
| [SPEC-nexus-notion-reconciliation](SPEC-nexus-notion-reconciliation.md) | Notion deletion reconciliation — soft_delete/revive + root-scoped prune | Draft | [ADR-0002](../adr/ADR-0002-reframe-system-command-debt.md) | 2026-07-09 |

## Statuses

- **draft** — being written
- **in_review** — critique opened, dispositions pending
- **approved** — signed off and content-hash stamped; ready to implement
- **stale** — body changed after approval; needs re-review
