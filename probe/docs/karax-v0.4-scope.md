# Karax v0.4 — 범위 정의

> **핵심 가치**: PR 리뷰 시 "왜 이렇게 만들어야 하는지"의 근거를 칼라(Khala)에서 자동으로 가져온다.
> **v0.3과의 관계**: v0.3은 Karax를 Claude Code의 도구로 노출했다. v0.4는 그 도구가 칼라의 지식을 활용해서 맥락 있는 판단을 내리게 한다.

---

## 0. v0.4가 하는 일 — 한 문장

**PR 변경에 관련된 규정·아키텍처 문서·서비스 의존 관계를 칼라에서 조회하여, 근거 기반의 맥락 있는 리뷰를 수행한다.**

---

## 1. 왜 필요한가

### v0.3만으로는 부족한 것

v0.1~v0.3의 Karax는 **코드 구조만 본다**. 변경된 파일의 역할, 응집도, API 스펙 품질은 판단하지만, "이 변경이 조직의 규정에 맞는지", "이 서비스가 어떤 다른 서비스에 영향을 주는지"는 모른다.

```
✅ v0.1~v0.3 — 코드 구조 분석
  - PR 범위 적절 (단일 도메인 CRUD)
  - API 스펙 린트 통과
  - 리뷰 체크리스트 생성

❌ v0.4가 해결할 것 — 맥락 부재
  - payment-service를 변경했는데, 이 서비스를 호출하는 order-service에 영향은?
  - "nullable 필드는 반드시 스펙에 명시" 규정이 있는데, 근거 문서를 첨부할 수 없다
  - 설계 문서에는 A→B 호출이 있는데, 실제 트레이스에는 없다 — 이 PR이 그걸 구현하는 건가?
```

### 칼라(Khala)가 제공하는 것

칼라는 **Enterprise RAG + GraphRAG 시스템**이다. 두 종류의 지식을 보유한다:

1. **설계 지식** (Designed) — 규정 문서, 아키텍처 문서, API 계약서 (Git → 인덱싱)
2. **관측 지식** (Observed) — OTel 트레이스로 관측된 실제 서비스 호출 패턴

| 칼라 API | Karax에서의 활용 |
|----------|-----------------|
| `POST /search` | 변경 관련 규정/문서 검색 → 리뷰 근거 첨부 |
| `POST /search/answer` | 변경에 대한 근거 기반 답변 생성 |
| `GET /graph/{entity_rid}` | 서비스 의존 관계 → 영향 범위 분석 |
| `GET /diff` | 설계 vs 관측 불일치 → 리뷰 시 경고 |

### 사용자 경험 변화

**Before (v0.3):**
```
사용자: "PR 리뷰해줘"
Karax: 범위 OK, API 린트 통과, 체크리스트 5개 항목
       → "서비스 테스트가 있는지 확인하세요" (일반적 조언)
```

**After (v0.4):**
```
사용자: "PR 리뷰해줘"
Karax: 범위 OK, API 린트 통과, 체크리스트 5개 항목
       + 📎 관련 규정: "nullable 필드 표기 의무" (규정 ② 2.3.1)
       + 📎 영향 서비스: order-service, notification-service가 payment-service를 호출
       + ⚠️ 설계-관측 갭: payment → inventory 호출이 설계에 있지만 트레이스에 없음
       → "payment-service의 processPayment()를 변경했는데,
          order-service가 이 메서드를 호출합니다. 하위 호환성을 확인하세요." (맥락 있는 조언)
```

---

## 2. 아키텍처

### 2.1 연동 구조

```
┌─────────────────────────────────────────────────────┐
│ Claude Code                                         │
│                                                     │
│   MCP tool call                                     │
│       ↓                                             │
│   ┌───────────────────────────────────────────┐     │
│   │ Karax MCP 서버 (v0.3)                      │     │
│   │                                           │     │
│   │   ┌─────────────┐   ┌──────────────────┐  │     │
│   │   │ 코어 엔진    │   │ Khala 클라이언트   │  │     │
│   │   │ (v0.1~v0.2) │   │ (v0.4 신규)      │  │     │
│   │   └─────────────┘   └────────┬─────────┘  │     │
│   │                              │             │     │
│   └──────────────────────────────┼─────────────┘     │
│                                  │ HTTP               │
└──────────────────────────────────┼───────────────────┘
                                   ↓
                    ┌──────────────────────────┐
                    │ Khala API 서버             │
                    │ (FastAPI, PostgreSQL,     │
                    │  pgvector, mecab-ko)      │
                    └──────────────────────────┘
```

### 2.2 새로운 모듈 구조

```
src/
├── khala/                         ← v0.4 신규 — 칼라 연동 레이어
│   ├── client.ts                  ← HTTP 클라이언트 (fetch 기반)
│   ├── types.ts                   ← 칼라 응답 타입 정의
│   ├── context-enricher.ts        ← 리뷰 컨텍스트 보강 오케스트레이터
│   └── impact-analyzer.ts         ← 서비스 영향 분석
├── core/
│   └── review-checklist.ts        ← 수정: 칼라 컨텍스트 반영
├── mcp/
│   └── tools.ts                   ← 수정: enriched 결과 반환
└── ...
```

### 2.3 설계 원칙

1. **칼라는 선택적이다** — 칼라가 없어도 v0.1~v0.3 기능은 그대로 동작한다. 칼라가 있으면 결과가 풍부해진다.
2. **칼라 장애 시 graceful degradation** — 타임아웃 3초, 실패 시 기존 결과만 반환. 에러를 삼키되, 로그는 남긴다.
3. **칼라는 읽기 전용** — Karax는 칼라에 데이터를 쓰지 않는다. 검색과 조회만 한다.
4. **응답 캐싱 없음** (v0.4) — 단순하게 시작한다. 성능이 문제가 되면 v0.5+에서 캐싱을 추가한다.

---

## 3. 칼라 클라이언트

### 3.1 `KhalaClient`

칼라 API를 호출하는 HTTP 클라이언트. Node.js 내장 `fetch`를 사용한다.

```typescript
// src/khala/client.ts

interface KhalaClientConfig {
  baseUrl: string;        // 기본: http://localhost:8000
  timeoutMs: number;      // 기본: 3000
  tenant: string;         // 기본: "default"
  classificationMax: string; // 기본: "INTERNAL"
}

class KhalaClient {
  /**
   * 하이브리드 검색 (BM25 + Vector + Graph + RRF)
   */
  async search(query: string, options?: {
    topK?: number;
    includeGraph?: boolean;
    includeEvidence?: boolean;
  }): Promise<KhalaSearchResult>

  /**
   * 검색 + LLM 근거 기반 답변
   */
  async searchAnswer(query: string, options?: {
    topK?: number;
  }): Promise<KhalaAnswerResult>

  /**
   * 엔티티 그래프 조회 (1~2홉 이웃)
   */
  async getGraph(entityRid: string, options?: {
    hops?: number;
  }): Promise<KhalaGraphResult>

  /**
   * 설계-관측 diff 보고서
   */
  async getDiff(options?: {
    flagFilter?: string;
  }): Promise<KhalaDiffResult>

  /**
   * 칼라 서버 상태 확인
   */
  async isAvailable(): Promise<boolean>
}
```

### 3.2 에러 처리

```typescript
// 모든 칼라 호출은 이 패턴을 따른다
async function withKhalaFallback<T>(
  fn: () => Promise<T>,
  fallback: T,
  context: string,
): Promise<T> {
  try {
    return await fn();
  } catch (error) {
    logger.debug(`칼라 조회 실패 (${context}): ${error} — 기본값으로 진행`);
    return fallback;
  }
}
```

타임아웃(3초), 네트워크 에러, 5xx 응답 모두 동일하게 fallback으로 처리한다. 칼라가 없으면 기존 결과만 반환.

---

## 4. 컨텍스트 보강

### 4.1 `ContextEnricher`

PR 분석 결과에 칼라의 맥락을 추가하는 오케스트레이터.

```typescript
// src/khala/context-enricher.ts

interface EnrichmentResult {
  /** 관련 규정/문서 스니펫 */
  relevantDocs: RelevantDoc[];
  /** 영향받는 서비스 (graph neighbor) */
  impactedServices: ImpactedService[];
  /** 설계-관측 불일치 */
  designObservationGaps: DesignGap[];
  /** 칼라 가용 여부 */
  khalaAvailable: boolean;
}

interface RelevantDoc {
  docTitle: string;
  sectionPath: string;
  snippet: string;
  score: number;
  classification: string;
}

interface ImpactedService {
  name: string;
  rid: string;
  relationship: string;    // "calls" | "called_by" | "publishes_to" | "subscribes_from"
  confidence: number;
  /** 관측 데이터가 있으면 포함 */
  observed?: {
    callCount: number;
    errorRate: number;
    latencyP95: number;
  };
}

interface DesignGap {
  flag: string;            // "doc_only" | "observed_only" | "conflict"
  fromName: string;
  toName: string;
  edgeType: string;
  detail: string;
  /** 설계 근거 (문서 스니펫) */
  designedEvidence?: string;
  /** 관측 근거 (트레이스 ID) */
  observedEvidence?: string[];
}
```

### 4.2 보강 흐름

```
PR 변경 파일 분석 완료 (v0.1~v0.3)
       ↓
  ① 서비스명 추출
     - 파일 경로에서 서비스/도메인명 추출
     - 예: src/main/kotlin/service/PaymentService.kt → "payment-service"
       ↓
  ② 병렬 칼라 조회 (3개 동시)
     ├─ search: "payment-service API 계약 규정" → 관련 문서
     ├─ graph: entity_rid("payment-service") → 의존 서비스
     └─ diff: flag_filter=null → 설계-관측 갭
       ↓
  ③ 결과 조립
     - 관련 문서 → 리뷰 근거로 첨부
     - 의존 서비스 → 영향 범위 경고
     - 설계-관측 갭 → 변경과 관련된 것만 필터
       ↓
  EnrichmentResult 반환
```

### 4.3 서비스명 추출 전략

변경 파일에서 서비스/도메인명을 추출한다. 플랫폼 프로파일의 `fileRoles`를 활용한다.

```typescript
/**
 * 변경 파일 목록에서 서비스/도메인 키워드를 추출한다.
 * 이 키워드로 칼라에 검색 쿼리를 만든다.
 */
function extractServiceNames(
  files: string[],
  groups: CohesionGroup[],
): string[] {
  // 1. cohesionGroup의 cohesionKey에서 추출
  //    예: { role: "Service", cohesionKey: "payment" } → "payment-service"
  // 2. 중복 제거 후 반환
}
```

---

## 5. 영향 분석

### 5.1 `ImpactAnalyzer`

변경된 서비스의 upstream/downstream을 칼라 그래프에서 조회하고, 영향 범위를 판단한다.

```typescript
// src/khala/impact-analyzer.ts

interface ImpactAnalysis {
  /** 변경된 서비스 */
  changedServices: string[];
  /** 직접 영향 (1홉) */
  directImpact: ImpactedService[];
  /** 간접 영향 (2홉) */
  indirectImpact: ImpactedService[];
  /** 영향 요약 */
  summary: string;
  /** 심각도: none | low | medium | high */
  severity: 'none' | 'low' | 'medium' | 'high';
}
```

### 5.2 심각도 판단 기준

| 심각도 | 조건 |
|--------|------|
| `none` | 다른 서비스에 영향 없음 |
| `low` | 1~2개 서비스가 영향받지만, 하위 호환 변경 |
| `medium` | 3개 이상 서비스 영향, 또는 설계-관측 갭 존재 |
| `high` | breaking 변경 + 다수 서비스 영향, 또는 error rate 높은 경로 변경 |

---

## 6. 기존 기능 확장

### 6.1 리뷰 체크리스트 확장

`generateReviewChecklist()`의 결과에 칼라 컨텍스트를 추가한다.

```typescript
// 기존 ReviewChecklist에 추가되는 필드
interface EnrichedReviewChecklist extends ReviewChecklist {
  /** 칼라에서 가져온 관련 규정 */
  relevantDocs?: RelevantDoc[];
  /** 영향 분석 결과 */
  impact?: ImpactAnalysis;
  /** 설계-관측 갭 */
  designGaps?: DesignGap[];
}
```

### 6.2 MCP 도구 확장

기존 5개 MCP 도구 중 2개를 확장한다:

#### `karax.reviewChecklist` 확장

```typescript
// 기존 입력에 추가
{
  enrichWithKhala: {
    type: "boolean",
    description: "칼라에서 맥락을 보강할지 여부 (기본: true, 칼라 사용 가능 시)",
    default: true,
  }
}

// 반환에 추가
{
  // 기존 필드...
  khalaEnrichment: {
    relevantDocs: [...],
    impact: {...},
    designGaps: [...],
    khalaAvailable: true,
  }
}
```

#### `karax.analyzeScope` 확장

```typescript
// 반환에 추가
{
  // 기존 필드...
  khalaEnrichment: {
    impactedServices: [...],
    khalaAvailable: true,
  }
}
```

### 6.3 MCP 도구 신규 (1개)

#### `karax.queryKhala`

칼라에 직접 자연어 질의를 보내는 범용 도구.

```typescript
{
  name: "karax.queryKhala",
  description: "칼라 지식베이스에 자연어로 질의한다. 규정, 아키텍처, 서비스 관계를 검색한다.",
  inputSchema: {
    type: "object",
    properties: {
      query: {
        type: "string",
        description: "검색 쿼리 (자연어, 한국어/영어)",
      },
      mode: {
        type: "string",
        enum: ["search", "answer", "graph", "diff"],
        description: "검색 모드 (기본: search)",
        default: "search",
      },
      entityName: {
        type: "string",
        description: "그래프/diff 모드에서 대상 엔티티명",
      },
    },
    required: ["query"],
  },
}
```

### 6.4 MCP 프롬프트 확장

#### `karax.prReview` 확장

기존 프롬프트의 분석 결과에 칼라 컨텍스트를 포함한다:

```
## Karax 분석 결과
{기존 scope + checklist}

## 칼라 맥락 (Khala Context)

### 관련 규정
- 규정 ② 2.3.1: "nullable 필드는 스펙에 명시" (출처: api-contract-guidelines.md > 2.3)
- 규정 ① 3.1: "에러 상태는 State Matrix에 정의" (출처: state-matrix-guidelines.md > 3)

### 영향 서비스
- order-service → payment-service (CALLS, 일 1,200회, error rate 0.1%)
- notification-service → payment-service (CALLS, 일 800회)

### 설계-관측 갭
- ⚠️ payment → inventory: 설계에 있지만 트레이스에 없음 (doc_only)
```

### 6.5 CLI 확장

```
karax check          기존 + 칼라 컨텍스트 (가용 시)
karax khala:search   칼라 직접 검색
karax khala:impact   영향 분석
karax khala:status   칼라 연결 상태 확인
```

---

## 7. 설정

### 7.1 `karax.config.ts` 확장

```typescript
interface KaraxConfig {
  // 기존 설정...

  /** 칼라 연동 설정 */
  khala?: {
    /** 칼라 API 서버 URL (기본: http://localhost:8000) */
    baseUrl?: string;
    /** 요청 타임아웃 (ms, 기본: 3000) */
    timeoutMs?: number;
    /** 테넌트 (기본: "default") */
    tenant?: string;
    /** 최대 분류 등급 (기본: "INTERNAL") */
    classificationMax?: string;
    /** 칼라 연동 비활성화 (기본: false) */
    disabled?: boolean;
    /** 검색 결과 최대 건수 (기본: 5) */
    searchTopK?: number;
    /** 그래프 탐색 홉 수 (기본: 1) */
    graphHops?: number;
  };
}
```

### 7.2 환경 변수

설정 파일 없이도 환경 변수로 연동할 수 있다:

```
KHALA_BASE_URL=http://localhost:8000
KHALA_TIMEOUT_MS=3000
KHALA_TENANT=default
KHALA_DISABLED=false
```

우선순위: `karax.config.ts` > 환경 변수 > 기본값

---

## 8. 구현 순서

### Phase 1: 기반

1. `src/khala/types.ts` — 칼라 응답 타입 정의
2. `src/khala/client.ts` — HTTP 클라이언트 + graceful degradation
3. `src/core/config-loader.ts` — 칼라 설정 추가
4. `tests/khala-client.test.ts` — 클라이언트 테스트 (모킹)

### Phase 2: 컨텍스트 보강

5. `src/khala/context-enricher.ts` — 보강 오케스트레이터
6. `src/khala/impact-analyzer.ts` — 영향 분석
7. `tests/context-enricher.test.ts` — 보강 테스트
8. `tests/impact-analyzer.test.ts` — 영향 분석 테스트

### Phase 3: 통합

9. `src/mcp/tools.ts` — 기존 도구 확장 + `queryKhala` 신규
10. `src/mcp/prompts.ts` — prReview 프롬프트 확장
11. `src/cli/index.ts` — CLI 확장 (`khala:*` 커맨드)
12. `src/index.ts` — 공개 API 확장
13. `tests/mcp-khala.test.ts` — MCP 통합 테스트

### Phase 4: 마무리

14. `package.json` — v0.4.0
15. CLAUDE.md 업데이트
16. 전체 테스트 + 빌드 확인

---

## 9. 하지 않는 것 (명시적 제외)

| 제외 항목 | 이유 |
|-----------|------|
| 칼라에 데이터 쓰기 | Karax는 읽기 전용. 인덱싱은 칼라의 책임 |
| 응답 캐싱 | v0.4는 단순하게. 성능 문제 시 v0.5+ |
| 칼라 인증/토큰 | v0.4는 내부 네트워크 가정. 외부 노출 시 v0.5+ |
| 칼라 서버 관리 | 칼라의 docker-compose는 칼라 프로젝트에서 관리 |
| OTel 직접 조회 | 칼라가 OTel을 추상화. Karax는 칼라만 호출 |
| LLM 답변 생성 | `searchAnswer` 호출은 가능하지만, 기본 모드는 `search` (스니펫만) |

---

## 10. 성공 기준

1. 칼라 서버가 실행 중일 때, `karax check`에 관련 규정과 영향 서비스가 표시된다
2. 칼라 서버가 없을 때, 기존 v0.3 기능이 그대로 동작한다 (degradation)
3. MCP 도구 `karax.reviewChecklist`가 칼라 컨텍스트를 포함한다
4. MCP 도구 `karax.queryKhala`로 칼라에 직접 질의할 수 있다
5. 타임아웃 3초 이내에 칼라 조회가 완료된다
6. 모든 기존 테스트 통과 + 칼라 관련 신규 테스트 통과
