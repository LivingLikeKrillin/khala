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
| [SPEC-nexus-notion-reconciliation](SPEC-nexus-notion-reconciliation.md) | Notion deletion reconciliation — soft_delete/revive + root-scoped prune | Approved | [ADR-0006](../adr/ADR-0006-nexus-entropy-spine.md) | 2026-07-09 |
| [SPEC-nexus-notion-source-console](SPEC-nexus-notion-source-console.md) | Notion source console — endpoint-first source management, background sync, previewed deletion | Approved | [ADR-0006](../adr/ADR-0006-nexus-entropy-spine.md) | 2026-07-10 |
| [SPEC-nexus-document-lifecycle](SPEC-nexus-document-lifecycle.md) | Document lifecycle — origin, search, hide, and the inverse of every destructive act | Approved | [ADR-0006](../adr/ADR-0006-nexus-entropy-spine.md) | 2026-07-10 |

## Statuses

- **draft** — being written
- **in_review** — critique opened, dispositions pending
- **approved** — signed off and content-hash stamped; ready to implement
- **stale** — body changed after approval; needs re-review
