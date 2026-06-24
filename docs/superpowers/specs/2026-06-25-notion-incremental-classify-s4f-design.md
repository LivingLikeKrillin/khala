# Design Spec — Notion 증분 sync + auto-classification (S4-follow-up)

- **Date:** 2026-06-25
- **Status:** Design (사용자 승인 — 후속 (3) 요청)
- **Author:** LivingLikeKrillin (with Claude)
- **상위:** [[org-doc-governance-initiative]] S4(PR #49) 위. S4가 미룬 두 후속.

## 1. Purpose / Scope

S4 Notion importer를 두 방향으로 보강:
1. **증분 sync** — `since`(ISO8601 watermark) 이후 변경된 페이지만 적재. 매번 전체 재적재 회피.
2. **auto-classification** — 모든 페이지를 NOTE로 고정하던 것을, 제목 키워드로 축-A 타입을 **결정론적**으로 추론(미매치 NOTE).

**하드 제약:** classification은 **결정론**이어야 한다(nexus 규율 "LLM으로 classification 결정 금지"; 딥리서치도 내용-추론 미해결로 경고). → 제목 키워드 휴리스틱. LLM/콘텐츠-추론 없음.

**불변:** **default-memo** — 분류는 `doc_type` 메타를 정확하게 할 뿐, intake는 여전히 메모(T3 label, 승격은 별도 인간 행위). 분류가 거버넌스를 자동 트리거하지 않는다.

**비범위(defer):** Notion search API 기반 증분 최적화(현재는 page_ref로 last_edited 확인 후 필터 — 대역폭 최적화 아님), watermark 자동 영속(state file/DB) — CLI `--since` 수동 + report가 다음 watermark 반환, 속성(property) 기반 분류(제목 휴리스틱이 첫 단계).

## 2. 증분 sync

`import_notion(source, tenant, ingest_fn, since=None)`:
- 기존 루프(live_ids→page_ref) 유지 + **인라인 필터**: `since` 가 주어지면 `ref.last_edited <= since` 페이지는 skip(변경 없음).
- `ImportReport.watermark`: 처리한 ref 중 최대 `last_edited`(다음 실행의 `since`로 쓰도록 반환). 처리 0건이면 입력 `since` 유지.
- ISO8601 UTC 문자열 비교(사전식 = 시간순). `since=None` → 전체(기존 동작).
- NotionSource.list_changed 풀구현은 불필요(importer가 인라인 필터) → S4의 NotImplementedError 유지.

## 3. auto-classification (결정론)

`classify_kind(title: str) -> str` (순수):
- 제목의 **첫 토큰**(영숫자 외 분리)을 키워드 맵과 대조: `adr→ADR, rfc→RFC, prd→PRD, design→DESIGN, spec→DESIGN, runbook→RUNBOOK, postmortem→POSTMORTEM`.
- 미매치 → `NOTE`(보수적; default-memo와 정합).
- 첫 토큰만 보아 false-positive 최소화(예: "ADR-001: ..."→ADR, "Design Doc"→DESIGN, "Payment PRD"→NOTE).

`build_csf`는 하드코딩 `kind="NOTE"` 대신 `kind=classify_kind(title)` 사용. 나머지(provenance/hash)는 S4 그대로. 분류 결과가 known 축-A 타입이면 S3가 그 doc_type을 행에 저장, 미지면 S1 레지스트리가 T3로 강등(이미 보장).

## 4. CLI

`nexus ingest-notion` 에 `--since` 옵션 추가. 실행 후 `watermark` 를 출력해 사용자/자동화가 다음 `--since` 로 쓰게 한다.

## 5. Units & 경계

| Unit | 책임 | 의존 | 독립 테스트 |
|---|---|---|---|
| `classify_kind` | 제목 → 축-A 타입(결정론) | 없음(순수) | 키워드별 매핑 + 미매치 NOTE |
| `build_csf`(수정) | kind=classify_kind(title) | classify_kind | kind 반영 |
| `import_notion`(수정) | since 필터 + watermark | source(주입) | since 경계 skip, watermark 계산 |
| CLI `--since` | 옵션 통과 + watermark 출력 | import_notion | (smoke) |

## 6. Acceptance

1. `classify_kind`: 키워드 제목→해당 타입, 미매치→NOTE, spec→DESIGN 정규화(첫 토큰).
2. `build_csf`: 분류 제목이면 그 kind, 아니면 NOTE. 기존 한국어 제목("결제 기획")→NOTE 회귀 없음.
3. `import_notion(since=X)`: last_edited<=X 페이지 skip, 초과만 적재; report.watermark=최대 last_edited.
4. CLI `--since` 등록 + watermark 출력.
5. 전체 회귀: S4 기존 테스트 통과(since=None 기본 동작 불변).

## 7. 향후

Notion search API 증분(대역폭) · watermark 자동 영속 · 속성 기반 분류 · 다른 source.
