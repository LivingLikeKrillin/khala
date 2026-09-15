# 설계 사양서 (Design Specs)

Khala 생태계의 시스템 아키텍처 및 구현 상세 사양서입니다. 각 사양서(SPEC)는 [ADR](../adr)에 기록된 아키텍처 결정이 *어떻게* 구현되는지 상세히 기술합니다. [Arbiter](../arbiter)의 표준 거버넌스 형식(`SPEC-<slug>.md`, 메타데이터 frontmatter `id/type/title/status/date`)을 준수하며, 코드 구현 착수 전 반드시 Arbiter의 다단계 검증 게이트(`record` → `critique` → 이슈 처분 → `approve`)를 거쳐야 합니다.

## 사양 색인 (Index)

| ID | 제목 | 상태 | 구현 대상 ADR | 일자 |
|----|-------|--------|------------|------|
| [SPEC-nexus-a2a-server-phase0-spike](SPEC-nexus-a2a-server-phase0-spike.md) | Phase 0 spike — Nexus A2A grounded-retrieval server | Draft | [ADR-0001](../adr/ADR-0001-adopt-a2a-inter-agent-interop.md) | 2026-06-18 |
| [SPEC-nexus-notion-reconciliation](SPEC-nexus-notion-reconciliation.md) | Notion deletion reconciliation — soft_delete/revive + root-scoped prune | Approved | [ADR-0006](../adr/ADR-0006-nexus-entropy-spine.md) | 2026-07-09 |
| [SPEC-nexus-notion-source-console](SPEC-nexus-notion-source-console.md) | Notion source console — endpoint-first source management, background sync, previewed deletion | Approved | [ADR-0006](../adr/ADR-0006-nexus-entropy-spine.md) | 2026-07-10 |
| [SPEC-nexus-document-lifecycle](SPEC-nexus-document-lifecycle.md) | Document lifecycle — origin, search, hide, and the inverse of every destructive act | Approved | [ADR-0006](../adr/ADR-0006-nexus-entropy-spine.md) | 2026-07-10 |

## 사양 상태머신 (Statuses)

- **draft** — 사양서 작성 중인 초기 상태
- **in_review** — 비평(Critique) 이슈가 등록되어 검토 및 처분이 진행 중인 상태
- **approved** — 인간 승인권자의 최종 서명 및 SHA-256 무결성 해시 스탬프가 발급되어 구현 게이트가 개방된 상태
- **stale** — 승인 완료 후 본문이 변경되어 무결성 해시가 불일치하므로 재검토가 필요한 상태
