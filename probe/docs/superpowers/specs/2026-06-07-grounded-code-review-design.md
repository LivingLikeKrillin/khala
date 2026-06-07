---
title: "Probe v0.6 — 그라운디드 코드 리뷰 (Grounded Code Review)"
date: 2026-06-07
status: draft
authors: [eisen]
supersedes: []
related:
  - probe/docs/superpowers/specs/2026-06-06-troubleshooting-grounding-design.md  # v0.5 — 같은 grounder 자산을 diff 입력으로 재사용
  - probe/docs/probe-v0.4-scope.md  # enrichWithKhala (수렴 대상)
  - khala/CLAUDE.md  # "맥락 기반 AI Agent(Code Review / Troubleshooting)의 context provider"
  - "[claude] mcp-tools/specledger"  # 승인 스펙 발행자 (specRefs seam 소스)
  - khala/docs/superpowers/specs/2026-06-06-domain-invariant-governance-design.md  # Archon(#17) — claim+code 발행자 (claimDrift seam 소스)
---

# Probe v0.6 — 그라운디드 코드 리뷰

## 0. 한 줄 요약

git diff를 입력받아, **정합 여부를 단정하지 않고** 변경 엔티티에 대한 조직 컨텍스트
(설계+관측 토폴로지, 엔티티 스코프 설계-관측 갭, 적용 규정, 승인 스펙, claim drift)를
하나로 묶은 **Review Grounding Pack**을 생성해 Claude(또는 사람)의 코드 리뷰 판단에
근거를 깔아주는 도구.

> **Probe는 비제너럴 조직 증거를 모은다. diff의 의미 추론과 정합 판정은 Claude가 한다.**

피보팅 2단계: v0.5(트러블슈팅 그라운딩)와 동일한 grounder 자산을 **에러 신호 대신
diff 입력**으로 재사용한다.

---

## 1. 배경 & 문제

### 1.1 왜 지금 이걸 만드는가

칼라 에코시스템 설계 의도(`khala/CLAUDE.md`): "맥락 기반 AI Agent(**Code Review** /
Troubleshooting)의 context provider가 최종 목표." v0.5가 Troubleshooting 자리를
채웠고, v0.6이 **Code Review** 자리를 채운다. 둘은 같은 그라운딩 골격을 공유한다.

### 1.2 핵심 철학 — 분업 경계 (NON-NEGOTIABLE)

이 작업의 출발점은 "제네릭 Claude 코드 리뷰보다 나은가, 그리고 *겹치지 않는가*"이다.

**(a) diff의 소스 레벨 추론은 Claude의 일이다 — Probe는 침범하지 않는다.**
"이 diff가 inventory 호출을 새로 추가한다" 같은 *소스 코드 의미 분석*(엣지/호출 추출,
로직 추론)은 제네릭 Claude Code가 이미 잘한다. Probe가 diff를 파싱해 엣지 델타를
추정하는 것은 **Claude의 영역을 침범**하는 안티패턴이다. **명시적으로 비목표(N1).**

**(b) Probe의 해자는 비(非)제너럴 조직 정보다.** Claude가 *구조적으로 볼 수 없는*
설계 그래프·실관측 trace·설계-관측 갭·조직 규정·승인 스펙·claim 상태를 변경 엔티티에
맞춰 취합해 건넨다. 그러면 판단 측 Claude가 "내가 diff에서 본 order→inventory 엣지가
Probe가 준 설계 그래프엔 없고, 이미 observed_only로 error_rate가 높다 → 미문서화
의존성을 코드로 굳히는 변경"이라고 *더 나은 판단*을 한다.

| 차원 | 제네릭 Claude 리뷰 | Probe + Khala |
|------|--------------------|---------------|
| diff 소스 의미/로직/엣지 추론 | ✅ 강함 | **위임 (경쟁/침범 안 함)** |
| 런타임 호출 토폴로지 | ❌ 코드만으론 모름 | ✅ `/graph` |
| **설계 vs 실관측(trace) 갭** | ❌ **구조적으로 불가능** | ✅ `/diff` (엔티티 스코프) |
| 적용 규정/런북 | ❌ 문서 접근 불가 | ✅ `/search` |
| 승인 스펙 정합 참조 | ❌ 승인 원장 접근 불가 | ✅ specledger 발행분 (seam) |
| core claim drift | ❌ claim 레지스트리 없음 | ✅ Archon (seam) |

### 1.3 v0.4와의 중복을 정직하게 처리한다 (수렴, not 병렬)

v0.4 `enrichWithKhala`는 **이미** 변경 서비스에 대해 (1) 규정 `/search`, (2) 영향
분석, (3) 설계-관측 갭(`/diff`)을 수집한다. 그러나 두 한계가 있다:

- **CLI `probe review`는 Khala를 안 쓴다.** `enrichWithKhala`는 MCP scope-check
  도구(`tools.ts`, `prompts.ts`) **안의 곁가지**로만 호출된다 — 리뷰 전용 표면이 아니다.
- 설계-관측 갭을 **전역 `/diff`**(`getDiff()` 인자 없음)로 가져온다 — 변경 엔티티로
  스코프되지 않아 노이즈가 크다. (엔티티 스코프 `entity_filter`는 v0.5에서 추가됨.)

따라서 v0.6은 **새 병렬 grounder를 만들지 않는다**(중복). 대신 `enrichWithKhala`를
**Review Grounding Pack으로 수렴/승격**한다: 전역→엔티티 스코프 diff 교정 + 스펙/claim
정합 차원 추가 + 곁가지가 아닌 독립 표면(CLI+MCP) + 증거 팩 재포장. 기존 MCP scope
도구는 이 공유 grounder를 쓰도록 위임시켜 중복을 제거한다(전역 diff 버그도 덤으로 교정).

### 1.4 산출물 소유권 (RACI — v0.5 §1.2 계승)

- **diff 소스 의미 분석/엣지 추출 = Claude 소유.** Probe는 안 함(§1.2a, N1).
- **`source_kind=code` / 코드 심볼 인덱스 / `claim↔code` drift = Archon 소유.** Probe는
  질의만(claimDrift seam). 자체 코드 인덱스 구축 금지.
- **critique→disposition→사인오프 원장/게이트 = specledger 소유.** Probe는 발행된 승인
  스펙을 **참조로 인용만**(specRefs), 정합 판정 안 함.
- **diff→엔티티 라우팅, 조직 그라운딩 조립, 리뷰 그라운딩 출력 = Probe 소유.**

> 패턴: **Probe = Khala 보편 소비자. specledger·Archon = Khala 생산자.**

---

## 2. 목표 & 비목표

### 2.1 목표
- G1. git diff → 변경 파일을 **service/entity로 라우팅**한다(소스 의미 분석 없이,
  파일 경로 귀속만 — 기존 `fileBelongsToService`).
- G2. 변경 엔티티 주변의 **설계+관측 토폴로지, 엔티티 스코프 설계-관측 갭, 적용 규정,
  승인 스펙 참조, 영향 범위**를 하나의 **Review Grounding Pack**으로 조립한다.
- G3. Khala 가용 수준에 따라 **티어(T0~T3)를 자가진단**하고 명시한다(침묵 강등 금지).
  v0.5의 `determineTier`/`getStatusProbe`를 공유(타임아웃 vs 단절 구분 포함).
- G4. v0.4 `enrichWithKhala`를 이 grounder로 **수렴**시킨다(병렬 복제 제거 + 전역 diff 교정).
- G5. CLI(`probe review:ground`)와 MCP(`probe.groundReview`) 두 표면으로 노출한다.
- G6. 빌드 *전에* **시그니처 시나리오(SR1~SR3)로 해자를 실증**한다.

### 2.2 비목표 (YAGNI)
- N1. **diff 소스 의미 분석 / 엣지·호출 델타 추출 / 로직 추론** (Claude의 일 — §1.2a).
- N2. 정합 자동판정(합/불 verdict). Probe는 증거+라벨만, 판정은 Claude.
- N3. 리뷰 critique/disposition/사인오프 원장·게이트 (specledger 영역).
- N4. 코드 심볼 인덱스/claim 레지스트리 구축 (Archon 영역). 질의만.
- N5. 다언어 풀 파서 (현존 플랫폼 프로파일 범위 — Spring Boot/Java, Next.js·React/TS·JS).

---

## 3. 입력 & 출력 계약

### 3.1 입력
```ts
interface ReviewGroundInput {
  /** git diff base (생략 시 기본: "origin/main" 또는 config) */
  base?: string;
}
```
troubleshoot의 자유텍스트 `signal`이 없다 — 입력은 diff base뿐. 변경 엔티티는 전부
고신뢰(실제로 바뀐 것)이므로 confidence 임계/국소화 휴리스틱(error-localizer)이 불필요하다.

### 3.2 출력 — Review Grounding Pack
```ts
interface ReviewGroundingPack {
  tier: 0 | 1 | 2 | 3;                     // 실제 동작한 그라운딩 티어
  tierReason: string;                      // 왜 그 티어인지
  changedEntities: ChangedEntity[];        // §1 diff→엔티티 (T0, 기반)
  applicableGuidelines?: RelevantDoc[];    // §2 적용 규정/런북 (T1)
  specRefs?: SpecRef[];                    // §3 승인 스펙 참조 (T1, specledger seam)
  topology?: ImpactAnalysis;               // §4 설계+관측 그래프 + 영향 (T2/T3)
  designObservationGaps?: DesignGap[];     // §5 엔티티 스코프 갭 (T2 doc_only / T3 observed_only·conflict)
  claimDrift?: ClaimRef[];                 // §6 Archon seam (티어와 직교; 미연동 시 생략)
  caveats: string[];                       // 부분결과·미연동·저신뢰 명시 (침묵 강등 금지)
}

interface ChangedEntity {
  entityName: string;        // grounder가 /graph·/diff에 넘길 정규화 service/entity명
  changedFiles: string[];    // fileBelongsToService로 귀속된 변경 파일
  cohesionGroup?: string;    // scope-analyzer 응집 그룹명 (선택, 추적용)
}

interface SpecRef {          // specledger가 Khala에 발행한 승인 스펙의 읽기전용 투영
  docTitle: string;
  sectionPath: string;
  approvedHash?: string;     // specledger content-hash 스탬프 (있으면)
  snippet: string;
  classification: string;
  // Probe는 정합 판정 안 함 — Claude가 diff↔스펙 대조
}
```

**재사용 타입:** `RelevantDoc`, `DesignGap`, `ImpactAnalysis`, `ClaimRef`는 모두 기존
`types.ts` 정의 재사용. **신규 타입은 `ReviewGroundingPack`/`ChangedEntity`/`SpecRef` 3개뿐.**

**핵심 불변식:** 모든 항목은 출처(evidence/provenance/hash/trace_ref)를 동반한다.
근거 없는 주장은 출력하지 않는다(Khala "Grounded answers only" 계승). Probe는 합/불·정합
여부를 *판정하지 않고* 증거+라벨만 — diff↔스펙/그래프/claim 대조는 Claude(§1.2, N2).

### 3.3 티어 → 섹션 권위 매트릭스 (단일 진실 원천)

| # | 섹션 | 산출 가능 최소 티어 | 근거 |
|---|------|--------------------|------|
| 1 | changedEntities | **T0** | 로컬 diff→엔티티, Khala 불필요 |
| 2 | applicableGuidelines | **T1** | `documents_count > 0` |
| 3 | specRefs | **T1** | 스펙 문서 존재 시 (없으면 생략+caveat) |
| 4 | topology: designed + impact | **T2** | `edges_count > 0` |
| 5 | designObservationGaps: `doc_only` | **T2** | 관측 없이 산출 가능 |
| 6 | topology: observed | **T3** | `observed_edges_count > 0` |
| 7 | designObservationGaps: `observed_only`/`conflict` | **T3** | 관측 엣지 필요 — **핵심 모트** |
| 8 | claimDrift | **별도 축(Archon)** | Archon claim+code 인덱스 연동 시에만. 티어와 직교 |

> 설계-관측 갭은 부분적으로 T2(`doc_only`)에서도 산출되고, 완전한 갭
> (`observed_only`/`conflict`)만 T3(v0.5 §3.4와 동일 규칙). claimDrift는 티어와 직교한다.

---

## 4. 섹션별 데이터 소스 매핑

| # | 섹션 | Khala 엔드포인트 / 소스 | 비고 |
|---|------|------------------------|------|
| 1 | 변경 엔티티 | (로컬) git diff + `analyzeScope` + `extractServiceNames`/`fileBelongsToService` | **Khala 호출 없음** |
| 2 | 적용 규정 | `POST /search` (엔티티+변경영역 쿼리) | context-enricher search 재사용 |
| 3 | 승인 스펙 참조 | `POST /search` (스펙 타입 필터) | §2와 동일 호출에 필터만 — 중복 fetch 방지 |
| 4 | 토폴로지+영향 | `GET /graph/{entity}?hops` + `analyzeImpact` | impact-analyzer 재사용 |
| 5 | 설계-관측 갭 | `GET /diff?entity_filter=<entity>` | v0.5의 entityFilter. flag: doc_only/observed_only/conflict |
| 6 | claim drift | (Archon) claim↔code 인덱스 질의 | Archon 연동 시에만. 부재 시 생략+caveat |

**§3 specRefs 식별:** specledger는 승인 스펙을 Khala에 발행한다(specledger ↔ Khala
publish 경로). Probe는 `/search`로 변경 엔티티 governing 문서를 조회하되, 스펙 타입
문서(doc kind / source_kind / frontmatter 마커 — 구현 계획에서 확정)만 `specRefs`로
투영한다. 스펙 미발견 시 생략 + caveat("변경 엔티티에 대한 승인 스펙 미발견").

### 4.1 KhalaClient — 신규 작업 거의 없음

v0.5에서 `getStatus`/`getStatusProbe`/`getDiff({entityFilter})`/`search`가 모두
갖춰졌다. v0.6은 **클라이언트 신규 메서드 없이** 기존 래퍼를 조합한다. specRefs용
스펙-타입 필터가 `/search` 파라미터로 표현 가능하면 클라이언트 변경 0 (구현 계획에서
Khala `/search` 필터 가용성 확인). 불가 시 응답측 필터링으로 처리(클라이언트 무변경).

### 4.2 Archon claimDrift seam (forward-compatible — Archon 없어도 동작)

v0.5 §4.2와 동일 패턴. Archon이 Khala에 `source_kind=code` 심볼 인덱스 + `claim`을
심으면, Probe는 변경 엔티티/심볼에 바인딩된 claim의 **상태·중요도·drift 여부**를
**인용만** 한다(만들지 않음). 부재 시 `claimDrift` 생략 + caveat 1줄. `ClaimRef`는 v0.5에서
정의된 읽기전용 투영 타입 그대로 재사용.

> **범위 경계:** Probe는 claim의 현재 *값*을 읽지 않는다(Archon 기획자 기능). 트러블슈팅과
> 동일하게 *상태·중요도·drift*만 인용한다("이 변경 엔티티는 core 불변식을 건드리고 drift됨").

---

## 5. 아키텍처

기존 하이브리드 구조(`src/` 코어 + `.claude/` 어댑터)에 정합되게 추가한다.

```
src/khala/
  review-grounder.ts    ← NEW: ChangedEntity[] → ReviewGroundingPack (diff/리뷰 정규 조립기)
  context-enricher.ts   ← REFACTOR: enrichWithKhala가 review-grounder에 위임
                          (전역→엔티티 스코프 diff 교정); extractServiceNames/fileBelongsToService 유지
  client.ts             ← 재사용 (getStatusProbe, getDiff entityFilter, search — v0.5/폴리시 자산)
  impact-analyzer.ts    ← 재사용 (§4 영향)
  types.ts              ← 확장: ReviewGroundingPack, ChangedEntity, SpecRef (신규 3개)
src/core/
  review-ground.ts      ← NEW: 입력→엔티티→티어 결정→grounder→caveat (core/troubleshoot.ts 미러)
                          determineTier/getStatusProbe 재사용
src/cli/
  index.ts              ← 확장: `probe review:ground` 서브커맨드
  parse-args.ts         ← 확장: --base, --format
  formatters.ts         ← 확장: ReviewGroundingPack markdown/json/brief 포맷
src/mcp/
  tools.ts              ← 확장: 8번째 도구 probe.groundReview + scope 도구를 grounder에 위임
```

### 5.1 단위별 책임 (isolation)

- **review-grounder**: `KhalaClient`와 `ChangedEntity[]`를 받아 §2~§6을 병렬 조립.
  각 섹션은 독립 실패해도 나머지를 막지 않음(`withKhalaFallback`). troubleshoot-grounder와
  **같은 Khala 섹션 호출**(getDiff entityFilter, search, analyzeImpact)을 쓰되, 출력은
  리뷰 전용 `ReviewGroundingPack`으로 조립. (두 grounder를 하나로 합치지 않음 — 출력
  계약이 다르므로. 공유는 client/impact-analyzer 레이어에서.)
- **review-ground (core)**: 오케스트레이션 — diff→`analyzeScope`→엔티티 추출,
  티어 결정(`getStatusProbe`+`determineTier`), grounder 호출, caveat 수집.
- **context-enricher (refactored)**: `enrichWithKhala`는 review-grounder를 호출하고
  결과를 레거시 `EnrichmentResult`로 투영하는 얇은 어댑터로 축소. 기존 MCP scope 도구
  호환 유지 + 전역 diff 버그 자동 교정.

### 5.2 티어 결정 로직 (v0.5 공유)
```
getStatusProbe()
  → {ok:false, reason:'timeout'}            ⇒ T0 (느림/콜드스타트 명시, 재시도 권장)
  → {ok:false, reason:'unreachable'}        ⇒ T0 (미가용)
  → documents_count>0, edges_count==0       ⇒ T1 (+규정/스펙)
  → edges_count>0, observed_edges_count==0  ⇒ T2 (+설계 토폴로지·영향·doc_only 갭)
  → observed_edges_count>0                  ⇒ T3 (+관측·observed_only/conflict 갭)
```

---

## 6. 에러 처리 & 강등 (v0.5 정책 계승)

- **입력 검증(Khala 호출 전):** 변경 파일 0개 → "변경 없음" 즉시 반환(Khala 미호출).
  엔티티 추출 0개 → "엔티티 귀속 실패 + 힌트(파일 경로/프로파일 확인)" 반환.
- Khala 전체 장애 → T0 강등, `tierReason` 명시. CLI 비-제로 종료 아님(조언 도구).
- 개별 섹션 실패(예: `/diff` 500) → 해당 섹션만 생략, `caveats` 기록, 나머지 진행.
- **승인 스펙 부재** → `specRefs` 생략 + caveat. **Archon 미연동** → `claimDrift` 생략 + caveat.
- 침묵 누락 절대 금지 — 모든 강등/부분결과는 `caveats`에 명시.

---

## 7. 출력 표면

### 7.1 CLI
```bash
probe review:ground                          # 기본 base(origin/main)
probe review:ground --base main --format json
probe review:ground --format brief           # CI 한 줄
```
네임스페이스(`api:lint`/`khala:*` 컨벤션)로 기존 `probe review`(체크리스트)와 충돌 없이
"review의 그라운디드 변형"임을 신호. 출력: markdown(기본)/json(에이전트·파이프라인)/brief(CI).

### 7.2 MCP 도구
```
probe.groundReview(base?, format?) → ReviewGroundingPack(JSON)
```
Claude Code 대화 중 "이 변경 리뷰해줘" → 이 도구가 조직 그라운딩을 반환, Claude가
실제 diff와 대조해 리뷰. (Probe는 정합 판정을 내지 않음 — §1.2 경계)

---

## 8. 시그니처 시나리오 (해자 실증 — 빌드 전 첫 마일스톤)

본 구현 *전에*, "그라운딩만이 가능케 하는" 리뷰 시나리오로 해자를 **실증**한다.
v0.5 §8 시드 절차(합성 관측 엣지/문서 주입)를 재사용한다.

- **SR1 (T3 모트 — 설계-관측 갭):** diff가 `order-service`를 수정.
  Probe가 기존 `observed_only` order→inventory 엣지 + error_rate 급증을 제시 →
  Claude가 "미문서화 고에러 의존성을 코드로 굳히는 변경"이라 판단.
  *제네릭 리뷰는 trace 없어 이 발견이 구조적으로 불가능.*
- **SR2 (T1 — 승인 스펙 정합):** diff가 payment 재시도 로직 터치.
  Probe가 승인 스펙(멱등성 요구)+규정②를 참조로 제시 → Claude가 diff↔스펙 대조.
- **SR3 (T0 강등 정직성):** Khala 미가용.
  Probe는 변경 엔티티만 제시하고 "T0, 그래프/관측/스펙 그라운딩 불가"를 명시(침묵 강등 안 함).

### 8.1 대조 검증 (해자 증명)
SR1을 (a) 제네릭 리뷰 단독, (b) Review Grounding Pack 첨부 두 조건에서 실행.
(a)가 observed_only 엣지를 **구조적으로 제시할 수 없음**을 보이면 해자가 실증된다.

---

## 9. 테스트 전략

- **단위:** 엔티티 추출(재사용분 회귀 — `fileBelongsToService`/`extractServiceNames`),
  티어 결정(공유분), ReviewGroundingPack 포맷터. Khala 응답 fixture 목킹.
- **통합:** 목 Khala로 §2~§6 조립 경로 + 부분 실패 강등 + spec/claim 부재 caveat 경로 +
  `enrichWithKhala` 수렴 후 레거시 EnrichmentResult 투영 회귀.
- **시그니처:** §8 SR1~SR3을 자동화 테스트(또는 재현 스크립트)로 고정.
- 기준: core 변경 테스트 필수(CLAUDE.md), `any` 금지, 한국어 우선 메시지.

---

## 10. 로드맵 반영

```
v0.4  칼라 연동 — 맥락 기반 리뷰                          ✅ (enrichWithKhala — v0.6이 수렴)
v0.5  트러블슈팅 그라운딩                                 ✅
v0.6  그라운디드 코드 리뷰 (본 문서)                     ← 신규 (피보팅 2단계)
```

> v0.6은 피보팅("Probe = Khala 보편 소비자 / 그라운딩 레이어")의 **2단계**다.
> v0.5의 grounder 자산(getDiff entityFilter, search, impact, 티어 결정)을 diff 입력으로
> 재사용하고, v0.4의 곁가지 enrichment를 정합성-프레이밍 리뷰 팩으로 수렴한다.
> Archon claimDrift / specledger specRefs는 #11+#17/specledger 출하 후 활성, 그 전엔 강등.

---

## 11. 미해결 질문 (구현 계획에서 확정)

- Q1. specRefs 식별 필터 — Khala `/search`가 스펙-타입 문서 필터를 파라미터로 지원하는지,
  아니면 응답측 필터링(doc kind/source_kind/frontmatter 마커)이 필요한지. (§4 §4.1)
- Q2. `probe review:ground`와 기존 `probe review`(체크리스트)의 출력 결합 여부 —
  v0.6은 분리(독립 팩)로 가되, 추후 `review`가 grounding 팩을 첨부 섹션으로 합칠지는 별도.
- Q3. `enrichWithKhala` 수렴 시 레거시 `EnrichmentResult` 호출부(MCP scope 도구, prompts)의
  마이그레이션 범위 — 어댑터 투영 유지 vs scope 도구를 ReviewGroundingPack 직접 소비로 전환.
- Q4. specRefs/claimDrift seam의 부재 caveat 문구 표준화.
- Q5. **specRefs ↔ applicableGuidelines 분할 규칙** — §2와 §3은 동일 `/search` 호출을
  공유하므로(중복 fetch 방지), 한 문서가 양쪽에 중복 투영되지 않도록 분배 규칙(스펙 타입 →
  specRefs, 그 외 → applicableGuidelines)을 구현 계획에서 명시한다. (리뷰어 권고)
- Q6. **enrichWithKhala 어댑터 투영 회귀 고정** — `ReviewGroundingPack.topology`(ImpactAnalysis)
  → 레거시 `EnrichmentResult.impactedServices`(`directImpact.concat(indirectImpact)`) 평탄화
  투영을 회귀 테스트로 핀(§9). (리뷰어 권고)
- Q7. **MCP 표면 에러 계약 일관성** — `runTroubleshoot`의 판별 유니온(`{ok:false}`)을
  리뷰 경로도 미러해 MCP 도구가 throw하지 않도록 한다. (리뷰어 권고)
