# Design Spec — 타입별 운용 가이드라인 (S2)

- **Date:** 2026-06-25
- **Status:** Design (사용자 승인 — 비전의 미완성 절반)
- **Author:** LivingLikeKrillin (with Claude)
- **상위:** [[org-doc-governance-initiative]] S1(PR #47) 위. 사용자 비전 "khala가 타입별 운용 베스트프랙티스 제공"의 절반.

## 1. Purpose / Scope

각 축-A 문서 타입을 **어떻게 저작·관리·운용해야 하는지** 근거 기반(딥리서치) 가이드를 khala가 제공한다. 단 inert 문서가 되지 않도록 **소비 지점에 묶는다**:
1. **promote 시점** — `promote_external`이 승격 대상 타입의 가이드를 반환(결정하는 순간 제시).
2. **조회** — MCP `guide(type)` 도구로 단건 조회.

**비목표(defer):** 검색 답변에 가이드 부착(별도 소비점, 후속), 풀-length 템플릿 본문 생성(가이드는 *요지+근거+포인터*, 템플릿 전문은 후속), 비-축-A 타입 가이드.

**근거:** 2026-06-25 딥리서치(24/25 주장 확정). 가이드 각 항목은 그 근거에 직접 대응.

## 2. 가이드 내용 (타입별, 근거 대응)

각 타입 가이드 = **lifecycle 한 줄 + 핵심 규칙 + 근거 출처**. 간결(읽히게).

| 타입 | 가이드 요지(근거) |
|---|---|
| `ADR` | **불변+supersede.** accepted 후 수정 금지 — 바꾸려면 새 ADR로 대체(old→superseded). 5섹션(Title/Status/Context/Decision/Consequences). 상태: proposed→accepted→deprecated/superseded. (arc42 §9, Nygard 2011, AWS) |
| `RFC` | **계층적 게이트.** substantial 변경만 정식 리뷰·승인; 버그픽스·리팩터는 게이트 없음. active→complete(구현 후)→inactive(폐기). 승인≠구현 보장. (Rust RFC 0002) |
| `DESIGN` | **단일 목적 + 승인 게이트.** 한 문서 한 목적. 구현 근거이므로 리뷰·승인 후 발효. 변경은 supersede(T1). (SWE at Google ch10) |
| `PRD` | **추적·제자리 개정.** 1차 표준 없음 — 버전+owner로 추적, SPEC이 파생되므로 변경 시 하위 stale 점검(drift). 승인 게이트 없음(T2). (실무 합성) |
| `RUNBOOK` | **운영 절차·주기 점검.** how-to-operate. 코드/인프라 변경과 함께 갱신, 정기 staleness 재확인 필수(doc-rot 최대 피해 영역). (Aghajani ICSE'19) |
| `POSTMORTEM` | **고정 내용 + 리뷰.** 사건/영향/완화/근본원인/후속을 기록. 리뷰는 강한 규범(미리뷰 = 없는 것). **비난 없는(blameless)**. 승인 게이트는 없음(T2). (Google SRE) |
| `NOTE` | **메모.** 생애주기 없음 — 인덱싱·검색만. 정본이 되면 promote로 격상. |
| (cross-cutting) | 모든 타입: **owner 명시 · 소스컨트롤 · 이슈 추적 · 자동 staleness 감지**(doc-rot 최강 치료제 docs-as-code). (SWE at Google ch10) |

## 3. 저장 — guidelines 모듈

가이드 내용은 **specledger `guidelines.py`**에 축-A 타입 키 dict로 둔다(정책 데이터 `document_types.yaml`과 분리 — 정책 vs 산문). 접근:

```python
def guidance_for(type_name: str) -> str | None    # 축-A 타입 → 가이드 텍스트(미등록 None)
```

타입 정규화는 기존 `doctypes.normalize_kind` 재사용(레거시 SPEC→DESIGN 등 동일 규칙) → guidance_for는 normalize 후 조회. cross-cutting 가이드는 모든 반환에 공통 푸터로 덧붙임(또는 별도 상수).

## 4. 소비 지점

### 4.1 promote_external 반환에 guidance
`promote_external`의 반환 dict에 `guidance: str` 추가(승격된 축-A 타입의 가이드). 기존 키(`artifact_id/status/provenance_carried`) 불변 — 순수 추가.

### 4.2 MCP `guide` 도구
specledger `server.py`에 `@app.tool() guide(type: str) -> dict` 추가: `{type, tier, guidance}`. tier는 `doctypes.tier_of`, guidance는 `guidance_for`. 미지 타입 → tier=T3 + "메모(생애주기 없음)" 가이드.

## 5. Units & 경계

| Unit | 책임 | 의존 | 독립 테스트 |
|---|---|---|---|
| `guidelines.py` | 타입→가이드 텍스트 + `guidance_for`(normalize 경유) | `doctypes.normalize_kind` | 타입별 반환, 레거시 정규화, 미지 None |
| `promote_external`(수정) | 반환에 guidance 추가 | guidance_for | 반환 guidance 존재(기존 키 회귀 없음) |
| MCP `guide` 도구 | type→{type,tier,guidance} | doctypes, guidelines | 알려진/미지 타입 |

## 6. Acceptance

1. `guidance_for`: 각 축-A 타입→근거 가이드, 레거시 SPEC→DESIGN 가이드, 미지→None.
2. `promote_external` 반환에 `guidance` 포함(ADR 승격→ADR 가이드); 기존 키/상태 회귀 없음.
3. MCP `guide(type)`→{type,tier,guidance}; 미지 타입→T3+메모 가이드.
4. specledger 전체 회귀 통과.

## 7. 향후

검색 답변에 타입 가이드 부착 · 풀 템플릿 본문 · 가이드 자체를 거버넌스 문서로(자기참조) · staleness 자동 감지(가이드의 "정기 재확인"을 코드로).
