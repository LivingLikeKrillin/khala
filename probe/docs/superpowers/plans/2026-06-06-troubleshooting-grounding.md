# Probe v0.5 — 트러블슈팅 그라운딩 Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 에러/스택트레이스/실패 테스트를 입력받아, 근본원인을 단정하지 않고 조직 컨텍스트(토폴로지·관측·규정·최근변경·도메인 불변식)를 묶은 **Grounding Pack**을 만들어 Claude/사람의 디버깅 추론에 깔아주는 기능을 Probe에 추가한다.

**Architecture:** 기존 하이브리드 구조(`src/` 코어 + `.claude/` 어댑터)에 정합. 신규 모듈은 `src/khala/error-localizer.ts`(에러→의심지점), `src/khala/troubleshoot-grounder.ts`(Grounding Pack 조립), `src/core/troubleshoot.ts`(오케스트레이션+티어). 기존 `KhalaClient`를 확장(`getStatus`, `getDiff` entityFilter)하고 CLI/MCP 표면을 더한다. Khala가 없거나 빈약해도 동작하는 **티어 강등(T0~T3)** 을 명시 보고한다.

**Tech Stack:** TypeScript (strict, ESM `.js` imports) · vitest (fetch 목킹) · zod (MCP 스키마) · `@modelcontextprotocol/sdk` · Node ≥20 · pnpm

**Spec:** `probe/docs/superpowers/specs/2026-06-06-troubleshooting-grounding-design.md` (specledger·Archon 비충돌 리뷰 통과)

**핵심 원칙 (CLAUDE.md):** `any` 금지(`unknown`+가드), `console.log` 금지(`logger`), 에러 메시지 한국어 우선·영어 병기, core 변경 시 테스트 필수, 외부 도구는 래퍼 경유. 파일 kebab-case / 타입 PascalCase / 함수 camelCase.

**커밋 규약:** `feat:` / `fix:` / `test:` / `refactor:` / `docs:` / `chore:`. 각 Task 끝에 1회 커밋.

**빌드/테스트 명령:**
- 단일 테스트: `pnpm vitest run tests/<file>.test.ts -t "<title>"`
- 전체: `pnpm test:run`
- 타입: `pnpm typecheck`

---

## 실행 순서 개요 (시그니처 시나리오 먼저)

| Chunk | 내용 | 게이트 |
|-------|------|--------|
| 1 | 기반 타입 + `KhalaClient` 확장(`getStatus`, `getDiff` entityFilter) | — |
| 2 | `error-localizer` (에러→Suspect) | — |
| **3** | **시그니처 시나리오 마일스톤** (시드 + S1/S2/S3 대조) | **★ 해자 실증 게이트 — 실패 시 중단·재검토** |
| 4 | `troubleshoot-grounder` (6~7개 섹션 → GroundingPack) | — |
| 5 | `core/troubleshoot` (티어 결정 + 입력검증 + 오케스트레이션) | — |
| 6 | CLI 표면 (`parse-args`, `formatters`, `troubleshoot` 커맨드) | — |
| 7 | MCP 도구 `probe.groundTroubleshooting` + 최종 배선 | — |

> Chunk 3이 **가설 검증 게이트**다. 여기서 "그라운딩만이 낼 수 있는 발견"(observed_only 갭)이 실증되지 않으면 Chunk 4~7로 진행하지 말고 사람에게 보고한다(스펙 §8.2).

---

## File Structure

| 파일 | 책임 | 신규/수정 |
|------|------|-----------|
| `src/khala/types.ts` | `Suspect`, `KhalaStatusResult`, `GroundingPack`, `ClaimRef` 등 타입 | 수정 |
| `src/khala/client.ts` | `getStatus()` 신규, `getDiff({entityFilter})` 확장 | 수정 |
| `src/khala/error-localizer.ts` | 에러/스택트레이스 → `Suspect[]` (순수 로컬) | 신규 |
| `src/khala/troubleshoot-grounder.ts` | `Suspect[]`+`KhalaClient` → `GroundingPack` 섹션 조립 | 신규 |
| `src/core/troubleshoot.ts` | 입력 파싱·티어 결정·오케스트레이션·caveats | 신규 |
| `src/cli/parse-args.ts` | `--kind`, `--diff-base`, `--suspect`, stdin 입력 | 수정 |
| `src/cli/formatters.ts` | `formatGroundingPackMarkdown/Brief` | 수정 |
| `src/cli/index.ts` | `troubleshoot` 커맨드 등록 | 수정 |
| `src/mcp/tools.ts` | `probe.groundTroubleshooting` 도구 | 수정 |
| `scripts/seed-signature-scenario.sql` | S1 재현용 Khala 시드 (검증 전용) | 신규 |
| `tests/*.test.ts` | 각 모듈 테스트 | 신규 |

---

## Chunk 1: 기반 타입 + KhalaClient 확장

### Task 1: Grounding 타입 정의

**Files:**
- Modify: `src/khala/types.ts` (파일 끝에 추가)
- Test: `tests/troubleshoot-types.test.ts` (타입은 런타임 테스트가 없으므로, 타입 컴파일을 보장하는 최소 사용 테스트)

- [ ] **Step 1: 타입 추가**

`src/khala/types.ts` 끝에 추가:

```typescript
// ─── 트러블슈팅 그라운딩 (v0.5) ───

/**
 * /status 응답 (가용성·티어 진단용).
 * 필드는 khala `api.py` status() (812~852행)가 반환하는 카운트와 일치:
 * documents_count/edges_count/observed_edges_count/diff_summary는 db_connected일 때만 채워짐.
 */
export interface KhalaStatusResult {
  db_connected: boolean;
  ollama_connected?: boolean;
  tempo_connected?: boolean;
  documents_count?: number;
  chunks_count?: number;
  entities_count?: number;
  edges_count?: number;
  observed_edges_count?: number;
  diff_summary?: {
    doc_only_count: number;
    observed_only_count: number;
    conflict_count: number;
  };
}

/** 트러블슈팅 입력 */
export interface TroubleshootInput {
  /** 에러 신호 본문 (스택트레이스 | 에러 메시지 | 실패 테스트 출력 | 인시던트 설명) */
  signal: string;
  /** 신호 종류 힌트 (생략 시 휴리스틱 추론) */
  kind?: 'stacktrace' | 'error' | 'test-failure' | 'incident';
  /** 선택: 최근 변경 상관 분석 (git diff base) */
  diffBase?: string;
  /** 선택: 사용자가 지목한 의심 서비스 */
  suspectServices?: string[];
}

/** 국소화 산출물 — §1 / localizer→grounder 계약 */
export interface Suspect {
  /** grounder가 getGraph/getDiff에 넘길 정규화된 service/entity 후보명 */
  entityName: string;
  /** 국소화 근거 */
  evidence: { kind: 'frame' | 'path' | 'user' | 'keyword'; raw: string }[];
  /** 0~1. 임계(0.3) 미만은 caveats로만 보고 */
  confidence: number;
}

/** Archon claim의 읽기 전용 투영 (Archon 연동 시에만) */
export interface ClaimRef {
  id: string;
  kind: 'goal' | 'invariant' | 'requirement';
  statement: string;
  status: string;
  criticality: 'core' | 'peripheral';
  confidence: 'high' | 'medium' | 'low';
  codeDrift: boolean;
  owner: string;
  boundSymbol: string;
}

/** 운영 신호 이상치 (§4) */
export interface OperationalSignal {
  fromName: string;
  toName: string;
  callCount: number;
  errorRate: number;
  latencyP95: number;
  /** 이상 판정 근거 (예: "error_rate 0.20 > 임계 0.05") */
  anomaly: string;
}

/** 최근 변경 상관 (§6) */
export interface ChangeLink {
  service: string;
  changedFiles: string[];
  relationship: string;
}

/** 트러블슈팅 그라운딩 결과 */
export interface GroundingPack {
  tier: 0 | 1 | 2 | 3;
  tierReason: string;
  suspects: Suspect[];
  knowledge?: RelevantDoc[];          // §5 (T1+)
  topology?: ImpactAnalysis;          // §2 (T2+) — 기존 ImpactAnalysis 재사용
  designObservationGaps?: DesignGap[]; // §3 — 기존 DesignGap 재사용
  operationalSignals?: OperationalSignal[]; // §4 (T3)
  changeCorrelation?: ChangeLink[];   // §6 (diffBase 제공 시)
  domainInvariants?: ClaimRef[];      // §4.2 seam (Archon 연동 시)
  caveats: string[];
}
```

- [ ] **Step 2: 타입 사용 테스트 작성**

`tests/troubleshoot-types.test.ts`:

```typescript
import { describe, it, expect } from 'vitest';
import type { GroundingPack, Suspect } from '../src/khala/types.js';

describe('트러블슈팅 타입', () => {
  it('GroundingPack을 최소 형태로 구성할 수 있다', () => {
    const suspect: Suspect = { entityName: 'order-service', evidence: [], confidence: 0.9 };
    const pack: GroundingPack = {
      tier: 0,
      tierReason: 'Khala 미가용',
      suspects: [suspect],
      caveats: [],
    };
    expect(pack.suspects[0]!.entityName).toBe('order-service');
    expect(pack.tier).toBe(0);
  });
});
```

- [ ] **Step 3: 테스트 실행 (통과 확인)**

Run: `pnpm vitest run tests/troubleshoot-types.test.ts`
Expected: PASS (타입이 올바르면 컴파일+통과)

- [ ] **Step 4: 타입체크**

Run: `pnpm typecheck`
Expected: 에러 없음

- [ ] **Step 5: Commit**

```bash
git add src/khala/types.ts tests/troubleshoot-types.test.ts
git commit -m "feat: add troubleshooting grounding types (Suspect, GroundingPack, KhalaStatusResult)"
```

---

### Task 2: KhalaClient.getStatus()

**Files:**
- Modify: `src/khala/client.ts`
- Test: `tests/khala-client.test.ts` (기존 파일에 describe 추가)

- [ ] **Step 1: 실패 테스트 작성**

`tests/khala-client.test.ts` 끝에 추가 (기존 import 재사용; 없으면 추가):

```typescript
describe('KhalaClient.getStatus', () => {
  let originalFetch: typeof globalThis.fetch;
  beforeEach(() => { originalFetch = globalThis.fetch; });
  afterEach(() => { globalThis.fetch = originalFetch; });

  it('상태 카운트를 반환한다', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true, status: 200,
      json: () => Promise.resolve({
        success: true,
        data: { db_connected: true, edges_count: 12, observed_edges_count: 3 },
        error: null, meta: {},
      }),
    });
    const client = new KhalaClient({ baseUrl: 'http://test:8000' });
    const status = await client.getStatus();
    expect(status?.observed_edges_count).toBe(3);
    expect(status?.edges_count).toBe(12);
  });

  it('서버 장애 시 null을 반환한다', async () => {
    globalThis.fetch = vi.fn().mockRejectedValue(new Error('conn refused'));
    const client = new KhalaClient({ baseUrl: 'http://test:8000' });
    expect(await client.getStatus()).toBeNull();
  });
});
```

- [ ] **Step 2: 실행 → 실패 확인**

Run: `pnpm vitest run tests/khala-client.test.ts -t "상태 카운트를 반환한다"`
Expected: FAIL (`getStatus` is not a function)

- [ ] **Step 3: 구현**

`src/khala/client.ts`의 `isAvailable()` 메서드 바로 아래에 추가하고, import에 `KhalaStatusResult` 추가:

```typescript
  /**
   * 시스템 상태를 조회한다 (가용성·티어 진단용).
   *
   * isAvailable()이 boolean만 주는 것과 달리, 카운트 본문을 반환한다.
   */
  async getStatus(): Promise<KhalaStatusResult | null> {
    return this.get<KhalaStatusResult>('/status', 'getStatus');
  }
```

타입 import 수정 (파일 상단 import 블록):

```typescript
import type {
  KhalaClientConfig,
  KhalaResponse,
  KhalaSearchResult,
  KhalaAnswerResult,
  KhalaGraphResult,
  KhalaDiffResult,
  KhalaStatusResult,
} from './types.js';
```

- [ ] **Step 4: 실행 → 통과 확인**

Run: `pnpm vitest run tests/khala-client.test.ts -t "KhalaClient.getStatus"`
Expected: PASS (2건)

- [ ] **Step 5: Commit**

```bash
git add src/khala/client.ts tests/khala-client.test.ts
git commit -m "feat: add KhalaClient.getStatus() returning typed status counts"
```

---

### Task 3: KhalaClient.getDiff() entityFilter 확장

**Files:**
- Modify: `src/khala/client.ts`
- Test: `tests/khala-client.test.ts`

- [ ] **Step 1: 실패 테스트 작성**

```typescript
describe('KhalaClient.getDiff entityFilter', () => {
  let originalFetch: typeof globalThis.fetch;
  beforeEach(() => { originalFetch = globalThis.fetch; });
  afterEach(() => { globalThis.fetch = originalFetch; });

  it('entityFilter를 쿼리 파라미터로 전송한다', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true, status: 200,
      json: () => Promise.resolve({ success: true, data: { diffs: [] }, error: null, meta: {} }),
    });
    globalThis.fetch = fetchMock;
    const client = new KhalaClient({ baseUrl: 'http://test:8000' });
    await client.getDiff({ entityFilter: 'order-service' });
    const calledUrl = String(fetchMock.mock.calls[0]![0]);
    expect(calledUrl).toContain('entity_filter=order-service');
  });
});
```

- [ ] **Step 2: 실행 → 실패 확인**

Run: `pnpm vitest run tests/khala-client.test.ts -t "entityFilter를 쿼리"`
Expected: FAIL (entity_filter 미포함)

- [ ] **Step 3: 구현**

`src/khala/client.ts`의 기존 `getDiff` 메서드를 교체:

```typescript
  /**
   * 설계-관측 diff 보고서.
   */
  async getDiff(options?: {
    flagFilter?: string;
    entityFilter?: string;
  }): Promise<KhalaDiffResult | null> {
    const params = new URLSearchParams({ tenant: this.config.tenant });
    if (options?.flagFilter) {
      params.set('flag_filter', options.flagFilter);
    }
    if (options?.entityFilter) {
      params.set('entity_filter', options.entityFilter);
    }
    return this.get<KhalaDiffResult>(`/diff?${params.toString()}`, 'getDiff');
  }
```

- [ ] **Step 4: 실행 → 통과 확인 (기존 getDiff 테스트도 회귀 확인)**

Run: `pnpm vitest run tests/khala-client.test.ts`
Expected: PASS (신규 + 기존 전부)

- [ ] **Step 5: Commit**

```bash
git add src/khala/client.ts tests/khala-client.test.ts
git commit -m "feat: add entityFilter option to KhalaClient.getDiff()"
```

---

### Task 3b: analyzeImpact를 이름 기반 그래프 조회로 수정 (스펙 §3.3 계약 준수)

> **왜 필요한가 (블로커):** 현재 `impact-analyzer.ts:57`은 `client.getGraph(buildEntityRid(name), …)`로
> 호출하는데, `buildEntityRid`(264~270)는 `ent_<serviceName>` 같은 **가짜 rid**를 만든다. 실제
> Khala rid는 `ent_` + sha256(...)[:12]이라 이 값은 절대 매칭되지 않는다. 게다가 `/graph`
> 엔드포인트는 이름 기반 조회를 지원하지만(`api.py` get_graph 392~405: `ent_`로 시작 안 하면
> name으로 조회), `ent_` 접두사를 붙이면 서버가 rid로 오인해 404 → 토폴로지·운영신호가 **조용히
> 빈값**이 된다. 스펙 §3.3은 "Probe는 rid를 직접 만들지 않고 이름을 그대로 넘긴다"를 명시한다.

**Files:**
- Modify: `src/khala/impact-analyzer.ts`
- Test: `tests/impact-analyzer.test.ts`

- [ ] **Step 1: 실패 테스트 추가** — getGraph가 `ent_` 없는 이름으로 호출되는지 검증

```typescript
it('getGraph를 ent_ 접두사 없이 이름으로 호출한다 (스펙 §3.3)', async () => {
  const fetchMock = vi.fn().mockResolvedValue({
    ok: true, status: 200,
    json: () => Promise.resolve({ success: true, data: { center_entity: { rid: 'x', name: 'order-service' }, edges: [], observed_edges: [] }, error: null, meta: {} }),
  });
  globalThis.fetch = fetchMock;
  const client = new KhalaClient({ baseUrl: 'http://test:8000' });
  await analyzeImpact(client, ['order-service']);
  const calledUrl = String(fetchMock.mock.calls[0]![0]);
  expect(calledUrl).toContain('/graph/order-service');
  expect(calledUrl).not.toContain('ent_');
});
```

- [ ] **Step 2: 실행 → 실패 확인**

Run: `pnpm vitest run tests/impact-analyzer.test.ts -t "ent_ 접두사 없이"`
Expected: FAIL (현재 `/graph/ent_order-service`로 호출됨)

- [ ] **Step 3: 구현** — `src/khala/impact-analyzer.ts`

`analyzeImpact` 내부의 `() => client.getGraph(buildEntityRid(name), { hops })`를
`() => client.getGraph(name, { hops })`로 변경하고, 이제 미사용이 된 `buildEntityRid` 함수(264~270)를 삭제한다.

- [ ] **Step 4: 실행 → 통과 확인 (기존 영향분석 테스트 회귀 포함)**

Run: `pnpm vitest run tests/impact-analyzer.test.ts`
Expected: PASS (신규 + 기존). 기존 테스트가 fetch를 목킹하므로 URL 변경에도 통과해야 함; 만약 기존 테스트가 `ent_` URL을 단언했다면 그 단언도 이름 기반으로 갱신.

- [ ] **Step 5: Commit**

```bash
git add src/khala/impact-analyzer.ts tests/impact-analyzer.test.ts
git commit -m "fix: analyzeImpact uses name-based /graph lookup (drop fabricated rid)"
```

---

### Chunk 1 검토

- [ ] plan-document-reviewer로 Chunk 1 검토 → 이슈 수정 → 재검토 (통과 시 Chunk 2)

---

## Chunk 2: error-localizer (에러 → Suspect)

### Task 4: Java 스택트레이스 국소화

**Files:**
- Create: `src/khala/error-localizer.ts`
- Test: `tests/error-localizer.test.ts`

- [ ] **Step 1: 실패 테스트 작성**

`tests/error-localizer.test.ts`:

```typescript
import { describe, it, expect } from 'vitest';
import { localizeError } from '../src/khala/error-localizer.js';

describe('localizeError — Java 스택트레이스', () => {
  it('클래스명을 kebab service로 정규화한다', () => {
    const signal = 'java.lang.NullPointerException\n\tat com.shop.order.OrderService.checkout(OrderService.java:88)';
    const suspects = localizeError({ signal, kind: 'stacktrace' });
    expect(suspects[0]!.entityName).toBe('order-service');
    expect(suspects[0]!.confidence).toBeGreaterThan(0.3);
    expect(suspects[0]!.evidence.some((e) => e.kind === 'frame')).toBe(true);
  });

  it('Service/Controller/Repository 접미사를 제거한다', () => {
    const signal = '\tat com.shop.PaymentController.pay(PaymentController.java:12)';
    const suspects = localizeError({ signal, kind: 'stacktrace' });
    expect(suspects[0]!.entityName).toBe('payment');
  });

  it('suspectServices 사용자 지정을 최상위 confidence로 포함한다', () => {
    const suspects = localizeError({ signal: '에러 발생', suspectServices: ['inventory-service'] });
    expect(suspects[0]!.entityName).toBe('inventory-service');
    expect(suspects[0]!.evidence[0]!.kind).toBe('user');
    expect(suspects[0]!.confidence).toBe(1);
  });

  it('의심 지점이 없으면 빈 배열을 반환한다', () => {
    expect(localizeError({ signal: '그냥 텍스트' })).toEqual([]);
  });
});
```

- [ ] **Step 2: 실행 → 실패 확인**

Run: `pnpm vitest run tests/error-localizer.test.ts`
Expected: FAIL (모듈 없음)

- [ ] **Step 3: 구현**

`src/khala/error-localizer.ts`:

```typescript
/**
 * 에러/스택트레이스 → 의심 지점(Suspect) 국소화
 *
 * 순수 로컬(Khala 호출 없음). 스택트레이스 프레임·파일 경로·사용자 지정에서
 * service/entity 후보를 추출해 confidence 내림차순으로 반환한다.
 *
 * 주의(스펙 §4.2 seam): Archon 코드 심볼 인덱스가 생기면 그쪽을 결정론적 1순위로,
 * 본 휴리스틱은 fallback이 된다. 따라서 과투자하지 않는다 (스펙 Q2).
 *
 * 규정 문서: docs/superpowers/specs/2026-06-06-troubleshooting-grounding-design.md §1, §3.3
 */

import type { TroubleshootInput, Suspect } from './types.js';

/** Java/Kotlin 프레임: at a.b.c.ClassName.method(File.java:88) */
const JAVA_FRAME = /\bat\s+(?:[\w$]+\.)*([A-Z][\w$]+)\.[\w$<>]+\(/g;
/** 파일 경로 프레임: src/order/order-service.ts:88 또는 (order-service.ts:88) */
const PATH_FRAME = /([\w-]+)(?:\.(?:ts|tsx|js|jsx|java|kt|py))\b/g;
/** service 후보로 보는 흔한 접미사 (제거 대상) */
const ROLE_SUFFIX = /(Service|Controller|Repository|Handler|Manager|UseCase|Component)$/;

/** PascalCase/대문자 클래스명을 kebab service명으로 정규화 */
function toServiceName(symbol: string): string {
  const stripped = symbol.replace(ROLE_SUFFIX, '');
  return stripped
    .replace(/([a-z0-9])([A-Z])/g, '$1-$2')
    .replace(/[_\s]+/g, '-')
    .toLowerCase();
}

/**
 * 에러 신호에서 의심 지점을 국소화한다.
 *
 * @param input 트러블슈팅 입력
 * @returns confidence 내림차순 Suspect 배열 (없으면 빈 배열)
 */
export function localizeError(input: TroubleshootInput): Suspect[] {
  const byName = new Map<string, Suspect>();

  const add = (
    entityName: string,
    ev: Suspect['evidence'][number],
    score: number,
  ): void => {
    if (!entityName) return;
    const existing = byName.get(entityName);
    if (existing) {
      existing.evidence.push(ev);
      existing.confidence = Math.min(1, existing.confidence + 0.15);
    } else {
      byName.set(entityName, { entityName, evidence: [ev], confidence: score });
    }
  };

  // 1) 사용자 지정 — 최상위
  for (const svc of input.suspectServices ?? []) {
    add(svc, { kind: 'user', raw: svc }, 1);
  }

  // 2) Java/Kotlin 프레임
  for (const m of input.signal.matchAll(JAVA_FRAME)) {
    const cls = m[1]!;
    add(toServiceName(cls), { kind: 'frame', raw: m[0]!.trim() }, 0.6);
  }

  // 3) 파일 경로 프레임
  for (const m of input.signal.matchAll(PATH_FRAME)) {
    const file = m[1]!;
    add(toServiceName(file), { kind: 'path', raw: m[0]! }, 0.45);
  }

  return [...byName.values()].sort((a, b) => b.confidence - a.confidence);
}
```

- [ ] **Step 4: 실행 → 통과 확인**

Run: `pnpm vitest run tests/error-localizer.test.ts`
Expected: PASS (4건)

> 참고: `PATH_FRAME`이 `OrderService.java`도 잡아 중복될 수 있으나 `add`가 동일 entityName을 병합하므로 안전(오히려 confidence 보강). TS 경로 케이스 검증은 Task 5에서 추가.

- [ ] **Step 5: Commit**

```bash
git add src/khala/error-localizer.ts tests/error-localizer.test.ts
git commit -m "feat: add error-localizer (stacktrace/error -> Suspect[])"
```

---

### Task 5: TS/JS 경로 국소화 + kind 휴리스틱

**Files:**
- Modify: `src/khala/error-localizer.ts`
- Test: `tests/error-localizer.test.ts`

- [ ] **Step 1: 실패 테스트 추가**

> 파일 상단 import를 `import { localizeError, inferKind } from '../src/khala/error-localizer.js';`로
> 갱신한다 (ESM — `require` 금지).

```typescript
describe('localizeError — TS/JS 경로 + kind 휴리스틱', () => {
  it('TS 파일 경로에서 service를 추출한다', () => {
    const signal = 'TypeError: undefined\n    at checkout (src/order/order-service.ts:88:10)';
    const suspects = localizeError({ signal });
    expect(suspects.some((s) => s.entityName === 'order-service')).toBe(true);
  });

  it('kind 미지정 시 프레임 존재로 stacktrace를 추론한다 (inferKind)', () => {
    expect(inferKind('\tat com.x.Y.z(Y.java:1)')).toBe('stacktrace');
    expect(inferKind('결제가 안 됩니다')).toBe('incident');
  });
});
```

- [ ] **Step 2: 실행 → 실패 확인**

Run: `pnpm vitest run tests/error-localizer.test.ts -t "kind 휴리스틱"`
Expected: FAIL (`inferKind` 없음)

- [ ] **Step 3: 구현 — `inferKind` export 추가**

`src/khala/error-localizer.ts`에 추가:

```typescript
/**
 * kind 힌트가 없을 때 신호 본문으로 종류를 추론한다.
 */
export function inferKind(signal: string): NonNullable<TroubleshootInput['kind']> {
  if (/\bat\s+[\w$.]+\(|\n\s+at\s/.test(signal)) return 'stacktrace';
  if (/\b(FAIL|AssertionError|expected .* to|✗|✕)\b/.test(signal)) return 'test-failure';
  if (/\b(Error|Exception|errno|stack)\b/i.test(signal)) return 'error';
  return 'incident';
}
```

- [ ] **Step 4: 실행 → 통과 확인**

Run: `pnpm vitest run tests/error-localizer.test.ts`
Expected: PASS (전체)

- [ ] **Step 5: Commit**

```bash
git add src/khala/error-localizer.ts tests/error-localizer.test.ts
git commit -m "feat: add TS/JS path localization and inferKind heuristic"
```

---

### Chunk 2 검토

- [ ] plan-document-reviewer로 Chunk 2 검토 → 수정 → 재검토 (통과 시 Chunk 3)

---

## Chunk 3: ★ 시그니처 시나리오 마일스톤 (해자 실증 게이트)

> **이 Chunk가 가설 검증 게이트다.** 목표: "제네릭 리뷰가 *구조적으로* 못 내는 발견 (설계에 없는 `order→inventory` observed_only 갭)을 Probe 데이터패스가 실제로 낸다"를 실증. 실패 시 Chunk 4 진행 금지, 사람에게 보고(스펙 §8.2).

### Task 6: 시드 스크립트 (S1 재현용, 검증 전용)

**Files:**
- Create: `scripts/seed-signature-scenario.sql`
- Create: `scripts/seed-signature-scenario.md` (런북)
- Create: `tests/fixtures/order-service-design.md` (설계 문서 픽스처)

- [ ] **Step 1: 설계 문서 픽스처 작성**

`tests/fixtures/order-service-design.md`:

```markdown
# Order Service 설계

order-service는 결제 완료 후 order 상태만 갱신한다.
**inventory-service를 직접 호출하지 않는다** — 재고 차감은 이벤트로 비동기 처리한다.
```

- [ ] **Step 2: 시드 SQL 작성**

`scripts/seed-signature-scenario.sql` (Khala Postgres 대상; 설계엔 order→inventory 동기 호출이 *없고*, 관측엔 *있는* 상태를 만든다 → `/diff`가 `observed_only` 산출):

```sql
-- 시그니처 시나리오 S1 시드 (검증 전용 — 프로덕션 금지)
-- 전제: order-service, inventory-service 엔티티가 이미 존재해야 함 (gazetteer/ingest 선행).
-- observed_edges 스키마(init.sql 189~213): from_name/to_name 컬럼은 없고
--   from_rid/to_rid TEXT NOT NULL REFERENCES entities(rid) 사용. rid는 콘텐츠 해시라
--   직접 만들 수 없으므로 name으로 조회한다.
-- 설계 엣지(edges)는 일부러 만들지 않는다 → /diff가 observed_only를 산출한다.

DO $$
DECLARE v_from TEXT; v_to TEXT;
BEGIN
  SELECT rid INTO v_from FROM entities
    WHERE name = 'order-service' AND tenant = 'default' AND status = 'active';
  SELECT rid INTO v_to FROM entities
    WHERE name = 'inventory-service' AND tenant = 'default' AND status = 'active';
  IF v_from IS NULL OR v_to IS NULL THEN
    RAISE EXCEPTION 'order-service/inventory-service 엔티티가 없습니다 — 먼저 khala ingest로 생성하세요 (Entities missing)';
  END IF;

  INSERT INTO observed_edges
    (rid, rtype, tenant, edge_type, from_rid, to_rid,
     call_count, error_rate, latency_p95, sample_trace_ids, trace_query_ref,
     status, created_at, updated_at)
  VALUES
    ('observed_edge_sig_s1', 'observed_edge', 'default', 'CALLS_OBSERVED', v_from, v_to,
     1500, 0.20, 850, ARRAY['trace-abc123'], 'tempo:order->inventory',
     'active', NOW(), NOW())
  ON CONFLICT (rid) DO UPDATE
    SET error_rate = EXCLUDED.error_rate, call_count = EXCLUDED.call_count;
END $$;
```

> 컬럼은 `khala/init.sql` `observed_edges` DDL(189~213)과 대조 완료: `from_rid`/`to_rid`(entities FK)
> 사용, `from_name`/`to_name` 없음. `ON CONFLICT (rid)`는 rid가 PRIMARY KEY라 유효.
> entities가 없으면 runbook step 2(ingest)가 graph 추출로 생성하거나 gazetteer 부트스트랩에
> 의존. 둘 다 실패 시 `entities.yaml`에 order-service/inventory-service를 추가 후 재-ingest.

- [ ] **Step 3: 런북 작성**

`scripts/seed-signature-scenario.md`:

```markdown
# 시그니처 시나리오 S1 — 라이브 실증 런북

목적: Probe 트러블슈팅 그라운딩이 제네릭 리뷰가 못 보는 observed_only 갭을 실제로
드러냄을 증명.

## 절차
1. Khala 기동: `cd ../../khala && docker-compose up -d`
2. 설계 문서 인덱싱:
   `khala ingest ../probe/tests/fixtures/order-service-design.md --force`
3. 관측 엣지 시드:
   `docker exec -i khala-postgres psql -U khala -d khala < scripts/seed-signature-scenario.sql`
4. 가용성 확인: `npx probe khala:status` → observed_edges_count ≥ 1
5. 실증:
   `npx probe troubleshoot "NPE at com.shop.order.OrderService.checkout(OrderService.java:88)"`
   기대 출력: designObservationGaps에 `observed_only: order-service → inventory-service`
   (error_rate 0.20) 가 포함.
6. 대조: 동일 입력을 일반 코드 리뷰 스킬에 주면 trace가 없어 이 갭을 낼 수 없음 → 해자 실증.
```

- [ ] **Step 4: Commit**

```bash
git add scripts/seed-signature-scenario.sql scripts/seed-signature-scenario.md tests/fixtures/order-service-design.md
git commit -m "test: add signature-scenario S1 seed + runbook (moat reproduction)"
```

---

### Task 7: S1 데이터패스 자동 테스트 (목킹 — CI 게이트)

**Files:**
- Test: `tests/signature-scenario.test.ts`

> 라이브 실증(Task 6 런북)은 사람이 1회 수행. 여기서는 **CI에서 항상 도는 결정론적 게이트**로, 목킹된 Khala가 observed_only를 줄 때 `localizeError → getDiff(entityFilter)` 경로가 그 갭을 끌어오는지 검증한다. (full grounder 불필요 — 스펙 §8.3.)

- [ ] **Step 1: 실패 테스트 작성**

```typescript
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { localizeError } from '../src/khala/error-localizer.js';
import { KhalaClient } from '../src/khala/client.js';

describe('시그니처 시나리오 S1 — observed_only 갭 데이터패스', () => {
  let originalFetch: typeof globalThis.fetch;
  beforeEach(() => { originalFetch = globalThis.fetch; });
  afterEach(() => { globalThis.fetch = originalFetch; });

  it('에러→국소화→getDiff(entityFilter)로 order→inventory observed_only 갭을 끌어온다', async () => {
    // 1) 국소화
    const suspects = localizeError({
      signal: 'NPE\n\tat com.shop.order.OrderService.checkout(OrderService.java:88)',
      kind: 'stacktrace',
    });
    expect(suspects[0]!.entityName).toBe('order-service');

    // 2) Khala /diff 목킹 (observed_only 갭)
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true, status: 200,
      json: () => Promise.resolve({
        success: true,
        data: {
          total_designed_edges: 0, total_observed_edges: 1, generated_at: 'now',
          diffs: [{
            flag: 'observed_only', edge_rid: null, observed_edge_rid: 'o1',
            from_name: 'order-service', to_name: 'inventory-service',
            edge_type: 'CALLS_OBSERVED', detail: '설계에 없는 호출',
            designed_evidence: [],
            observed_evidence: { sample_trace_ids: ['trace-abc123'], trace_query_ref: 'tempo:...' },
          }],
        },
        error: null, meta: {},
      }),
    });

    const client = new KhalaClient({ baseUrl: 'http://test:8000' });
    const diff = await client.getDiff({ entityFilter: suspects[0]!.entityName });

    // 3) 갭이 끌려왔는가 — 제네릭 리뷰가 구조적으로 못 내는 발견
    const gap = diff?.diffs.find((d) => d.flag === 'observed_only');
    expect(gap).toBeDefined();
    expect(gap!.from_name).toBe('order-service');
    expect(gap!.to_name).toBe('inventory-service');
  });
});
```

- [ ] **Step 2: 실행 → 통과 확인 (Chunk 1·2 산출물로 이미 통과해야 함)**

Run: `pnpm vitest run tests/signature-scenario.test.ts`
Expected: PASS

> 만약 PASS하지 않으면 데이터패스(client/localizer)에 결함이 있는 것이므로 Chunk 1·2로 돌아간다.

- [ ] **Step 3: Commit**

```bash
git add tests/signature-scenario.test.ts
git commit -m "test: add S1 moat datapath gate (localize -> getDiff -> observed_only)"
```

---

### ★ Chunk 3 게이트 결정

- [ ] Task 7 자동 테스트 PASS + (가능 시) Task 6 런북으로 라이브 S1 출력 1회 확보
- [ ] **게이트 판정:** observed_only 갭이 실증되면 → Chunk 4 진행. 실증 불가(예: Khala 데이터 구조가 스펙과 다름, /diff가 기대대로 동작 안 함)면 → **중단하고 사람에게 보고** (스펙 §8.2: 해자 미실증 시 범위 축소/중단 재검토)
- [ ] plan-document-reviewer로 Chunk 3 검토 → 수정 → 재검토

---

## Chunk 4: troubleshoot-grounder (GroundingPack 조립)

### Task 8: 그라운더 — 지식·토폴로지·갭·운영신호 조립

**Files:**
- Create: `src/khala/troubleshoot-grounder.ts`
- Test: `tests/troubleshoot-grounder.test.ts`

- [ ] **Step 1: 실패 테스트 작성**

```typescript
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { groundTroubleshooting } from '../src/khala/troubleshoot-grounder.js';
import { KhalaClient } from '../src/khala/client.js';

function mockFetchByPath(handlers: Record<string, unknown>) {
  return vi.fn((url: string) => {
    const path = new URL(url).pathname;
    const key = Object.keys(handlers).find((k) => path.startsWith(k));
    const data = key ? handlers[key] : {};
    return Promise.resolve({
      ok: true, status: 200,
      json: () => Promise.resolve({ success: true, data, error: null, meta: {} }),
    });
  });
}

describe('groundTroubleshooting', () => {
  let originalFetch: typeof globalThis.fetch;
  beforeEach(() => { originalFetch = globalThis.fetch; });
  afterEach(() => { globalThis.fetch = originalFetch; });

  it('갭과 운영신호를 GroundingPack에 담는다 (T3)', async () => {
    globalThis.fetch = mockFetchByPath({
      '/diff': {
        diffs: [{
          flag: 'observed_only', from_name: 'order-service', to_name: 'inventory-service',
          edge_type: 'CALLS_OBSERVED', detail: '설계에 없음',
          designed_evidence: [], observed_evidence: { sample_trace_ids: ['t1'], trace_query_ref: 'ref' },
        }],
      },
      '/graph': {
        center_entity: { rid: 'ent_order', name: 'order-service' },
        edges: [],
        observed_edges: [{
          rid: 'o1', edge_type: 'CALLS_OBSERVED', from_name: 'order-service',
          to_name: 'inventory-service', call_count: 1500, error_rate: 0.2, latency_p95: 850,
          sample_trace_ids: ['t1'], trace_query_ref: 'ref',
        }],
      },
      '/search': { results: [] },
    }) as unknown as typeof globalThis.fetch;

    const client = new KhalaClient({ baseUrl: 'http://test:8000' });
    const pack = await groundTroubleshooting(
      client,
      [{ entityName: 'order-service', evidence: [], confidence: 0.9 }],
      { signal: 'NPE', tier: 3 },
    );

    expect(pack.designObservationGaps?.some((g) => g.flag === 'observed_only')).toBe(true);
    expect(pack.operationalSignals?.some((s) => s.errorRate >= 0.05)).toBe(true);
  });

  it('개별 섹션 실패가 전체를 막지 않는다', async () => {
    globalThis.fetch = vi.fn((url: string) =>
      String(url).includes('/diff')
        ? Promise.reject(new Error('500'))
        : Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({ success: true, data: { results: [] }, error: null, meta: {} }) }),
    ) as unknown as typeof globalThis.fetch;

    const client = new KhalaClient({ baseUrl: 'http://test:8000' });
    const pack = await groundTroubleshooting(
      client, [{ entityName: 'order-service', evidence: [], confidence: 0.9 }],
      { signal: 'NPE', tier: 3 },
    );
    expect(pack.caveats.some((c) => c.includes('diff'))).toBe(true);
  });
});
```

- [ ] **Step 2: 실행 → 실패 확인**

Run: `pnpm vitest run tests/troubleshoot-grounder.test.ts`
Expected: FAIL (모듈 없음)

- [ ] **Step 3: 구현**

`src/khala/troubleshoot-grounder.ts`:

```typescript
/**
 * 트러블슈팅 Grounding Pack 조립
 *
 * Suspect[]와 KhalaClient로 §2~§6 섹션을 병렬 조립한다.
 * 각 섹션은 독립 실패해도 나머지를 막지 않는다 (withKhalaFallback).
 * §5 지식 그라운딩은 client.search()를 직접 호출한다 (context-enricher 재사용 안 함 — 스펙 §5.1).
 *
 * 규정 문서: docs/superpowers/specs/2026-06-06-troubleshooting-grounding-design.md §2~§6
 */

import { KhalaClient, withKhalaFallback } from './client.js';
import { analyzeImpact } from './impact-analyzer.js';
import type {
  Suspect, GroundingPack, DesignGap, OperationalSignal, RelevantDoc, ImpactAnalysis,
} from './types.js';

/** 운영 신호 이상치 임계 (impact-analyzer와 동일치 재사용 — 스펙 Q3) */
const ERROR_RATE_THRESHOLD = 0.05;

export interface GroundOptions {
  signal: string;
  tier: 0 | 1 | 2 | 3;
  searchTopK?: number;
  graphHops?: number;
  /** §6 최근 변경 상관용 (Task 9에서 로직 추가; 인터페이스는 여기서 미리 선언해 순서 위험 제거) */
  changedServices?: { service: string; changedFiles: string[] }[];
}

/**
 * Grounding Pack을 조립한다 (티어가 허용하는 섹션까지).
 */
export async function groundTroubleshooting(
  client: KhalaClient,
  suspects: Suspect[],
  options: GroundOptions,
): Promise<GroundingPack> {
  const caveats: string[] = [];
  const pack: GroundingPack = {
    tier: options.tier,
    tierReason: '',  // core/troubleshoot에서 채움
    suspects,
    caveats,
  };

  const names = suspects.filter((s) => s.confidence >= 0.3).map((s) => s.entityName);

  // §5 지식 (T1+)
  if (options.tier >= 1) {
    const knowledge = await withKhalaFallback(
      () => fetchKnowledge(client, options.signal, options.searchTopK ?? 5),
      null, 'search',
    );
    if (knowledge) pack.knowledge = knowledge;
    else caveats.push('지식 그라운딩(search) 조회 실패 (Knowledge grounding unavailable)');
  }

  // §2 토폴로지 + §6은 core에서 diff 입력 받아 별도; 여기선 토폴로지/영향 (T2+)
  if (options.tier >= 2 && names.length > 0) {
    const topology = await withKhalaFallback<ImpactAnalysis | null>(
      () => analyzeImpact(client, names, { hops: options.graphHops ?? 2 }),
      null, 'impact',
    );
    if (topology) pack.topology = topology;
  }

  // §3 설계-관측 갭 (doc_only는 T2+, observed_only/conflict는 T3)
  if (options.tier >= 2 && names.length > 0) {
    const gaps = await withKhalaFallback(
      () => fetchGaps(client, names),
      null, 'diff',
    );
    if (gaps) {
      pack.designObservationGaps = options.tier >= 3
        ? gaps
        : gaps.filter((g) => g.flag === 'doc_only');
      // §4 운영 신호 (T3) — 갭의 관측치 + 토폴로지 관측치에서 이상 추출
      if (options.tier >= 3) {
        pack.operationalSignals = extractSignals(pack.topology);
      }
    } else {
      caveats.push('설계-관측 갭(diff) 조회 실패 (Design-observation gap unavailable)');
    }
  }

  return pack;
}

/** §5: 의심 지점 + 신호로 관련 문서 검색 */
async function fetchKnowledge(
  client: KhalaClient, signal: string, topK: number,
): Promise<RelevantDoc[]> {
  // 검색 쿼리는 앞 500자만 사용 (저장 신호의 8000자 절단과는 별개 — 쿼리 품질·길이 제한용)
  const result = await client.search(signal.slice(0, 500), { topK });
  if (!result) return [];
  return result.results.map((h) => ({
    docTitle: h.doc_title, sectionPath: h.section_path,
    snippet: h.snippet, score: h.score, classification: h.classification,
  }));
}

/** §3: 각 의심 service의 diff를 합쳐 DesignGap[]으로 변환 */
async function fetchGaps(client: KhalaClient, names: string[]): Promise<DesignGap[]> {
  const results = await Promise.all(
    names.map((n) => withKhalaFallback(() => client.getDiff({ entityFilter: n }), null, `diff:${n}`)),
  );
  const gaps: DesignGap[] = [];
  for (const r of results) {
    if (!r) continue;
    for (const d of r.diffs) {
      gaps.push({
        flag: d.flag, fromName: d.from_name, toName: d.to_name,
        edgeType: d.edge_type, detail: d.detail,
        // 기존 context-enricher.ts 패턴과 일관: 모든 설계 근거를 join
        designedEvidence: d.designed_evidence.length > 0
          ? d.designed_evidence.map((e) => e.text).join('; ')
          : undefined,
        observedEvidence: d.observed_evidence?.sample_trace_ids,
      });
    }
  }
  return gaps;
}

/** §4: 토폴로지 관측치에서 이상 신호 추출 */
function extractSignals(topology?: ImpactAnalysis): OperationalSignal[] {
  if (!topology) return [];
  const signals: OperationalSignal[] = [];
  for (const svc of [...topology.directImpact, ...topology.indirectImpact]) {
    if (svc.observed && svc.observed.errorRate >= ERROR_RATE_THRESHOLD) {
      signals.push({
        fromName: topology.changedServices[0] ?? '?',
        toName: svc.name,
        callCount: svc.observed.callCount,
        errorRate: svc.observed.errorRate,
        latencyP95: svc.observed.latencyP95,
        anomaly: `error_rate ${svc.observed.errorRate.toFixed(2)} > 임계 ${ERROR_RATE_THRESHOLD}`,
      });
    }
  }
  return signals;
}
```

- [ ] **Step 4: 실행 → 통과 확인**

Run: `pnpm vitest run tests/troubleshoot-grounder.test.ts`
Expected: PASS (2건)

- [ ] **Step 5: Commit**

```bash
git add src/khala/troubleshoot-grounder.ts tests/troubleshoot-grounder.test.ts
git commit -m "feat: add troubleshoot-grounder (assemble GroundingPack sections)"
```

---

### Task 9: 최근 변경 상관(§6) 통합

**Files:**
- Modify: `src/khala/troubleshoot-grounder.ts`
- Test: `tests/troubleshoot-grounder.test.ts`

- [ ] **Step 1: 실패 테스트 추가**

```typescript
it('changedServices가 주어지면 의심 토폴로지와 상관시킨다', async () => {
  globalThis.fetch = mockFetchByPath({ '/search': { results: [] }, '/diff': { diffs: [] },
    '/graph': { center_entity: { rid: 'e', name: 'order-service' }, edges: [], observed_edges: [] } }) as unknown as typeof globalThis.fetch;
  const client = new KhalaClient({ baseUrl: 'http://test:8000' });
  const pack = await groundTroubleshooting(
    client, [{ entityName: 'order-service', evidence: [], confidence: 0.9 }],
    { signal: 'NPE', tier: 2, changedServices: [{ service: 'order-service', changedFiles: ['OrderService.java'] }] },
  );
  expect(pack.changeCorrelation?.[0]!.service).toBe('order-service');
});
```

- [ ] **Step 2: 실행 → 실패 확인**

Run: `pnpm vitest run tests/troubleshoot-grounder.test.ts -t "changedServices가 주어지면"`
Expected: FAIL (changedServices 옵션 미지원)

- [ ] **Step 3: 구현 — 상관 로직 추가**

> `GroundOptions.changedServices` 필드는 Task 8에서 이미 선언됨 (순서 위험 제거). 여기선 로직만 추가.
함수 본문 끝(`return pack` 직전)에 추가:

```typescript
  // §6 최근 변경 상관: 변경 service ∩ 의심 service (스펙 §3.4: T2 — 설계 그래프 필요)
  if (options.tier >= 2 && options.changedServices?.length) {
    const suspectSet = new Set(names);
    pack.changeCorrelation = options.changedServices
      .filter((c) => suspectSet.has(c.service))
      .map((c) => ({ service: c.service, changedFiles: c.changedFiles, relationship: 'changed∩suspect' }));
  }
```

- [ ] **Step 4: 실행 → 통과 확인**

Run: `pnpm vitest run tests/troubleshoot-grounder.test.ts`
Expected: PASS (전체)

- [ ] **Step 5: Commit**

```bash
git add src/khala/troubleshoot-grounder.ts tests/troubleshoot-grounder.test.ts
git commit -m "feat: correlate recent changes with suspect topology (grounding section 6)"
```

---

### Chunk 4 검토

- [ ] plan-document-reviewer로 Chunk 4 검토 → 수정 → 재검토

---

## Chunk 5: core/troubleshoot (티어 결정 + 입력검증 + 오케스트레이션)

### Task 10: 티어 결정 + 입력 검증

**Files:**
- Create: `src/core/troubleshoot.ts`
- Test: `tests/core-troubleshoot.test.ts`

- [ ] **Step 1: 실패 테스트 작성**

```typescript
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { determineTier, validateInput } from '../src/core/troubleshoot.js';
import type { KhalaStatusResult } from '../src/khala/types.js';

describe('determineTier', () => {
  it('Khala 미가용이면 T0', () => {
    expect(determineTier(null).tier).toBe(0);
  });
  it('문서만 있으면 T1', () => {
    const s: KhalaStatusResult = { db_connected: true, documents_count: 5, edges_count: 0 };
    expect(determineTier(s).tier).toBe(1);
  });
  it('설계 엣지가 있으면 T2', () => {
    const s: KhalaStatusResult = { db_connected: true, documents_count: 5, edges_count: 3, observed_edges_count: 0 };
    expect(determineTier(s).tier).toBe(2);
  });
  it('관측 엣지가 있으면 T3', () => {
    const s: KhalaStatusResult = { db_connected: true, edges_count: 3, observed_edges_count: 2 };
    expect(determineTier(s).tier).toBe(3);
  });
});

describe('validateInput', () => {
  it('빈 신호를 거부한다', () => {
    expect(validateInput({ signal: '   ' }).ok).toBe(false);
  });
  it('과대 입력을 절단하고 caveat를 남긴다', () => {
    const r = validateInput({ signal: 'x'.repeat(50_000) });
    expect(r.ok).toBe(true);
    expect(r.signal!.length).toBeLessThan(50_000);
    expect(r.caveats.length).toBeGreaterThan(0);
  });
});
```

- [ ] **Step 2: 실행 → 실패 확인**

Run: `pnpm vitest run tests/core-troubleshoot.test.ts`
Expected: FAIL (모듈 없음)

- [ ] **Step 3: 구현**

`src/core/troubleshoot.ts`:

```typescript
/**
 * 트러블슈팅 오케스트레이션 — 입력검증, 티어 결정, grounder 호출, caveat 수집
 *
 * 규정 문서: docs/superpowers/specs/2026-06-06-troubleshooting-grounding-design.md §5, §6
 */

import { KhalaClient } from '../khala/client.js';
import { localizeError, inferKind } from '../khala/error-localizer.js';
import { groundTroubleshooting } from '../khala/troubleshoot-grounder.js';
import type {
  TroubleshootInput, GroundingPack, KhalaStatusResult,
} from '../khala/types.js';

const MAX_SIGNAL_LEN = 8_000;

/** 입력 검증 결과 */
export interface ValidatedInput {
  ok: boolean;
  signal?: string;
  reason?: string;
  caveats: string[];
}

/**
 * 입력을 검증한다 (Khala 호출 전).
 */
export function validateInput(input: TroubleshootInput): ValidatedInput {
  const caveats: string[] = [];
  const signal = (input.signal ?? '').trim();
  if (!signal) {
    return { ok: false, reason: '입력 신호가 비어 있습니다 (Empty signal). 예: probe troubleshoot "<에러/스택트레이스>"', caveats };
  }
  let trimmed = signal;
  if (signal.length > MAX_SIGNAL_LEN) {
    trimmed = signal.slice(0, MAX_SIGNAL_LEN);
    caveats.push(`입력이 길어 앞 ${MAX_SIGNAL_LEN}자로 절단함 (Signal truncated)`);
  }
  return { ok: true, signal: trimmed, caveats };
}

/** 티어 결정 결과 */
export interface TierDecision {
  tier: 0 | 1 | 2 | 3;
  reason: string;
}

/**
 * /status 카운트로 그라운딩 티어를 결정한다 (스펙 §5.2).
 */
export function determineTier(status: KhalaStatusResult | null): TierDecision {
  if (!status || !status.db_connected) {
    return { tier: 0, reason: 'Khala 미가용 → T0 (국소화·프로파일만)' };
  }
  const obs = status.observed_edges_count ?? 0;
  const edges = status.edges_count ?? 0;
  const docs = status.documents_count ?? 0;
  if (obs > 0) return { tier: 3, reason: `관측 엣지 ${obs}개 → T3 (운영신호·설계-관측 갭 포함)` };
  if (edges > 0) return { tier: 2, reason: `설계 엣지 ${edges}개, 관측 0 → T2 (토폴로지·영향)` };
  if (docs > 0) return { tier: 1, reason: `문서 ${docs}개, 엣지 0 → T1 (RAG 지식만)` };
  return { tier: 0, reason: 'Khala 연결됐으나 인덱싱 데이터 없음 → T0' };
}

/**
 * 트러블슈팅 그라운딩 전체 실행.
 *
 * @param input 트러블슈팅 입력
 * @param client 칼라 클라이언트
 * @param changedServices 선택: 최근 변경 service (CLI/MCP에서 git diff로 추출해 전달)
 */
export async function runTroubleshoot(
  input: TroubleshootInput,
  client: KhalaClient,
  changedServices?: { service: string; changedFiles: string[] }[],
): Promise<{ ok: false; reason: string } | { ok: true; pack: GroundingPack }> {
  const v = validateInput(input);
  if (!v.ok) return { ok: false, reason: v.reason! };

  const kind = input.kind ?? inferKind(v.signal!);
  const suspects = localizeError({ ...input, signal: v.signal!, kind });

  const status = await client.getStatus();
  const tierDecision = determineTier(status);

  if (suspects.length === 0) {
    return {
      ok: true,
      pack: {
        tier: tierDecision.tier, tierReason: tierDecision.reason, suspects: [],
        caveats: [...v.caveats, '의심 지점을 국소화하지 못함 — 스택트레이스/파일경로/서비스명을 포함해 다시 시도'],
      },
    };
  }

  const pack = await groundTroubleshooting(client, suspects, {
    signal: v.signal!, tier: tierDecision.tier, changedServices,
  });
  pack.tierReason = tierDecision.reason;
  pack.caveats.unshift(...v.caveats);

  // 낮은 confidence suspect 경고 (침묵 누락 금지)
  const lowConf = suspects.filter((s) => s.confidence < 0.3);
  if (lowConf.length) {
    pack.caveats.push(`신뢰도 낮은 의심 지점 ${lowConf.length}개 — 참고만: ${lowConf.map((s) => s.entityName).join(', ')}`);
  }
  // Archon 미연동 안내
  if (!pack.domainInvariants) {
    pack.caveats.push('도메인 불변식 그라운딩은 Archon 미연동으로 생략됨');
  }

  return { ok: true, pack };
}
```

- [ ] **Step 4: 실행 → 통과 확인**

Run: `pnpm vitest run tests/core-troubleshoot.test.ts`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/core/troubleshoot.ts tests/core-troubleshoot.test.ts
git commit -m "feat: add core troubleshoot orchestration (tier + input validation)"
```

---

### Task 11: runTroubleshoot 통합 테스트 (강등·국소화실패 경로)

**Files:**
- Test: `tests/core-troubleshoot.test.ts`

- [ ] **Step 1: 실패 테스트 추가**

```typescript
import { runTroubleshoot } from '../src/core/troubleshoot.js';
import { KhalaClient } from '../src/khala/client.js';

describe('runTroubleshoot 경로', () => {
  let originalFetch: typeof globalThis.fetch;
  beforeEach(() => { originalFetch = globalThis.fetch; });
  afterEach(() => { globalThis.fetch = originalFetch; });

  it('빈 입력은 ok:false', async () => {
    const client = new KhalaClient({ baseUrl: 'http://test:8000' });
    const r = await runTroubleshoot({ signal: '' }, client);
    expect(r.ok).toBe(false);
  });

  it('Khala 미가용이면 T0 + 국소화만', async () => {
    globalThis.fetch = vi.fn().mockRejectedValue(new Error('down'));
    const client = new KhalaClient({ baseUrl: 'http://test:8000' });
    const r = await runTroubleshoot(
      { signal: 'at com.shop.order.OrderService.checkout(OrderService.java:88)' }, client,
    );
    expect(r.ok).toBe(true);
    if (r.ok) {
      expect(r.pack.tier).toBe(0);
      expect(r.pack.suspects[0]!.entityName).toBe('order-service');
    }
  });
});
```

- [ ] **Step 2: 실행 → 통과 확인** (구현 완료 상태이므로 PASS 기대)

Run: `pnpm vitest run tests/core-troubleshoot.test.ts`
Expected: PASS (전체)

- [ ] **Step 3: Commit**

```bash
git add tests/core-troubleshoot.test.ts
git commit -m "test: cover runTroubleshoot degradation and localization-miss paths"
```

---

### Chunk 5 검토

- [ ] plan-document-reviewer로 Chunk 5 검토 → 수정 → 재검토

---

## Chunk 6: CLI 표면

### Task 12: parse-args 확장 (--kind, --diff-base, --suspect, stdin)

**Files:**
- Modify: `src/cli/parse-args.ts`
- Test: `tests/cli-parse-args.test.ts`

- [ ] **Step 1: 실패 테스트 추가** (`tests/cli-parse-args.test.ts`에)

```typescript
import { parseTroubleshootArgs } from '../src/cli/parse-args.js';

describe('parseTroubleshootArgs', () => {
  it('인자 신호와 플래그를 파싱한다', () => {
    const o = parseTroubleshootArgs(['NPE at X', '--kind', 'stacktrace', '--suspect', 'order-service', '--format', 'json']);
    expect(o.signal).toBe('NPE at X');
    expect(o.kind).toBe('stacktrace');
    expect(o.suspectServices).toContain('order-service');
    expect(o.format).toBe('json');
  });
  it('--diff-base를 받는다', () => {
    const o = parseTroubleshootArgs(['err', '--diff-base', 'origin/main']);
    expect(o.diffBase).toBe('origin/main');
  });
});
```

- [ ] **Step 2: 실행 → 실패 확인**

Run: `pnpm vitest run tests/cli-parse-args.test.ts -t "parseTroubleshootArgs"`
Expected: FAIL (함수 없음)

- [ ] **Step 3: 구현** — `src/cli/parse-args.ts`에 추가 (기존 `parseArgs`는 유지)

```typescript
export interface TroubleshootCliOptions {
  signal: string;
  kind?: 'stacktrace' | 'error' | 'test-failure' | 'incident';
  diffBase?: string;
  suspectServices: string[];
  format: OutputFormat;
}

/**
 * troubleshoot 커맨드 인자를 파싱한다.
 * 비-플래그 토큰은 신호로 합친다 (인자 우선; stdin은 호출부에서 fallback).
 */
export function parseTroubleshootArgs(args: string[]): TroubleshootCliOptions {
  const o: TroubleshootCliOptions = { signal: '', kind: undefined, suspectServices: [], format: 'markdown' };
  const signalParts: string[] = [];
  for (let i = 0; i < args.length; i++) {
    const arg = args[i]!;
    if (arg === '--kind' && i + 1 < args.length) {
      const k = args[++i]!;
      if (k === 'stacktrace' || k === 'error' || k === 'test-failure' || k === 'incident') o.kind = k;
    } else if (arg === '--diff-base' && i + 1 < args.length) {
      o.diffBase = args[++i]!;
    } else if (arg === '--suspect' && i + 1 < args.length) {
      o.suspectServices.push(args[++i]!);
    } else if (arg === '--format' && i + 1 < args.length) {
      const f = args[++i]!;
      if (f === 'markdown' || f === 'json' || f === 'brief') o.format = f;
    } else if (!arg.startsWith('--')) {
      signalParts.push(arg);
    }
  }
  o.signal = signalParts.join(' ');
  return o;
}
```

- [ ] **Step 4: 실행 → 통과 확인**

Run: `pnpm vitest run tests/cli-parse-args.test.ts`
Expected: PASS (신규 + 기존 회귀)

- [ ] **Step 5: Commit**

```bash
git add src/cli/parse-args.ts tests/cli-parse-args.test.ts
git commit -m "feat: add parseTroubleshootArgs (kind/diff-base/suspect/format)"
```

---

### Task 13: GroundingPack 포맷터

**Files:**
- Modify: `src/cli/formatters.ts`
- Test: `tests/cli-formatters.test.ts`

- [ ] **Step 1: 실패 테스트 추가**

```typescript
import { formatGroundingPackMarkdown, formatGroundingPackBrief } from '../src/cli/formatters.js';
import type { GroundingPack } from '../src/khala/types.js';

describe('formatGroundingPack', () => {
  const pack: GroundingPack = {
    tier: 3, tierReason: '관측 엣지 1개 → T3',
    suspects: [{ entityName: 'order-service', evidence: [], confidence: 0.9 }],
    designObservationGaps: [{ flag: 'observed_only', fromName: 'order-service', toName: 'inventory-service', edgeType: 'CALLS_OBSERVED', detail: '설계에 없음' }],
    caveats: ['도메인 불변식 그라운딩은 Archon 미연동으로 생략됨'],
  };
  it('markdown에 티어·갭·caveat가 들어간다', () => {
    const md = formatGroundingPackMarkdown(pack);
    expect(md).toContain('T3');
    expect(md).toContain('observed_only');
    expect(md).toContain('inventory-service');
    expect(md).toContain('Archon 미연동');
  });
  it('brief는 한 줄 요약', () => {
    expect(formatGroundingPackBrief(pack)).toContain('order-service');
  });
});
```

- [ ] **Step 2: 실행 → 실패 확인**

Run: `pnpm vitest run tests/cli-formatters.test.ts -t "formatGroundingPack"`
Expected: FAIL

- [ ] **Step 3: 구현** — `src/cli/formatters.ts`에 추가 (기존 포맷터 스타일 따름)

```typescript
import type { GroundingPack } from '../khala/types.js';

/** GroundingPack → markdown (근본원인 단정 없이 증거만) */
export function formatGroundingPackMarkdown(pack: GroundingPack): string {
  const lines: string[] = [];
  lines.push(`## 🔬 트러블슈팅 그라운딩 (T${pack.tier})`);
  lines.push('');
  lines.push(`> ${pack.tierReason}`);
  lines.push('> ⚠️ 이건 근거 모음이지 근본원인 판정이 아닙니다 — 추론은 분석자/Claude가 합니다.');
  lines.push('');

  lines.push('### 의심 지점');
  for (const s of pack.suspects) {
    lines.push(`- \`${s.entityName}\` (confidence ${s.confidence.toFixed(2)})`);
  }
  lines.push('');

  if (pack.designObservationGaps?.length) {
    lines.push('### ⚠️ 설계-관측 갭 (제네릭 리뷰가 구조적으로 못 보는 발견)');
    for (const g of pack.designObservationGaps) {
      lines.push(`- **${g.flag}**: ${g.fromName} → ${g.toName} (${g.edgeType}) — ${g.detail}`);
      if (g.observedEvidence?.length) lines.push(`  - trace: ${g.observedEvidence.join(', ')}`);
    }
    lines.push('');
  }

  if (pack.operationalSignals?.length) {
    lines.push('### 운영 신호');
    for (const s of pack.operationalSignals) {
      lines.push(`- ${s.fromName} → ${s.toName}: ${s.anomaly} (${s.callCount}회, p95 ${s.latencyP95}ms)`);
    }
    lines.push('');
  }

  if (pack.topology) {
    lines.push(`### 토폴로지 영향: ${pack.topology.summary}`);
    lines.push('');
  }

  if (pack.knowledge?.length) {
    lines.push('### 관련 규정/문서');
    for (const d of pack.knowledge) lines.push(`- ${d.docTitle} > ${d.sectionPath} (score ${d.score.toFixed(2)})`);
    lines.push('');
  }

  if (pack.changeCorrelation?.length) {
    lines.push('### 최근 변경 상관');
    for (const c of pack.changeCorrelation) lines.push(`- ${c.service}: ${c.changedFiles.join(', ')}`);
    lines.push('');
  }

  if (pack.domainInvariants?.length) {
    lines.push('### 도메인 불변식 (Archon)');
    for (const c of pack.domainInvariants) {
      lines.push(`- \`${c.boundSymbol}\` → ${c.kind} \`${c.id}\` (${c.criticality}, status=${c.status}, drift=${c.codeDrift})`);
    }
    lines.push('');
  }

  if (pack.caveats.length) {
    lines.push('### 한계 (caveats)');
    for (const c of pack.caveats) lines.push(`- ${c}`);
  }

  return lines.join('\n');
}

/** GroundingPack → 한 줄 요약 */
export function formatGroundingPackBrief(pack: GroundingPack): string {
  const names = pack.suspects.map((s) => s.entityName).join(', ') || '(국소화 실패)';
  const gaps = pack.designObservationGaps?.length ?? 0;
  return `트러블슈팅 T${pack.tier}: 의심 [${names}], 설계-관측 갭 ${gaps}개`;
}
```

- [ ] **Step 4: 실행 → 통과 확인**

Run: `pnpm vitest run tests/cli-formatters.test.ts`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/cli/formatters.ts tests/cli-formatters.test.ts
git commit -m "feat: add GroundingPack markdown/brief formatters"
```

---

### Task 14: troubleshoot 커맨드 배선

**Files:**
- Modify: `src/cli/index.ts`

> 이 Task는 입출력 배선이라 단위 테스트 대신 수동 스모크 + 기존 회귀로 검증한다 (기존 CLI 커맨드들도 단위 테스트 없이 동일 패턴).

- [ ] **Step 1: import 추가** (`src/cli/index.ts` 상단)

```typescript
import { runTroubleshoot } from '../core/troubleshoot.js';
import { parseTroubleshootArgs } from './parse-args.js';
import { formatGroundingPackMarkdown, formatGroundingPackBrief } from './formatters.js';
import { readFileSync } from 'node:fs';
```

- [ ] **Step 2: 커맨드 함수 추가** (`runKhalaStatus` 아래)

```typescript
/**
 * troubleshoot 커맨드 — 에러/스택트레이스 → Grounding Pack
 */
async function runTroubleshootCmd(args: string[]): Promise<void> {
  const o = parseTroubleshootArgs(args);

  // 인자 우선, 없으면 stdin (파이프) fallback (스펙 Q4)
  let signal = o.signal;
  if (!signal && !process.stdin.isTTY) {
    signal = readFileSync(0, 'utf-8').trim();
  }
  if (!signal) {
    logger.error('에러 신호를 입력하세요 (Usage: probe troubleshoot "<에러/스택트레이스>" [--kind] [--suspect] [--diff-base])');
    process.exitCode = 1;
    return;
  }

  const config = await loadConfigAsync();
  const khalaConfig = resolveKhalaConfig(config);
  const client = new KhalaClient(khalaConfig);

  // 선택: --diff-base 제공 시 최근 변경 service 추출
  let changedServices: { service: string; changedFiles: string[] }[] | undefined;
  if (o.diffBase) {
    const { profile } = await resolveProfileForCli(config);
    if (profile) {
      const changedFiles = getChangedFiles(o.diffBase);
      const scope = analyzeScope(changedFiles, profile, getDiffLines(o.diffBase));
      const { extractServiceNames } = await import('../khala/context-enricher.js');
      changedServices = extractServiceNames(scope.groups).map((service) => ({
        service,
        changedFiles: changedFiles.filter((f) => f.toLowerCase().includes(service.replace(/-/g, ''))),
      }));
    }
  }

  const result = await runTroubleshoot(
    { signal, kind: o.kind, diffBase: o.diffBase, suspectServices: o.suspectServices },
    client,
    changedServices,
  );

  if (!result.ok) {
    logger.error(result.reason);
    process.exitCode = 1;
    return;
  }

  switch (o.format) {
    case 'json':
      logger.info(JSON.stringify(result.pack, null, 2));
      break;
    case 'brief':
      logger.info(formatGroundingPackBrief(result.pack));
      break;
    case 'markdown':
    default:
      logger.info(formatGroundingPackMarkdown(result.pack));
      break;
  }
}
```

- [ ] **Step 3: switch에 case 추가** (`case 'khala:status':` 아래)

```typescript
  case 'troubleshoot':
    void runTroubleshootCmd(args.slice(1));
    break;
```

그리고 기본 usage 텍스트에 한 줄 추가:
```
  probe troubleshoot    에러/스택트레이스 → 트러블슈팅 그라운딩
```

- [ ] **Step 4: 빌드 + 스모크 테스트**

Run:
```bash
pnpm build
echo "java.lang.NullPointerException at com.shop.order.OrderService.checkout(OrderService.java:88)" | node dist/cli/index.js troubleshoot
```
Expected: T0(또는 가용 티어) GroundingPack markdown 출력, `order-service` 의심 지점 포함. (Khala 없으면 T0 + caveat)

- [ ] **Step 5: 전체 회귀 + 타입체크**

Run: `pnpm test:run && pnpm typecheck`
Expected: 전부 PASS

- [ ] **Step 6: Commit**

```bash
git add src/cli/index.ts
git commit -m "feat: wire 'probe troubleshoot' CLI command"
```

---

### Chunk 6 검토

- [ ] plan-document-reviewer로 Chunk 6 검토 → 수정 → 재검토

---

## Chunk 7: MCP 도구

### Task 15: probe.groundTroubleshooting 도구

**Files:**
- Modify: `src/mcp/tools.ts`
- Test: `tests/mcp-tools.test.ts` (기존 패턴 따름)

- [ ] **Step 1: 실패 테스트 작성**

> 주의(리뷰 반영): 기존 `tests/mcp-tools.test.ts`는 코어 함수를 직접 테스트할 뿐 `registerTools`를
> 호출하거나 도구 이름을 수집하는 헬퍼가 **없다.** 따라서 가짜 `McpServer`로 `.tool(name, …)`
> 호출을 캡처하는 방식을 사용한다. 별도 파일 `tests/mcp-troubleshoot-tool.test.ts`로 둔다.

`tests/mcp-troubleshoot-tool.test.ts`:

```typescript
import { describe, it, expect } from 'vitest';
import type { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js';
import { registerTools } from '../src/mcp/tools.js';

describe('probe.groundTroubleshooting 등록', () => {
  it('registerTools가 groundTroubleshooting 도구를 등록한다', () => {
    const names: string[] = [];
    // server.tool(name, desc, schema, handler) 호출만 캡처하는 가짜 서버
    const fake = { tool: (name: string) => { names.push(name); } };
    registerTools(fake as unknown as McpServer);
    expect(names).toContain('probe.groundTroubleshooting');
  });
});
```

- [ ] **Step 2: 실행 → 실패 확인**

Run: `pnpm vitest run tests/mcp-troubleshoot-tool.test.ts`
Expected: FAIL (도구 미등록)

- [ ] **Step 3: 구현** — `src/mcp/tools.ts`의 `registerTools` 내부에 도구 추가, import에 `runTroubleshoot`, `KhalaClient`(이미 있음), `resolveKhalaConfig`(이미 있음) 확인

```typescript
  // ─── probe.groundTroubleshooting (v0.5) ───
  server.tool(
    'probe.groundTroubleshooting',
    '에러/스택트레이스/실패 테스트를 받아 조직 컨텍스트(토폴로지·관측·설계-관측 갭·규정)를 묶은 Grounding Pack을 반환한다. 근본원인은 단정하지 않는다 — 추론은 호출자가 한다.',
    {
      signal: z.string().describe('에러 메시지 | 스택트레이스 | 실패 테스트 출력 | 인시던트 설명'),
      kind: z.enum(['stacktrace', 'error', 'test-failure', 'incident']).optional().describe('신호 종류 힌트 (생략 시 자동 추론)'),
      suspectServices: z.array(z.string()).optional().describe('사용자가 지목한 의심 서비스'),
      diffBase: z.string().optional().describe('최근 변경 상관 분석용 git base (예: origin/main)'),
    },
    async ({ signal, kind, suspectServices, diffBase }) => {
      const config = await loadConfigAsync();
      const khalaConfig = resolveKhalaConfig(config);
      const client = new KhalaClient(khalaConfig);
      const result = await runTroubleshoot({ signal, kind, suspectServices, diffBase }, client);
      const payload = result.ok ? result.pack : { error: result.reason };
      return { content: [{ type: 'text' as const, text: JSON.stringify(payload, null, 2) }] };
    },
  );
```

import 추가 (파일 상단):
```typescript
import { runTroubleshoot } from '../core/troubleshoot.js';
```

- [ ] **Step 3b: 같은 파일의 기존 `queryKhala` 가짜 rid 버그도 수정 (Task 3b와 동일 결함)**

`src/mcp/tools.ts:251`의 `client.getGraph(\`ent_${entityName}\`, …)` 같은 패턴이 있으면
`client.getGraph(entityName, …)`로 바꾼다 (`/graph`가 이름 조회 지원 — api.py 392~405).
가짜 `ent_` 접두사는 404를 유발한다. (Task 3b와 동일 근거.) 해당 패턴이 없으면 생략.

- [ ] **Step 4: 실행 → 통과 확인**

Run: `pnpm vitest run tests/mcp-troubleshoot-tool.test.ts`
Expected: PASS

- [ ] **Step 5: 전체 회귀 + 타입체크 + 빌드**

Run: `pnpm test:run && pnpm typecheck && pnpm build`
Expected: 전부 PASS

- [ ] **Step 6: Commit**

```bash
git add src/mcp/tools.ts tests/mcp-troubleshoot-tool.test.ts
git commit -m "feat: add probe.groundTroubleshooting MCP tool"
```

---

### Task 16: 문서 반영

**Files:**
- Modify: `probe/README.md`, `probe/CLAUDE.md`

- [ ] **Step 1: README/CLAUDE 갱신**

- README: 핵심 명령어에 `npx probe troubleshoot "<에러>"` 추가, MCP 도구 표에 7번째 행 추가, 로드맵 v0.5 상태 `Done`로.
- CLAUDE.md: "현재 버전: v0.5" + 구조 트리에 `error-localizer.ts`, `troubleshoot-grounder.ts`, `core/troubleshoot.ts` 추가, MCP "7개 도구"로.

- [ ] **Step 2: Commit**

```bash
git add probe/README.md probe/CLAUDE.md
git commit -m "docs: document v0.5 troubleshooting grounding (CLI + MCP)"
```

---

### Chunk 7 검토

- [ ] plan-document-reviewer로 Chunk 7 검토 → 수정 → 재검토

---

## 완료 기준 (Definition of Done)

- [ ] `pnpm test:run` 전체 PASS (신규 테스트 포함)
- [ ] `pnpm typecheck` 에러 없음 (`any` 미사용)
- [ ] `pnpm build` 성공
- [ ] **Chunk 3 게이트 통과** — S1 observed_only 갭 데이터패스 실증 (자동 + 가능 시 라이브)
- [ ] `probe troubleshoot` CLI 동작 (Khala 유/무 양쪽 — 티어 명시)
- [ ] `probe.groundTroubleshooting` MCP 도구 등록·동작
- [ ] Khala 없을 때 T0로 강등하며 명시 (침묵 강등 없음)
- [ ] README/CLAUDE 갱신
- [ ] 모든 출력이 "근거 모음(근본원인 단정 아님)" 원칙 준수

## 미해결(스펙 §11) — 구현 중 확정

- Q2 국소화 휴리스틱: Archon 코드 인덱스 생기면 대체될 fallback이므로 현 수준 유지(과투자 금지).
- Q3 이상치 임계: `ERROR_RATE_THRESHOLD = 0.05` (impact-analyzer와 일치).
- Q4 stdin 우선순위: 인자 우선, 비어있고 비-TTY면 stdin (Task 14 구현).
