---
title: "Probe v0.5 — 트러블슈팅 그라운딩 (Troubleshooting Grounding)"
date: 2026-06-06
status: draft
authors: [eisen]
supersedes: []
related:
  - probe/docs/probe-v0.4-scope.md
  - khala/CLAUDE.md  # "맥락 기반 AI Agent(Code Review / Troubleshooting)의 context provider"
  - "[claude] mcp-tools/specledger"  # 비충돌 경계 대상 (스펙 거버넌스 생산자)
  - khala/docs/superpowers/specs/2026-06-06-domain-invariant-governance-design.md  # Archon(#17) — claim+code 생산자, Probe 그라운딩 소스
---

# Probe v0.5 — 트러블슈팅 그라운딩

## 0. 한 줄 요약

에러·스택트레이스·실패 테스트를 입력받아, **근본원인을 단정하지 않고** 조직 컨텍스트
(토폴로지·관측 신호·규정·최근 변경)를 하나로 묶은 **Grounding Pack**을 생성해
Claude(또는 사람)의 디버깅 추론에 근거를 깔아주는 도구.

> **Probe는 증거를 모은다. 추론은 Claude가 한다.**

---

## 1. 배경 & 문제

### 1.1 왜 지금 이걸 만드는가

Khala 에코시스템의 설계 의도는 명확하다 (`khala/CLAUDE.md` 첫 문장):

> "맥락 기반 AI Agent(**Code Review / Troubleshooting**)의 context provider가 최종 목표다."

즉 **Nexus = context provider, Probe = 그 컨텍스트를 소비하는 에이전트**다.
v0.4까지 Probe는 *구조적 리뷰*(PR 범위·API 계약·체크리스트)만 했고,
"트러블슈팅"은 로드맵에 있었으나 미구현이었다. v0.5가 그 자리를 채운다.

### 1.2 만들지 *않는* 이유를 먼저 검증했다 (반(反)중복 분석)

이 작업의 출발점은 "이미 존재하는 것보다 나은가?"라는 질문이었다.

**(a) 제네릭 Claude 코드 리뷰/디버깅 스킬과 경쟁하지 않는다.**
`code-review`, `tech-lead:review`, `superpowers:systematic-debugging` 등은 코드를
**고립된 상태로** 추론하는 데 이미 매우 강하다. "로직 버그 더 잘 잡기"는 방어 가능한
해자가 아니다. 따라서 Probe는 **그 영역을 재구현하지 않고**, 그들이 *구조적으로 접근할
수 없는* 조직 컨텍스트를 공급하는 데 집중한다.

| 차원 | 제네릭 스킬 | Probe + Nexus |
|------|------------|---------------|
| 로직/버그/안티패턴 추론 | ✅ 강함 | 위임 (경쟁 안 함) |
| 런타임 호출 토폴로지 | ❌ 코드만으론 모름 | ✅ `/graph` |
| **설계 vs 실관측(trace) 갭** | ❌ **구조적으로 불가능** | ✅ `/diff` (해자) |
| 운영 신호(error_rate/latency) | ❌ 정적 분석 불가 | ✅ 관측 엣지 |
| 조직 규정/런북/과거 인시던트 | ❌ 문서 접근 불가 | ✅ `/search` |

**(b) specledger와 중복되지 않는다 — 오히려 체인된다.**

| | Specledger | Probe v0.5 |
|---|---|---|
| 수명주기 단계 | **코드 작성 전** (설계→승인→게이트) | **코드 작성 후 + 런타임** |
| 리뷰 대상 | **문서**(spec/ADR) | **코드/diff + 운영 동작** |
| 핵심 기제 | critique→사람 disposition→해시 게이트 | Nexus 컨텍스트 기반 그라운딩 |
| Nexus 관계 | 승인 스펙을 Nexus에 **발행**(producer) | Nexus 컨텍스트를 **소비**(consumer) |

체인: `Specledger(스펙 승인→Nexus 발행) → 코드 작성 → Probe(diff/에러를 조직
컨텍스트에 비춰 그라운딩)`. Probe는 specledger가 Nexus에 넣은 승인 스펙을 그라운딩
입력의 하나로 소비할 수 있어, 두 도구는 상보적이다.

**(c) Archon(#17, Nexus 확장)과 중복되지 않는다 — Probe의 그라운딩 기반을 *깊게* 만든다.**

Archon은 Nexus에 (1) 신규 rtype `claim`(goal/invariant/requirement), (2) 신규
source_kind `code`(코드 상수·설정·강제 메커니즘을 (파일+심볼) hash로 인덱싱),
(3) `claim↔code` drift 태깅을 추가하는 **Nexus 생산자/확장**이다. 청중은 기획자,
기제는 결정론적 값 조회 + 캘리브레이션 신뢰. **코드 diff 리뷰나 런타임 트러블슈팅을
하지 않는다.**

| | Archon (#17) | Probe v0.5 |
|---|---|---|
| 역할 | Nexus **생산자**: claim + code 소스를 *심음* | Nexus **소비자**: 심긴 것을 *적용* |
| 청중 | 기획자(비엔지니어) | 엔지니어 + AI |
| 기제 | 결정론적 값 조회 / 캘리브레이션 | 에러→증거 조립(그라운딩) |
| 코드와의 관계 | 코드 상수/심볼을 **인덱싱**(쓰기) | 인덱스를 **질의**(읽기) |

**산출물 소유권 계약 (RACI — 중복 원천 차단):**
- **`source_kind=code` / 코드 심볼 인덱스 / `claim↔code` drift = Archon 소유 (Owner).**
  Probe는 이 인덱스를 **만들지 않고 질의만** 한다(Consumer). Probe가 자체 코드 인덱스를
  구축하면 중복이므로 금지.
- **claim(불변식/값/요구) 레지스트리·검증 티어·캘리브레이션 = Archon 소유.**
  Probe는 claim을 **그라운딩 근거로 인용만** 한다 — claim 상태를 *판정*하지 않는다.
- **에러→의심지점 국소화, 토폴로지/관측 그라운딩, 트러블슈팅 출력 = Probe 소유.**
  Archon은 여기 관여하지 않는다.

> 패턴 일반화: **Probe = Nexus 보편 소비자. specledger·Archon = Nexus 생산자.**
> 세 도구는 같은 Nexus를 공유하되 생산/소비 방향과 청중으로 갈린다.

**경계 불변식 (NON-NEGOTIABLE):**
- Probe는 **근본원인을 단정하지 않는다** (그건 Claude의 추론).
- Probe는 **critique→disposition→사인오프 원장이나 게이트를 만들지 않는다** (그건 specledger).
- Probe는 **코드 심볼 인덱스나 claim 레지스트리를 만들지 않는다** (그건 Archon). 질의만 한다.
- 대상·청중·기제·산출물 소유권을 분리해 중복을 원천 차단한다.

---

## 2. 목표 & 비(非)목표

### 2.1 목표
- G1. 에러 신호(스택트레이스/에러 메시지/실패 테스트/인시던트 설명)를 입력받아 **의심
  지점을 service/entity로 국소화**한다.
- G2. 의심 지점 주변의 **설계+관측 토폴로지, 설계-관측 갭, 운영 신호, 관련 규정/런북,
  최근 변경 상관**을 하나의 **Grounding Pack**으로 조립한다.
- G3. Nexus 가용 수준에 따라 **그라운딩 티어(T0~T3)를 자가진단**하고, 동작한 티어를
  **명시**한다 (침묵 강등 금지).
- G4. CLI(`probe troubleshoot`)와 MCP(`probe.groundTroubleshooting`) 두 표면으로 노출한다.
- G5. 빌드 *전에* **시그니처 시나리오로 해자를 실증**한다.

### 2.2 비목표 (YAGNI)
- N1. 근본원인 자동 판정 / 자동 수정 제안 (Claude의 일).
- N2. Tempo에서 raw trace 직접 fetch (Nexus가 주는 `sample_trace_ids` /
  `trace_query_ref` 포인터만 노출).
- N3. 다언어 스택트레이스 풀 파서 (현존 플랫폼 프로파일 범위 — Spring Boot/Java,
  Next.js·React/TS·JS — 만 1차 지원).
- N4. 통계적 이상치 탐지 모델 (관측 엣지의 error_rate/latency 단순 임계 비교로 충분).
- N5. 리뷰 원장/게이트 (specledger 영역).

---

## 3. 입력 & 출력 계약

### 3.1 입력
```ts
interface TroubleshootInput {
  /** 에러 신호 본문 (스택트레이스 | 에러 메시지 | 실패 테스트 출력 | 인시던트 설명) */
  signal: string;
  /** 신호 종류 힌트 (생략 시 휴리스틱 추론) */
  kind?: 'stacktrace' | 'error' | 'test-failure' | 'incident';
  /** 선택: 최근 변경과 상관 분석 (git diff base) */
  diffBase?: string;        // 예: "origin/main"
  /** 선택: 사용자가 지목한 의심 서비스 */
  suspectServices?: string[];
}
```

### 3.2 출력 — Grounding Pack
```ts
interface GroundingPack {
  tier: 0 | 1 | 2 | 3;            // 실제 동작한 그라운딩 티어
  tierReason: string;            // 왜 그 티어인지 (예: "OTel 관측 데이터 없음 → T2")
  suspects: Suspect[];           // §1 국소화
  topology?: TopologyView;       // §2 설계+관측 그래프 (T2+)
  designObservationGaps?: Gap[]; // §3 /diff conflict·observed_only (T3)
  operationalSignals?: Signal[]; // §4 error_rate/latency 이상치 (T3)
  knowledge?: KnowledgeRef[];    // §5 런북/규정/인시던트 (근거+provenance) (T1+)
  changeCorrelation?: ChangeLink[]; // §6 diff ∩ 의심 토폴로지 (diffBase 제공 시)
  domainInvariants?: ClaimRef[]; // §4.2 seam: 의심 심볼에 바인딩된 Archon claim 인용 (Archon 연동 시에만)
  caveats: string[];             // 신뢰 한계 명시 (낮은 confidence, 부분 결과, Archon 미연동 등)
}
```

**핵심 원칙: 모든 항목은 출처(evidence/provenance/trace_ref)를 동반한다.**
근거 없는 주장은 출력하지 않는다 (Nexus의 "Grounded answers only" 원칙 계승).

### 3.3 Suspect — 국소화 산출물 & localizer→grounder 계약

§1 국소화의 출력이자 §2~§6 모든 Nexus 호출의 입력이다. 이 계약이 정의되지 않으면
grounder를 구현할 수 없으므로 여기서 확정한다 (구체적 *휴리스틱*만 Q2로 미룸).

```ts
interface Suspect {
  /** grounder가 getGraph/getDiff에 넘길 정규화된 service/entity 후보명 */
  entityName: string;
  /** 국소화 근거 (스택트레이스 프레임, 파일 경로, 사용자 지정 등) */
  evidence: { kind: 'frame' | 'path' | 'user' | 'keyword'; raw: string }[];
  /** 0~1. grounder는 임계(기본 0.3) 미만 suspect는 caveats로만 보고 */
  confidence: number;
}
```

**계약:** `error-localizer`는 `Suspect[]`를 confidence 내림차순으로 반환한다.
`troubleshoot-grounder`는 각 suspect의 `entityName`을 그대로 `getGraph(name, {hops})` /
`getDiff({entityFilter: name})`에 전달한다 (`/graph`·`/diff`는 이름→rid 변환을 서버에서
지원함 — `api.py` get_graph 392-405, get_diff entity_filter 486). 즉 Probe는 rid를
직접 만들지 않는다 (기존 `buildEntityRid` 추정 로직 의존 제거).

### 3.4 티어 → 섹션 권위 매트릭스 (단일 진실 원천)

§3.2 필드 주석, §4 "비고", §5.2 임계는 모두 이 표를 참조한다. 충돌 시 이 표가 우선.

| 섹션 | 산출 가능 최소 티어 | 근거 |
|------|--------------------|------|
| suspects (§1) | **T0** | 로컬, Nexus 불필요 |
| knowledge (§5) | **T1** | documents_count > 0 |
| topology: designed (§2) | **T2** | edges_count > 0 |
| changeCorrelation (§6) | **T2** | 설계 그래프 + git diff |
| designObservationGaps: `doc_only` (§3) | **T2** | `/diff`의 doc_only는 관측 없이 산출 가능 |
| topology: observed (§2) | **T3** | observed_edges_count > 0 |
| operationalSignals (§4) | **T3** | 관측 엣지의 error_rate/latency 필요 |
| designObservationGaps: `observed_only`/`conflict` (§3) | **T3** | 관측 엣지 필요 |
| domainInvariants (§4.2 seam) | **별도 축(Archon)** | Archon claim+code 인덱스 연동 시에만. 티어와 직교 — Archon 없으면 항상 생략 |

> 주의: 설계-관측 갭은 **부분적으로 T2에서도** 산출된다(`doc_only`). 완전한 갭
> (`observed_only`/`conflict`)만 T3. 이전 초안이 갭 전체를 T3로 묶은 것은 부정확했다.
> 도메인 불변식 차원은 T0~T3 티어와 **직교**한다(Archon 연동 여부에 달림). `tierReason`과
> 별개로 `caveats`에 Archon 연동 상태를 명시한다.

---

## 4. 6개 섹션의 데이터 소스 매핑

| # | 섹션 | Nexus 엔드포인트 / 소스 | 비고 |
|---|------|------------------------|------|
| 1 | 의심 지점 국소화 | (로컬) 스택트레이스 파싱 + 플랫폼 프로파일 — **Nexus 호출 없음** | service 후보 검증이 필요하면 `GET /entities/suggest` (선택) |
| 2 | 토폴로지 | `GET /graph/{entity}?hops=2` | designed + observed edges |
| 3 | 설계-관측 갭 | `GET /diff?entity_filter=<service>` | flag: `conflict` / `observed_only` / `doc_only` (값 확인: `diff_engine.py` 41/88/101) |
| 4 | 운영 신호 | `/graph` 응답의 observed_edges (call_count/error_rate/latency_p95) | 임계 비교 (§4 row 2와 같은 호출 재사용, 추가 호출 없음) |
| 5 | 지식 그라운딩 | `POST /search` (또는 `/search/answer`) | evidence_snippets + provenance |
| 6 | 최근 변경 상관 | (로컬) `git diff` + 기존 `impact-analyzer.ts` | 변경 service ∩ 의심 토폴로지 |

**§1 국소화는 Nexus를 호출하지 않는다** (순수 로컬). 다만 후보 service명을 Nexus
엔티티명과 맞추는 검증이 필요하면 `GET /entities/suggest`를 선택적으로 쓸 수 있다.
서버 내부 함수 `find_entities_in_text`는 HTTP로 노출되지 않으므로 Probe가 호출하지 않는다.

### 4.2 Archon 시너지 seam (forward-compatible — v0.5는 없어도 동작)

Archon(#17)이 Nexus에 `source_kind=code` 심볼 인덱스와 `claim`을 심으면, Probe는
**만들지 않고 질의만** 한다(§1.2c RACI). v0.5는 이를 *선택적 강화*로 설계하고 부재 시
강등한다 — Archon에 출하가 막히지 않는다.

| seam | Archon 있을 때 (강화) | Archon 없을 때 (v0.5 기본) |
|------|----------------------|---------------------------|
| **국소화 (§1)** | 스택트레이스 심볼 → Archon 코드 심볼 인덱스로 **결정론적** service/concept 매핑 | 플랫폼 프로파일 휴리스틱(파일경로→service). Q2의 휴리스틱이 fallback이 됨 |
| **도메인 불변식 그라운딩 (신규 §7번째 차원)** | 의심 코드에 바인딩된 `claim`의 **상태(status)**(불변식 held/violated, 요구 reflected 등) + `claim_code_drift` 플래그를 근거로 인용 | 생략 (caveats에 "Archon 미연동" 1줄) |

> **범위 경계**: Probe는 claim의 **현재 *값*을 읽지 않는다**(예: "준회원 5개"). 값 조회는
> Archon의 기획자용 결정론 기능(Archon §10·§11)이다. Probe가 트러블슈팅에 쓰는 것은
> claim의 *상태·중요도·drift 여부*뿐이다("이 의심 코드는 core 불변식을 건드리고 drift됨").

**도메인 불변식 그라운딩(7번째 차원)의 출력 계약**: 의심 심볼에 바인딩된 claim을
**인용만** 한다. Probe는 claim 상태를 *재판정하지 않고* Archon이 매긴 값을 그대로
전달한다(소유권 §1.2c). 이는 제네릭 스킬이 구조적으로 못 하는 그라운딩이다.

`ClaimRef`는 Archon claim(Archon 스펙 §5.2)의 **읽기 전용 투영**이다 — Probe는 이
필드를 만들지 않고 Nexus 응답에서 그대로 복사한다:
```ts
interface ClaimRef {
  id: string;            // 예: "associate-max-playlists"
  kind: 'goal' | 'invariant' | 'requirement';
  statement: string;
  status: string;        // Archon이 매김. kind별 어휘 상이 (invariant: held/violated/unverified; requirement: reflected/partial/not-reflected/unverified). Probe는 인용만, 변경 안 함
  criticality: 'core' | 'peripheral';
  confidence: 'high' | 'medium' | 'low';
  codeDrift: boolean;    // Archon의 claim_code_drift 플래그
  owner: string;
  boundSymbol: string;   // 이 claim이 매달린 의심 코드 심볼
}
```
예: "의심 심볼 `PlaylistPolicy.ASSOCIATE_MAX_PLAYLISTS` → 불변식
`associate-max-playlists`(core, status=held, owner=@backend-lead, codeDrift=false)."

### 4.1 NexusClient 확장 (정직한 신규 작업 — v0.4 클라이언트로 *충분하지 않다*)

v0.4 `NexusClient`는 `/search`·`/search/answer`·`/graph`·`/diff`·`/status`를 래핑하지만,
v0.5는 다음 **신규 메서드/타입/옵션**이 필요하다. (이전 초안이 "신규 코드 불필요"라
적었던 것은 오류였다.)

| 항목 | 현재 상태 | v0.5 필요 작업 |
|------|----------|---------------|
| `getStatus()` | `isAvailable()`가 `/status`를 호출하나 body를 버리고 boolean만 반환 | **신규** `getStatus(): Promise<NexusStatusResult \| null>` + **신규 타입** `NexusStatusResult`(`documents_count`, `edges_count`, `observed_edges_count`, `tempo_connected`, `diff_summary` 등). §5.2 티어 로직의 전제. |
| `getDiff` entity 스코프 | `getDiff`가 `flag_filter`만 전송 | **확장**: `getDiff({ entityFilter?, flagFilter? })` — `/diff?entity_filter=` 추가. §3 S1의 전제. |
| `suggestEntities()` (선택) | 없음 | **선택 신규**: `GET /entities/suggest` 래퍼. §1 service명↔엔티티명 정합 검증용(없어도 T0 동작). |

> `/graph`, `/search`, `/diff` 엔드포인트 자체는 `api.py`에 이미 존재하므로 **서버측
> Nexus 변경은 없다.** 변경은 Probe의 클라이언트 레이어에 국한된다.

---

## 5. 아키텍처

기존 하이브리드 구조(`src/` 코어 + `.claude/` 어댑터)에 정합되게 추가한다.

```
src/nexus/
  error-localizer.ts        ← NEW: 에러/스택트레이스 → 의심 service/entity (§1)
  troubleshoot-grounder.ts  ← NEW: 6개 섹션 → GroundingPack 조립 (§2~§6)
  client.ts                 ← 확장 (getStatus 신규, getDiff entityFilter 확장 — §4.1 참조)
  impact-analyzer.ts        ← 재사용 (§6 변경 상관)
  context-enricher.ts       ← 재사용 (§5 규정 보강)
  types.ts                  ← 확장: TroubleshootInput, GroundingPack 등
src/core/
  troubleshoot.ts           ← NEW: 입력 파싱 → tier 결정 → grounder → 결과
src/cli/
  index.ts                  ← 확장: `probe troubleshoot <signal>` 서브커맨드
  parse-args.ts             ← 확장: --diff-base, --kind, --suspect 플래그
  formatters.ts             ← 확장: GroundingPack markdown/json/brief 포맷
src/mcp/
  tools.ts                  ← 확장: 7번째 도구 `probe.groundTroubleshooting`
```

### 5.1 단위별 책임 (isolation)

- **error-localizer**: 순수 함수. 입력 = signal + 활성 플랫폼 프로파일. 출력 =
  `Suspect[]`(파일·심볼·service·entity 후보 + confidence). Nexus 의존 없음 → 독립 테스트 가능.
- **troubleshoot-grounder**: `NexusClient`와 `Suspect[]`를 받아 §2~§6을 병렬 조립.
  각 섹션은 독립적으로 실패해도 나머지를 막지 않음 (`withNexusFallback`).
  **`/search` 호출 소유권**: §5 지식 그라운딩은 grounder가 `client.search()`를 직접
  호출한다. 기존 `context-enricher.ts`는 PR-리뷰 맥락 보강용(`EnrichmentResult`)이라
  반환 구조가 다르므로 v0.5에서 **재사용하지 않는다** (중복 fetch 방지). §6 변경 상관만
  `impact-analyzer.ts`를 재사용한다.
- **troubleshoot (core)**: 오케스트레이션 + 티어 결정(`/status`로 가용성 진단) + caveat 수집.

### 5.2 티어 결정 로직
```
/status 조회 (또는 isAvailable 실패)
  → Nexus 미가용                         ⇒ T0 (국소화 + 프로파일만)
  → documents_count > 0, edges_count==0   ⇒ T1 (+ RAG)
  → edges_count > 0, observed_edges_count==0 ⇒ T2 (+ 설계 토폴로지 + 영향)
  → observed_edges_count > 0              ⇒ T3 (+ 운영 신호 + 설계-관측 갭)
```
`tierReason`에 판정 근거를 그대로 적는다.

---

## 6. 에러 처리 & 강등

- **입력 검증** (Nexus 호출 *전*): `signal`이 공백/빈 문자열이면 즉시 "입력 없음 +
  사용 예시" 반환(Nexus 호출 안 함). `signal` 과대 입력은 앞 N KB로 절단하고 `caveats`에
  기록. `kind` 힌트가 본문과 모순되면(예: `kind=stacktrace`인데 프레임 0개) 힌트를
  무시하고 휴리스틱으로 재판정 후 `caveats`에 명시.
- Nexus 전체 장애: T0로 강등, `tierReason`에 명시. CLI는 비-제로 종료코드 아님(조언 도구).
- 개별 섹션 실패(예: `/diff` 500): 해당 섹션만 생략, `caveats`에 기록, 나머지 진행.
- 국소화 실패(의심 지점 0개): Grounding Pack 대신 "국소화 불가 + 입력 개선 힌트" 반환.
- 낮은 confidence suspect(< 0.3): 출력하되 `caveats`에 신뢰 한계 명시 (침묵 누락 금지).

---

## 7. 출력 표면

### 7.1 CLI
```bash
probe troubleshoot "java.lang.NullPointerException at OrderService.checkout(OrderService.java:88)"
probe troubleshoot --kind test-failure --diff-base origin/main < test-output.txt
probe troubleshoot "결제 통합테스트 실패" --suspect payment-service --format json
```
출력: markdown(기본) / json(에이전트·파이프라인) / brief(CI 한 줄).

### 7.2 MCP 도구
```
probe.groundTroubleshooting(signal, kind?, diffBase?, suspectServices?) → GroundingPack(JSON)
```
Claude Code 대화 중 에러를 붙여넣으면 이 도구가 호출되어 그라운딩을 반환,
Claude가 그 위에서 근본원인을 추론한다. (Probe는 추론 결과를 내지 않는다 — §1.2 경계)

---

## 8. 가설 검증을 첫 마일스톤으로 (시그니처 시나리오 먼저)

본 구현 *전에*, "그라운딩만이 풀 수 있는" 시나리오로 해자를 **실증**한다.

### 8.1 시그니처 시나리오
- **S1 (T3 전용 — 설계-관측 갭):** `OrderService.checkout` NPE.
  Probe는 설계 문서에 없는 `order→inventory`의 **observed_only 엣지**와 그 엣지의
  **error_rate 급증**을 제시한다. → 제네릭 스킬은 trace가 없어 *이 발견이 구조적으로 불가능*.
- **S2 (T1+T2 — 규정+변경 상관):** payment 통합테스트 실패.
  Probe는 규정 ②(멱등성)과 payment 재시도 로직을 건드린 **최근 diff**를 상관시킨다.
- **S3 (T0 강등 정직성):** Nexus 미가용 상태.
  Probe는 국소화만 수행하고 **"T0, OTel/그래프 그라운딩 불가"를 명시**한다 (침묵 강등 안 함).

### 8.2 대조 검증 (해자 증명)
S1을 (a) 제네릭 디버깅 스킬 단독, (b) Probe Grounding Pack 첨부 두 조건에서 실행.
(a)가 observed_only 엣지를 **구조적으로 제시할 수 없음**을 보이면 해자가 실증된다.

### 8.3 검증 데이터 가용성 & 시드 절차 (마일스톤 차단 해소)

S1/S2는 Nexus에 관측 엣지·문서가 필요하다. 마일스톤이 미해결 질문에 막히지 않도록
시드 절차를 **여기서 확정**한다 (Q1 제거):

1. `getStatus()`로 가용성 진단. observed_edges_count > 0이고 S1 토폴로지가 이미
   존재하면 → 실데이터로 검증.
2. 없으면 **재현 가능한 합성 시드**를 주입한다:
   - 설계 문서: `order-service`가 `inventory-service`를 호출하지 *않는다*고 명시한
     짧은 markdown → `nexus ingest`로 인덱싱 (designed edge 생성/부재 확립).
   - 관측 엣지: `nexus otel-aggregate` 경로 대신, 테스트 픽스처로 `observed_edges`에
     `order→inventory`(error_rate 0.2) 1건을 직접 삽입하는 시드 스크립트(`scripts/`).
     Tempo raw trace 불필요(N2 준수) — 집계 결과 테이블만 채운다.
3. 이 시드는 **검증 전용**이며 `/diff`가 `observed_only`(order→inventory)를 산출함을
   확인하는 데만 쓴다. 프로덕션 경로에 들어가지 않는다.

> 따라서 §8 "시그니처 시나리오 먼저" 마일스톤은 위 1~3과 `getStatus()`/`getDiff` 확장만
> 선행하면 시작 가능하다 (전체 grounder 구현 불필요).

---

## 9. 테스트 전략

- **단위:** `error-localizer`(스택트레이스 → suspects), 티어 결정 로직, 포맷터.
  Nexus 응답은 fixture로 목킹.
- **통합:** `NexusClient` 목 서버로 §2~§6 조립 경로. 부분 실패 강등 경로 포함.
- **시그니처:** §8의 S1~S3을 자동화 테스트(또는 재현 스크립트)로 고정.
- 기준: core 변경은 테스트 필수(CLAUDE.md 규칙), `any` 금지, 한국어 우선 메시지.

---

## 10. 로드맵 반영

```
v0.4  Nexus 연동 — 맥락 기반 리뷰                 ✅
v0.5  트러블슈팅 그라운딩 (본 문서)              ← 신규
v0.6  그라운드 코드 리뷰 (diff ↔ 스펙/규정/그래프/claim 합성)  ← 차기 (피보팅 2단계)
```

> v0.5는 피보팅("Probe = Nexus 보편 소비자 / 그라운딩 레이어")의 **1단계**다.
> 2단계(그라운드 코드 리뷰)는 같은 grounder 자산을 diff 입력으로 재사용하며, Archon의
> `claim↔code` drift를 직접 소비한다("이 diff가 core 불변식을 건드림").
>
> **에코시스템 생산자/소비자 지도** (중복 없이 시너지):
> - specledger → 승인 스펙 발행 (생산자)
> - Archon(#17) → claim + code 소스 발행 (생산자)
> - **Probe → 위 전부 + 토폴로지/관측을 소비해 리뷰/트러블슈팅 그라운딩 (소비자)**
> - 공유 선행조건: Nexus(#11). Archon 연동 기능은 #11+#17 이후 활성, 그 전엔 강등.

---

## 11. 미해결 질문 (구현 계획에서 확정)

> Q1(시드 데이터)은 §8.3에서 해소됨. 아래는 *휴리스틱 디테일* 수준의 잔여 질문으로,
> §3.3에서 인터페이스 계약은 이미 고정되었으므로 grounder 구현을 막지 않는다.

- Q2. 스택트레이스 프레임/파일 경로 → `Suspect.entityName` 매핑의 *휴리스틱 내용*
  (계약은 §3.3 고정). 단 §4.2 seam에 따라: Archon 코드 심볼 인덱스가 있으면 그쪽을
  결정론적 1순위로, 휴리스틱은 fallback. 즉 이 휴리스틱은 "Archon 없을 때의 fallback"
  품질만 책임지면 된다 (과투자 금지).
- Q3. 운영 신호 이상치 임계값 기본치 (`impact-analyzer`의 error_rate > 0.05 재사용 제안).
- Q4. CLI에서 stdin 입력(파이프) vs 인자 입력의 우선순위 (§3.1 / §7.1).
