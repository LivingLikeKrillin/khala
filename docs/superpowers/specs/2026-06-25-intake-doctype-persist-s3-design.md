# Design Spec — Intake 타입 보존 + 검색 노출 (S3, thin)

- **Date:** 2026-06-25
- **Status:** Design (사용자 승인 — thin scope)
- **Author:** LivingLikeKrillin (with Claude)
- **상위:** [[org-doc-governance-initiative]] S1 머지(PR #47) 위. 이 문서는 S3(intake)다.

## 1. Purpose / Scope

외부 intake가 CSF의 축-A 타입을 **저장**하고 검색에 **노출**하게 한다. 현재(S1 이후) 게이트웨이는 정규화된 `doc_type`을 *응답 artifact*에만 carry하고 `documents` 행에는 저장하지 않는다 — 분류기 추측값이 박히고 CSF 선언 타입은 유실된다.

**핵심 결정 — nexus는 tier 레지스트리가 필요 없다.** tier는 type에서 파생되며 파생은 거버넌스 경계(specledger, 레지스트리 보유)에서만 일어난다. nexus는 정규화된 축-A `doc_type`만 저장하면 된다 → S1의 작은 alias 미러(`_KIND_ALIASES`)로 충분, 교차-패키지 레지스트리 공유를 짓지 않는다.

**비목표(defer):** tier 차등 라우팅, T2 거버넌스 기계, auto-classification(호출자 선언 kind 신뢰; 없으면 NOTE). **default-memo 불변** — 모든 타입은 intake 시 Nexus 메모로 적재, 승격은 별도 인간 행위(promote_external).

"A 흡수"는 개념적 reframe(게이트웨이 = 이 이니셔티브의 intake 레이어). 코드 rename 없음.

## 2. Deliverable

1. **Intake 저장:** `_default_external_ingest_fn`이 ingest 후 정규화된 `doc_type`을 `documents` 행에 UPDATE(기존 `external_spec` label UPDATE 패턴 미러). **quarantine 행 제외**(default-deny 정신, 기존 label 규칙과 동일). idempotent 재예치 시에도 안전(멱등 UPDATE).
2. **검색 노출:** `SearchHit.doc_type` 필드 + 검색 SQL에 `d.doc_type`(documents 이미 LEFT JOIN) + `EvidenceSnippet.doc_type` + `format_for_llm` 헤더에 타입 1줄.

## 3. Units & 경계

| Unit | 책임 | 의존 | 독립 테스트 |
|---|---|---|---|
| intake doc_type 저장 | ingest 후 행에 축-A doc_type UPDATE | `normalize_csf_kind`(S1) | (DB 의존 — 단위는 normalize, 통합은 후속/E2E) |
| 검색 doc_type 노출 | SQL→SearchHit→EvidenceSnippet→LLM 포맷에 doc_type 전파 | 없음(순수 매핑) | assemble_packet 가 doc_type 전파, formatter 출력 |

## 4. Acceptance

1. `_default_external_ingest_fn`이 비-quarantine 외부 문서 행에 정규화된 `doc_type`을 저장(단위: UPDATE 호출/멱등; quarantine 행 미저장).
2. `assemble_packet`이 hit→snippet으로 `doc_type` 전파, `format_for_llm`이 노출.
3. 기존 검색/외부-ingest 테스트 회귀 없음(SearchHit 신규 필드는 기본값 `""`).

## 5. 향후

S4(Notion importer) — 이 intake 위에서 Notion 문서를 타입 보존하며 적재. nexus↔specledger 레지스트리 통합은 불필요(이 결정으로 소멸). tier 차등 행위는 demand-pull 시.
