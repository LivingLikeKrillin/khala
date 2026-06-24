# Design Spec — 문서-타입 Taxonomy + 거버넌스 Tier 정책 (S1, spine)

- **Date:** 2026-06-25
- **Status:** Design (brainstorming output) — pending spec review + user approval
- **Author:** LivingLikeKrillin (with Claude)
- **Source of insight:** "노션 문서를 가져오고 싶다"는 실수요에서 출발 → 배치마다 "메모냐 거버넌스냐"를 손으로 정하는 것은 ad-hoc이라는 사용자 통찰 → **타입 체계를 정의하고 타입별 생애주기를 붙이면 import는 "분류 → 라우팅"이 된다.** 정책은 직관이 아니라 **업계 관행 딥리서치**(2026-06-25, 24/25 주장 확정)로 근거를 둔다.
- **Deliverable (이 S1):** ① 두-축 문서-타입 체계(taxonomy), ② 3-tier 거버넌스 모델 + 타입별 생애주기 정책, ③ 타입↔tier 배치 원리·표, ④ 모든 tier 공통 요구(owner·소스컨트롤·이슈추적·staleness), ⑤ 기존 khala 자산(specledger/Nexus 메모/외부-spec ingest)에의 매핑. **머신리더블 타입 레지스트리**가 S1의 구체 산출물.

---

## 0. 이니셔티브 맥락 — 이 문서의 위치

khala 정체성 정본(ADR-0002)은 '시스템 장악 = 수렴점(convergence point)이 되는 것' + 'AI 3대 부채(특히 문서/인지 부채) 관리'다. 사용자는 이를 구체화했다: **"SW 조직에서 중장기 관리가 필요한 모든 문서를 사용자가 밀어 넣고, khala는 타입별로 어떻게 관리·운용할지 베스트프랙티스/가이드라인을 제공한다."**

이 큰 그림은 의존 순서로 분해된다:

| # | 서브프로젝트 | 무엇 | 이 문서 |
|---|---|---|---|
| **S1** | **타입 taxonomy + tier 생애주기 정책** (spine) | 타입 체계 + 각 타입의 tier·생애주기 규칙 + 공통 요구 | ◀ **이 문서** |
| S2 | 타입별 베스트프랙티스/가이드라인 (knowledge) | 각 타입 저작·리뷰·supersede·drift 운용 매뉴얼 | 후속 |
| S3 | 인바운드 분류·라우팅 (intake) | 들어온 문서 → 타입 분류 → tier/생애주기로 라우팅. 기존 외부-spec ingest gateway(A) 흡수·확장 | 후속 |
| S4 | 소스 importer (transport) | Notion(첫 실수요) 등. `NotionSource` 완성/확장 | 후속 |

**demand-pull 기록:** 이 이니셔티브는 ADR-0002의 "부채 도구는 demand-pull 게이트를 override하고 적극 빌드"에 해당하며, 동시에 구체 소비자("노션 문서 import", S4)가 실재한다. 단 S1은 *정책 spine*이므로 코드 표면이 최소다(아래 §6: 양 끝 tier는 이미 구현).

## 1. Purpose

khala가 흡수하는 문서를 **타입으로 분류하고 타입마다 합당한 생애주기·거버넌스를 적용**하기 위한 *단일 정본 모델*을 정의한다. 이 모델이 없으면 S3(intake)·S4(importer)·기존 specledger/Nexus가 제각기 ad-hoc 결정을 반복한다. S1은 그 결정을 한 번, 근거 위에 고정한다.

비목표(이 문서가 정하지 않는 것): 타입별 *가이드라인 내용*(S2), 분류 *알고리즘*(S3), *전송*(S4), Tier-2 거버넌스 *기계의 구현*(후속 plan). S1은 **모델과 계약**만 정의한다.

## 2. 근거 (딥리서치 2026-06-25, 인용 기반)

핵심 발견(전부 적대적 검증 통과):

- **업계는 "타입별 생애주기"로 수렴.** ADR은 *불변(immutable) + supersede* 관행 — accepted 후 수정 금지, 변경은 새 ADR로 대체(arc42 §9, Nygard 2011, Fowler, AWS Prescriptive Guidance; 만장일치). RFC는 **계층적 거버넌스** — "substantial" 변경만 승인 게이트, 버그픽스·리팩터는 게이트 없음(Rust RFC 0002). Postmortem은 고정 콘텐츠 + *리뷰는 강한 규범이나 승인 게이트는 없음*(Google SRE Book).
- **doc rot/staleness가 지배적 실패모드.** 3,000+ GitHub 프로젝트 대다수가 outdated 참조 보유(Tan et al., EMSE 2023, arXiv:2212.01479); 문서 이슈의 39%가 up-to-dateness(Aghajani et al., ICSE 2019, 162개 이슈 유형 분류); Google GooWiki 폐기 시 ~90%가 수개월 무열람·무갱신.
- **최강 치료제 = docs-as-code**: owner 명시 + 소스컨트롤 + 변경 리뷰 + 이슈 추적(Software Engineering at Google, ch10). *단 단일 출처(Google)라 "보고된 효과"로 취급.*
- **두 분류 축은 별개.** Diátaxis(tutorial/how-to/reference/explanation)는 *user-facing 콘텐츠 형태*를 다루며 **내부 프로세스 문서(ADR·runbook·회의록)를 명시적으로 배제**한다(diataxis.fr). 따라서 단일 enum에 모두 욱여넣으면 안 된다.

정직한 공백: (a) **PRD 생애주기는 1차 표준이 없다** — 약한 근거로 정의. (b) 비-코드 문서의 **자동 staleness 신호는 미해결 연구 문제**. (c) docs-as-code "최선"은 단일 출처.

## 3. 두-축 타입 체계 (Taxonomy)

문서는 **두 직교 축**으로 기술된다. 단일 enum이 아니다.

### 축 A — 거버넌스 타입 (필수, tier를 결정)

열린 enum. 시작 어휘:

| 타입 | 정의 | 예시 |
|---|---|---|
| `ADR` | 되돌리기 힘든 아키텍처 결정의 근거 기록 | "Postgres를 쓴다" |
| `RFC` | 변경 제안(substantial change) | "A2A 프로토콜 도입 제안" |
| `DESIGN` | 기술 설계·명세(구현의 근거) | 이 문서, CSF 설계 |
| `PRD` | 제품·기획 요구(의도·범위) | "외부 spec 수렴 허브" |
| `RUNBOOK` | 운영 절차(how-to-operate) | "장애 대응 절차" |
| `POSTMORTEM` | 사후 분석(사건·근본원인·후속) | "DB 다운 포스트모템" |
| `NOTE` | 회의록·위키·자유 메모 | 브레인스토밍 메모 |

- **열림:** 새 타입은 추가 가능. 미지/미분류 타입은 기본 Tier 3(메모)로 안전하게 강등(default-deny와 같은 보수성).
- 기존 CSF `kind`(PRD\|SPEC\|ADR\|FLOW\|NOTE)는 축 A로 **흡수·정규화**된다(SPEC→DESIGN, FLOW→RUNBOOK 또는 NOTE로 정착; §6 마이그레이션).

### 축 B — 콘텐츠 형태 (선택, user-facing 문서에만)

Diátaxis: `tutorial` \| `how-to` \| `reference` \| `explanation`. **user-facing 문서에만** 부여하며 tier를 바꾸지 않는다(검색·표현 메타). 내부 프로세스 문서(ADR/RFC/...)에는 적용하지 않는다(연구 근거). 축 B는 **옵션** — S1은 필드를 예약만 하고, 실제 활용은 user-facing docs를 다루는 후속에서.

> **결정:** S1의 load-bearing 축은 A다. 축 B는 미래 user-facing 문서를 위한 *예약 필드*로만 도입한다(YAGNI — 지금 강제하지 않음).

## 4. 3-Tier 거버넌스 모델

### 배치 원리 (자의적 표가 아니라 규칙)

> **다른 작업이 그 문서의 안정성·승인에 의존하는 정도만큼 거버넌스가 강해진다.**

이 자가 tier를 결정한다. 의존이 강할수록(구현·후속결정이 근거로 삼음) 승인 게이트와 불변성이 필요하고, 의존이 없을수록(참고·기억) 가볍게 둔다.

### Tier 정의

| Tier | 의미 | 생애주기(근거 기반) | 축 A 타입 |
|---|---|---|---|
| **T1 — 거버넌스** | 승인 게이트 + 불변 + supersede. 구현/후속이 이걸 근거로 삼음 | `proposed → 리뷰/승인 게이트 → accepted(불변) → 변경은 supersede → superseded/deprecated` | `ADR`, `RFC`, `DESIGN`, (승인된)`SPEC` |
| **T2 — 추적** | 리뷰는 하되 승인 게이트는 없음. 제자리 개정 + 버전 + **주기적 staleness/owner 재확인** | `draft → 리뷰(기대됨) → published → 주기적 재확인 → 개정(version++) → deprecate` | `PRD`, `RUNBOOK`, `POSTMORTEM` |
| **T3 — 메모** | 게이트 없음. 인덱싱·검색만, 옵션 staleness flag | `capture → (옵션) staleness flag → archive` | `NOTE`, 미분류 |

근거 매핑: T1 = ADR 불변+supersede(arc42/Nygard/AWS) + RFC 승인 게이트. T2 = postmortem "리뷰는 필수 규범, 승인 게이트는 없음"(Google SRE) + RFC의 "모든 변경이 게이트는 아니다". T3 = 의존 없는 참고 문서.

### Cross-cutting (모든 tier 공통, doc-rot 최강 증거가 지목)

1. **owner 필수** — owner 없는 문서가 stale의 직접 원인(Google GooWiki 90%). 미지정 시 ingest 거부 또는 `unknown`+경고.
2. **소스컨트롤·이슈추적** — 변경은 추적, 문제는 버그처럼 티켓.
3. **자동 staleness 감지** — tier별 다른 신호(§7 공백: 비-코드 신호는 미해결, 훅만 예약). drift breadcrumb는 기존 `promoted_from_source_hash` 패턴 확장.

## 5. khala 자산 매핑 — 신규 표면은 최소

| Tier | khala 현 자산 | S1이 추가하는 것 |
|---|---|---|
| **T1** | ✅ **specledger** (DRAFT/PROPOSED→critique→approve→`approved_hash` stamp + 게이트 + supersede). ADR/SPEC 이미 처리 | `RFC`·`DESIGN`을 T1 타입으로 등록(specledger `_KIND_TO_TYPE` 확장). 새 기계 없음 |
| **T2** | ⚠️ **빈칸**. drift 훅(`promoted_from_source_hash`)만 존재 | **유일한 진짜 신규** — 추적 생애주기(version·재확인·deprecate). 단 S1은 *모델/계약*만; 기계 구현은 후속 plan |
| **T3** | ✅ **Nexus 메모** (`external_spec` label, 인덱싱·검색) | 타입 메타(`doc_type=NOTE`)만. 기계 없음 |

**즉 S1의 코드 산출물은 (a) 타입 레지스트리 + (b) specledger T1 타입 확장**이 핵심이고, T2 기계는 별도 슬라이스로 분리한다.

### 타입 레지스트리 (S1의 머신리더블 산출물)

단일 정본 레지스트리(예: `document-types.yaml` 또는 specledger config)로 각 타입을 선언:

```yaml
types:
  ADR:        { tier: T1, lifecycle: governed,  immutable: true,  owner_required: true }
  RFC:        { tier: T1, lifecycle: governed,  immutable: true,  owner_required: true }
  DESIGN:     { tier: T1, lifecycle: governed,  immutable: true,  owner_required: true }
  PRD:        { tier: T2, lifecycle: tracked,   immutable: false, owner_required: true }
  RUNBOOK:    { tier: T2, lifecycle: tracked,   immutable: false, owner_required: true }
  POSTMORTEM: { tier: T2, lifecycle: tracked,   immutable: false, owner_required: true }
  NOTE:       { tier: T3, lifecycle: memo,      immutable: false, owner_required: false }
default_tier: T3   # 미지 타입은 메모로 안전 강등
```

S3(intake)·specledger·Nexus가 이 레지스트리를 **읽어** 라우팅·게이트를 결정한다. 정책이 코드에 흩어지지 않고 한 곳에 산다.

## 6. 기존 자산과의 정합 / 마이그레이션

- **CSF `kind` → 축 A:** 외부-spec ingest gateway(A)의 CSF `kind`(PRD\|SPEC\|ADR\|FLOW\|NOTE)를 축 A 어휘로 정규화. `SPEC→DESIGN`, `FLOW→RUNBOOK\|NOTE`. `promote_external`의 `_KIND_TO_TYPE`(현재 SPEC/ADR만)은 레지스트리 기반으로 일반화.
- **순수 additive:** 기존 governed publish 경로(approved_hash), Nexus 메모 경로는 의미 불변. T1/T3는 *이미 있는 것에 타입을 붙일 뿐*.
- **외부-spec gateway(A)는 S3로 흡수:** A의 "기본 메모, 선택 승격"은 이 모델의 특수 사례 — "들어오면 타입 분류 → T3 기본, T1/T2로 승격". A는 이미 그 한 경로(NOTE→메모, →promote)를 구현했다.

## 7. 정직한 공백·미해결 (deferral)

| 공백 | 처리 |
|---|---|
| PRD 생애주기 1차 표준 부재 | T2 일반 생애주기 적용 + S2에서 약한 근거(실무 사례)로 구체화 |
| 비-코드 문서 자동 staleness 신호 | **훅만 예약**(owner 재확인 주기 필드). 실제 감지 알고리즘은 후속 슬라이스(demand-pull) |
| 축 B(Diátaxis) 실제 활용 | user-facing docs 다루는 후속까지 예약 필드로만 |
| T2 거버넌스 기계 구현 | S1은 모델/계약. 구현은 별도 plan |

## 8. Units & 경계

| Unit | 책임 | 의존 | 독립 테스트 |
|---|---|---|---|
| **타입 레지스트리** | 타입→tier→lifecycle 선언(단일 정본) | 없음(선언적 데이터) | 스키마 검증 + 미지 타입→default_tier |
| **레지스트리 리더** | 레지스트리를 읽어 tier/정책 조회 API | 레지스트리 | 알려진/미지 타입 조회 |
| **specledger T1 확장** | `_KIND_TO_TYPE`를 레지스트리 기반으로 일반화(RFC/DESIGN 등록) | 레지스트리 리더 | RFC/DESIGN promote → 올바른 시작 상태 |

각 unit은 인터페이스만으로 "무엇을 하는가"가 드러나고 독립 테스트된다.

## 9. Acceptance (S1 완료 기준)

1. 타입 레지스트리가 §3·§4 모델을 선언하고 스키마 검증 통과.
2. 레지스트리 리더: 알려진 타입→올바른 tier, 미지 타입→`default_tier=T3`.
3. specledger `promote_external`가 레지스트리를 통해 T1 타입(ADR/SPEC/DESIGN/RFC)을 매핑(기존 SPEC/ADR 회귀 없음).
4. 외부-spec gateway(A)의 CSF `kind`가 축 A로 정규화되어 기존 E2E 회귀 없음.
5. **신규 거버넌스 기계 0 for T1/T3** — 기존 specledger/Nexus 재사용 증명.

## 10. 향후 (이 문서 범위 밖, 의존 순서)

- **S2 — 타입별 베스트프랙티스/가이드라인:** 각 타입 운용 매뉴얼(템플릿·리뷰주기·supersede 규칙). khala가 *제공*하는 지식 산출물.
- **S3 — intake 분류·라우팅:** 들어온 문서 타입 분류 → 레지스트리 기반 tier 라우팅. A를 흡수.
- **S4 — importer:** Notion(첫 소비자) 등. `NotionSource` 완성.
- **T2 기계 / staleness 감지:** demand-pull 신호 잡히면.
