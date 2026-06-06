# Probe v0.6 그라운디드 코드 리뷰 Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** git diff를 입력받아 변경 엔티티에 대한 비제너럴 조직 그라운딩(설계-관측 갭·규정·토폴로지·승인 스펙·claim drift)을 `ReviewGroundingPack`(증거만, 판정 없음)으로 조립해 CLI/MCP로 노출한다.

**Architecture:** v0.5 grounder 자산(`getDiff({entityFilter})`/`getStatusProbe`/`determineTier`/`analyzeImpact`/`search`)을 diff 입력으로 재사용한다. 새 `review-grounder`가 정규 조립기이고, v0.4 `enrichWithKhala`는 이 grounder에 위임하는 얇은 어댑터로 수렴(전역 diff 버그 교정). Probe는 diff 소스를 의미 분석하지 않는다 — 변경 파일→엔티티 라우팅까지만. 판정은 Claude.

**Tech Stack:** TypeScript (strict), Node ≥20, vitest, tsup. 기존 `src/khala`·`src/core`·`src/cli`·`src/mcp` 구조 준수.

**Spec:** `docs/superpowers/specs/2026-06-07-grounded-code-review-design.md`

---

## File Structure

**Create:**
- `src/khala/tier.ts` — `determineTier`/`TierDecision` 이전(khala 레이어). `core`/`khala` 양쪽이 순환 없이 공유.
- `src/khala/grounding-sections.ts` — 두 grounder 공유 섹션 헬퍼: `fetchEntityGaps`, `searchDocs`.
- `src/khala/review-grounder.ts` — `ChangedEntity[]` → `ReviewGroundingPack` 정규 조립기 + `partitionDocs`.
- `src/core/review-ground.ts` — `buildChangedEntities`(순수) + `runReviewGround`(티어→grounder→caveat).
- `tests/khala-tier.test.ts`, `tests/grounding-sections.test.ts`, `tests/review-grounder.test.ts`, `tests/core-review-ground.test.ts`, `tests/cli-review-ground.test.ts`(포맷터), `tests/signature-review-scenario.test.ts`.

**Modify:**
- `src/khala/types.ts` — `ReviewGroundingPack`/`ChangedEntity`/`SpecRef` 추가.
- `src/core/troubleshoot.ts` — `determineTier`/`TierDecision`를 `khala/tier.ts`에서 re-export(back-compat).
- `src/khala/troubleshoot-grounder.ts` — `fetchGaps`→`fetchEntityGaps`, `fetchKnowledge`→`searchDocs` 위임(DRY).
- `src/khala/context-enricher.ts` — `enrichWithKhala`를 `groundReview` 위임 어댑터로 축소(전역→엔티티 스코프 diff).
- `src/cli/index.ts` — `review:ground` 서브커맨드.
- `src/cli/parse-args.ts` — `parseReviewGroundArgs`.
- `src/cli/formatters.ts` — `formatReviewGroundingPackMarkdown`/`Brief`.
- `src/mcp/tools.ts` — 8번째 도구 `probe.groundReview`.
- `README.md`/`CLAUDE.md` — v0.6 현재 버전 표기 + 8 MCP 도구.

---

## Chunk 1: 타입 + 공유 헬퍼 + review-grounder

### Task 1: 신규 타입 추가

**Files:**
- Modify: `src/khala/types.ts` (ImpactedService/DesignGap/ClaimRef 정의 뒤, GroundingPack 부근)
- Test: `tests/troubleshoot-types.test.ts` (기존 타입 컴파일 테스트에 추가)

- [ ] **Step 1: 타입 컴파일 테스트 작성**

`tests/troubleshoot-types.test.ts`에 추가:
```typescript
import type { ReviewGroundingPack, ChangedEntity, SpecRef } from '../src/khala/types.js';

it('ReviewGroundingPack 타입이 구성된다', () => {
  const pack: ReviewGroundingPack = {
    tier: 2, tierReason: 'r',
    changedEntities: [{ entityName: 'order-service', changedFiles: ['a.ts'] }],
    caveats: [],
  };
  const spec: SpecRef = { docTitle: 't', sectionPath: 's', snippet: 'x', classification: 'INTERNAL' };
  const e: ChangedEntity = { entityName: 'x', changedFiles: [] };
  expect(pack.tier).toBe(2);
  expect(spec.docTitle).toBe('t');
  expect(e.entityName).toBe('x');
});
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `npx vitest run tests/troubleshoot-types.test.ts`
Expected: FAIL — `ReviewGroundingPack` 등 타입 없음 (TS2305/컴파일 에러)

- [ ] **Step 3: 타입 구현**

`src/khala/types.ts`의 `GroundingPack` 인터페이스 정의 바로 뒤에 추가:
```typescript
/** 변경 엔티티 — diff→service/entity 라우팅 산출 (v0.6) */
export interface ChangedEntity {
  /** grounder가 /graph·/diff에 넘길 정규화 service/entity명 */
  entityName: string;
  /** fileBelongsToService로 이 엔티티에 귀속된 변경 파일 */
  changedFiles: string[];
  /** scope-analyzer 응집 그룹명 (추적용, 선택) */
  cohesionGroup?: string;
}

/** specledger가 Khala에 발행한 승인 스펙의 읽기전용 투영 (v0.6) */
export interface SpecRef {
  docTitle: string;
  sectionPath: string;
  /** specledger content-hash 스탬프 (있으면) */
  approvedHash?: string;
  snippet: string;
  classification: string;
}

/** 리뷰 그라운딩 결과 — 증거만, 정합 판정은 Claude가 한다 (v0.6) */
export interface ReviewGroundingPack {
  tier: 0 | 1 | 2 | 3;
  tierReason: string;
  changedEntities: ChangedEntity[];
  applicableGuidelines?: RelevantDoc[];
  specRefs?: SpecRef[];
  topology?: ImpactAnalysis;
  designObservationGaps?: DesignGap[];
  claimDrift?: ClaimRef[];
  caveats: string[];
}
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `npx vitest run tests/troubleshoot-types.test.ts`
Expected: PASS

- [ ] **Step 5: 커밋**

```bash
git add src/khala/types.ts tests/troubleshoot-types.test.ts
git commit -m "feat: add ReviewGroundingPack/ChangedEntity/SpecRef types (v0.6)"
```

### Task 2: determineTier를 khala/tier.ts로 이전 (순환 방지)

**근거:** `enrichWithKhala`(khala 레이어)가 티어를 계산하려면 `determineTier`가 필요한데, 현재 `core/troubleshoot.ts`에 있어 khala→core 순환이 생긴다. khala 레이어로 옮기고 core는 re-export한다. 기존 테스트는 `core/troubleshoot`에서 import하므로 re-export로 무변경 통과.

**Files:**
- Create: `src/khala/tier.ts`
- Modify: `src/core/troubleshoot.ts` (determineTier/TierDecision 정의 삭제 → re-export)
- Test: `tests/khala-tier.test.ts`

- [ ] **Step 1: 실패 테스트 작성**

`tests/khala-tier.test.ts`:
```typescript
import { describe, it, expect } from 'vitest';
import { determineTier } from '../src/khala/tier.js';
import type { KhalaStatusResult } from '../src/khala/types.js';

describe('determineTier (khala/tier)', () => {
  it('null+timeout이면 T0이고 미가용과 사유가 다르다', () => {
    expect(determineTier(null, 'timeout').tier).toBe(0);
    expect(determineTier(null, 'timeout').reason).not.toBe(determineTier(null, 'unreachable').reason);
  });
  it('관측 엣지가 있으면 T3', () => {
    const s: KhalaStatusResult = { db_connected: true, edges_count: 3, observed_edges_count: 2 };
    expect(determineTier(s).tier).toBe(3);
  });
});
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `npx vitest run tests/khala-tier.test.ts`
Expected: FAIL — `src/khala/tier.js` 없음

- [ ] **Step 3: tier.ts 작성 + core 재export**

`src/khala/tier.ts` (현재 `core/troubleshoot.ts`의 `TierDecision`+`determineTier` 본문을 그대로 이동):
```typescript
/**
 * 그라운딩 티어 결정 — /status 카운트와 실패 사유로 T0~T3을 판정한다.
 * v0.5(troubleshoot)와 v0.6(review)이 공유한다. khala 레이어에 둬서 순환을 피한다.
 */
import type { KhalaStatusResult } from './types.js';

export interface TierDecision {
  tier: 0 | 1 | 2 | 3;
  reason: string;
}

export function determineTier(
  status: KhalaStatusResult | null,
  failure?: 'timeout' | 'unreachable',
): TierDecision {
  if (!status || !status.db_connected) {
    if (failure === 'timeout') {
      return {
        tier: 0,
        reason: 'Khala 응답 시간 초과 → T0 (느림/콜드스타트 가능 — 재시도 권장, Khala timeout)',
      };
    }
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
```

`src/core/troubleshoot.ts`에서 `TierDecision` 인터페이스와 `determineTier` 함수 정의를 **삭제**하고, 파일 상단 import 영역에 re-export 추가:
```typescript
// 티어 결정은 khala/tier로 이전됨 (순환 방지). back-compat re-export.
export { determineTier } from '../khala/tier.js';
export type { TierDecision } from '../khala/tier.js';
```
(`runTroubleshoot` 내부의 `determineTier(...)` 호출은 그대로 동작 — 같은 심볼.)

- [ ] **Step 4: 전체 테스트 통과 확인 (기존 core-troubleshoot 회귀 포함)**

Run: `npx vitest run tests/khala-tier.test.ts tests/core-troubleshoot.test.ts`
Expected: PASS (both) — 기존 `core-troubleshoot.test.ts`의 `determineTier` import는 re-export로 통과

- [ ] **Step 5: 커밋**

```bash
git add src/khala/tier.ts src/core/troubleshoot.ts tests/khala-tier.test.ts
git commit -m "refactor: move determineTier to khala/tier (avoid khala→core cycle)"
```

### Task 3: 공유 섹션 헬퍼 추출 (grounding-sections.ts)

**근거:** `troubleshoot-grounder`의 `fetchGaps`(엔티티 스코프 /diff)와 `fetchKnowledge`(search→RelevantDoc 매핑)는 review-grounder와 동일하다. DRY로 추출하고 troubleshoot-grounder를 위임시킨다. 동작 불변이라 기존 테스트 green 유지.

**Files:**
- Create: `src/khala/grounding-sections.ts`
- Modify: `src/khala/troubleshoot-grounder.ts` (fetchGaps/fetchKnowledge → 공유 헬퍼 위임)
- Test: `tests/grounding-sections.test.ts`

- [ ] **Step 1: 실패 테스트 작성**

`tests/grounding-sections.test.ts`:
```typescript
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { fetchEntityGaps, searchDocs } from '../src/khala/grounding-sections.js';
import { KhalaClient } from '../src/khala/client.js';

function mockByPath(handlers: Record<string, unknown>) {
  return vi.fn((url: string) => {
    const path = new URL(url).pathname;
    const key = Object.keys(handlers).find((k) => path.startsWith(k));
    return Promise.resolve({ ok: true, status: 200,
      json: () => Promise.resolve({ success: true, data: key ? handlers[key] : {}, error: null, meta: {} }) });
  });
}

describe('grounding-sections', () => {
  let orig: typeof globalThis.fetch;
  beforeEach(() => { orig = globalThis.fetch; });
  afterEach(() => { globalThis.fetch = orig; });

  it('fetchEntityGaps는 엔티티별 /diff를 합쳐 DesignGap[]을 만든다', async () => {
    globalThis.fetch = mockByPath({ '/diff': { diffs: [
      { flag: 'doc_only', from_name: 'a', to_name: 'b', edge_type: 'CALLS', detail: 'd', designed_evidence: [], observed_evidence: null },
    ] } }) as unknown as typeof globalThis.fetch;
    const gaps = await fetchEntityGaps(new KhalaClient({ baseUrl: 'http://t:8000' }), ['order-service']);
    expect(gaps[0]!.flag).toBe('doc_only');
  });

  it('fetchEntityGaps는 모든 diff가 null이면 throw한다', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({ ok: false, status: 500, json: () => Promise.resolve({ success: false, error: 'e' }) }) as unknown as typeof globalThis.fetch;
    await expect(fetchEntityGaps(new KhalaClient({ baseUrl: 'http://t:8000' }), ['x'])).rejects.toThrow();
  });

  it('searchDocs는 검색 히트를 RelevantDoc[]로 매핑한다', async () => {
    globalThis.fetch = mockByPath({ '/search': { results: [
      { doc_title: 'T', section_path: '1', snippet: 's', score: 0.9, classification: 'INTERNAL' },
    ] } }) as unknown as typeof globalThis.fetch;
    const docs = await searchDocs(new KhalaClient({ baseUrl: 'http://t:8000' }), 'q', 5);
    expect(docs?.[0]!.docTitle).toBe('T');
  });
});
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `npx vitest run tests/grounding-sections.test.ts`
Expected: FAIL — 모듈 없음

- [ ] **Step 3: grounding-sections.ts 작성**

`src/khala/grounding-sections.ts` (현재 troubleshoot-grounder.ts의 `fetchGaps`/`fetchKnowledge` 본문을 일반화해 이동):
```typescript
/**
 * 두 grounder(troubleshoot v0.5 / review v0.6) 공유 Khala 섹션 헬퍼.
 * 동일 호출의 중복을 막기 위해 추출됐다 — 출력 팩 조립만 각 grounder가 한다.
 */
import type { KhalaClient } from './client.js';
import type { DesignGap, RelevantDoc } from './types.js';

/** 각 엔티티의 엔티티 스코프 /diff를 합쳐 DesignGap[]로 변환한다.
 *  모든 diff 조회가 null이면 throw해 상위 withKhalaFallback이 caveat을 남기게 한다. */
export async function fetchEntityGaps(client: KhalaClient, names: string[]): Promise<DesignGap[]> {
  const results = await Promise.all(names.map((n) => client.getDiff({ entityFilter: n })));
  const ok = results.filter((r) => r !== null);
  if (ok.length === 0 && names.length > 0) {
    throw new Error('diff 조회 전체 실패 (All diff lookups failed)');
  }
  const gaps: DesignGap[] = [];
  for (const r of ok) {
    for (const d of r!.diffs) {
      gaps.push({
        flag: d.flag, fromName: d.from_name, toName: d.to_name,
        edgeType: d.edge_type, detail: d.detail,
        designedEvidence: d.designed_evidence.length > 0
          ? d.designed_evidence.map((e) => e.text).join('; ')
          : undefined,
        observedEvidence: d.observed_evidence?.sample_trace_ids,
      });
    }
  }
  return gaps;
}

/** 쿼리로 문서를 검색해 RelevantDoc[]로 매핑한다. 실패 시 null. */
export async function searchDocs(
  client: KhalaClient, query: string, topK: number,
): Promise<RelevantDoc[] | null> {
  const result = await client.search(query, { topK });
  if (!result) return null;
  return result.results.map((h) => ({
    docTitle: h.doc_title, sectionPath: h.section_path,
    snippet: h.snippet, score: h.score, classification: h.classification,
  }));
}
```

- [ ] **Step 4: troubleshoot-grounder를 공유 헬퍼로 위임**

`src/khala/troubleshoot-grounder.ts`:
1. import 추가: `import { fetchEntityGaps, searchDocs } from './grounding-sections.js';`
2. `fetchKnowledge` 본문을 `return searchDocs(client, signal.slice(0, 500), topK);`로 교체(또는 호출부를 `searchDocs(client, options.signal.slice(0,500), ...)`로 바꾸고 로컬 `fetchKnowledge` 제거).
3. 로컬 `fetchGaps` 제거하고 호출부 `fetchGaps(client, names)` → `fetchEntityGaps(client, names)`.

- [ ] **Step 5: 전체 회귀 통과 확인**

Run: `npx vitest run tests/grounding-sections.test.ts tests/troubleshoot-grounder.test.ts`
Expected: PASS (both) — troubleshoot-grounder 동작 불변

- [ ] **Step 6: 커밋**

```bash
git add src/khala/grounding-sections.ts src/khala/troubleshoot-grounder.ts tests/grounding-sections.test.ts
git commit -m "refactor: extract shared grounding-sections (fetchEntityGaps/searchDocs)"
```

### Task 4: review-grounder.ts (정규 조립기 + partitionDocs)

**Files:**
- Create: `src/khala/review-grounder.ts`
- Test: `tests/review-grounder.test.ts`

- [ ] **Step 1: 실패 테스트 작성**

`tests/review-grounder.test.ts`:
```typescript
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { groundReview, partitionDocs } from '../src/khala/review-grounder.js';
import { KhalaClient } from '../src/khala/client.js';
import type { RelevantDoc } from '../src/khala/types.js';

function mockByPath(handlers: Record<string, unknown>) {
  return vi.fn((url: string) => {
    const path = new URL(url).pathname;
    const key = Object.keys(handlers).find((k) => path.startsWith(k));
    return Promise.resolve({ ok: true, status: 200,
      json: () => Promise.resolve({ success: true, data: key ? handlers[key] : {}, error: null, meta: {} }) });
  });
}

describe('partitionDocs', () => {
  it('스펙 마커가 제목/경로에 있으면 specRefs로, 아니면 guidelines로 분리한다', () => {
    const docs: RelevantDoc[] = [
      { docTitle: 'Order Spec', sectionPath: '2', snippet: 's1', score: 0.9, classification: 'INTERNAL' },
      { docTitle: '결제 규정', sectionPath: '1', snippet: 's2', score: 0.8, classification: 'INTERNAL' },
    ];
    const { specRefs, guidelines } = partitionDocs(docs, ['spec', '스펙']);
    expect(specRefs).toHaveLength(1);
    expect(specRefs[0]!.docTitle).toBe('Order Spec');
    expect(guidelines).toHaveLength(1);
    expect(guidelines[0]!.docTitle).toBe('결제 규정');
  });
});

describe('groundReview', () => {
  let orig: typeof globalThis.fetch;
  beforeEach(() => { orig = globalThis.fetch; });
  afterEach(() => { globalThis.fetch = orig; });

  it('T3에서 엔티티 스코프 갭과 토폴로지를 담는다', async () => {
    globalThis.fetch = mockByPath({
      '/search': { results: [{ doc_title: 'Order Spec', section_path: '2', snippet: 's', score: 0.9, classification: 'INTERNAL' }] },
      '/graph': { center_entity: { rid: 'e', name: 'order-service' },
        edges: [{ rid: 'e1', edge_type: 'CALLS', from_name: 'order-service', to_name: 'inventory-service', from_rid: 'a', to_rid: 'b', confidence: 0.9, hop: 1, evidence: [] }],
        observed_edges: [{ rid: 'o1', edge_type: 'CALLS_OBSERVED', from_name: 'order-service', to_name: 'inventory-service', call_count: 100, error_rate: 0.2, latency_p95: 800, sample_trace_ids: ['t1'], trace_query_ref: 'r' }] },
      '/diff': { diffs: [{ flag: 'observed_only', from_name: 'order-service', to_name: 'inventory-service', edge_type: 'CALLS_OBSERVED', detail: '설계에 없음', designed_evidence: [], observed_evidence: { sample_trace_ids: ['t1'], trace_query_ref: 'r' } }] },
    }) as unknown as typeof globalThis.fetch;

    const client = new KhalaClient({ baseUrl: 'http://t:8000' });
    const pack = await groundReview(client,
      [{ entityName: 'order-service', changedFiles: ['OrderService.java'] }],
      { tier: 3 });

    expect(pack.designObservationGaps?.some((g) => g.flag === 'observed_only')).toBe(true);
    expect(pack.specRefs?.some((s) => s.docTitle === 'Order Spec')).toBe(true);
    expect(pack.topology?.changedServices).toContain('order-service');
  });

  it('스펙 미발견 시 caveat를 남긴다', async () => {
    globalThis.fetch = mockByPath({
      '/search': { results: [{ doc_title: '결제 규정', section_path: '1', snippet: 's', score: 0.8, classification: 'INTERNAL' }] },
      '/graph': { center_entity: { rid: 'e', name: 'order-service' }, edges: [], observed_edges: [] },
      '/diff': { diffs: [] },
    }) as unknown as typeof globalThis.fetch;
    const client = new KhalaClient({ baseUrl: 'http://t:8000' });
    const pack = await groundReview(client, [{ entityName: 'order-service', changedFiles: [] }], { tier: 3 });
    expect(pack.caveats.some((c) => c.includes('승인 스펙') || c.toLowerCase().includes('spec'))).toBe(true);
    expect(pack.applicableGuidelines?.some((g) => g.docTitle === '결제 규정')).toBe(true);
  });

  it('Archon 미연동 caveat를 항상 남긴다', async () => {
    globalThis.fetch = mockByPath({ '/search': { results: [] }, '/graph': { center_entity: { rid: 'e', name: 'x' }, edges: [], observed_edges: [] }, '/diff': { diffs: [] } }) as unknown as typeof globalThis.fetch;
    const client = new KhalaClient({ baseUrl: 'http://t:8000' });
    const pack = await groundReview(client, [{ entityName: 'x', changedFiles: [] }], { tier: 2 });
    expect(pack.caveats.some((c) => c.includes('Archon'))).toBe(true);
  });
});
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `npx vitest run tests/review-grounder.test.ts`
Expected: FAIL — 모듈 없음

- [ ] **Step 3: review-grounder.ts 구현**

`src/khala/review-grounder.ts`:
```typescript
/**
 * 리뷰 Grounding Pack 조립 (v0.6)
 *
 * ChangedEntity[]와 KhalaClient로 §2~§6 섹션을 병렬 조립한다.
 * 각 섹션은 독립 실패해도 나머지를 막지 않는다 (withKhalaFallback).
 * Probe는 diff 소스를 의미 분석하지 않는다 — 변경 엔티티에 대한 조직 그라운딩만 모은다.
 *
 * 규정 문서: docs/superpowers/specs/2026-06-07-grounded-code-review-design.md
 */
import { KhalaClient, withKhalaFallback } from './client.js';
import { analyzeImpact } from './impact-analyzer.js';
import { fetchEntityGaps, searchDocs } from './grounding-sections.js';
import type {
  ChangedEntity, ReviewGroundingPack, SpecRef, RelevantDoc, ImpactAnalysis,
} from './types.js';

/** 승인 스펙 식별 기본 마커 (구현 계획 §11 Q1/Q5 — production 마커는 추후 튜닝) */
const DEFAULT_SPEC_MARKERS = ['spec', '스펙', 'adr', 'rfc'];

export interface ReviewGroundOptions {
  tier: 0 | 1 | 2 | 3;
  searchTopK?: number;
  graphHops?: number;
  /** 승인 스펙 식별 마커 (제목/섹션경로에 포함되면 specRef로 투영) */
  specMarkers?: string[];
}

/** 검색 문서를 승인 스펙(specRefs)과 일반 규정(guidelines)으로 분리한다.
 *  한 문서가 양쪽에 중복되지 않도록 배타 분배한다 (스펙 §11 Q5). */
export function partitionDocs(
  docs: RelevantDoc[], specMarkers: string[],
): { specRefs: SpecRef[]; guidelines: RelevantDoc[] } {
  const specRefs: SpecRef[] = [];
  const guidelines: RelevantDoc[] = [];
  for (const d of docs) {
    const hay = `${d.docTitle} ${d.sectionPath}`.toLowerCase();
    if (specMarkers.some((m) => hay.includes(m.toLowerCase()))) {
      specRefs.push({
        docTitle: d.docTitle, sectionPath: d.sectionPath,
        snippet: d.snippet, classification: d.classification,
      });
    } else {
      guidelines.push(d);
    }
  }
  return { specRefs, guidelines };
}

/** 변경 엔티티에 대한 Review Grounding Pack을 조립한다 (티어가 허용하는 섹션까지). */
export async function groundReview(
  client: KhalaClient,
  changedEntities: ChangedEntity[],
  options: ReviewGroundOptions,
): Promise<ReviewGroundingPack> {
  const caveats: string[] = [];
  const pack: ReviewGroundingPack = {
    tier: options.tier, tierReason: '', changedEntities, caveats,
  };
  const names = changedEntities.map((e) => e.entityName);

  // §2/§3 지식 → 규정 + 승인 스펙 분리 (T1+)
  if (options.tier >= 1 && names.length > 0) {
    const docs = await withKhalaFallback(
      () => searchDocs(client, names.join(' '), options.searchTopK ?? 5),
      null, 'search',
    );
    if (docs) {
      const { specRefs, guidelines } = partitionDocs(docs, options.specMarkers ?? DEFAULT_SPEC_MARKERS);
      if (guidelines.length) pack.applicableGuidelines = guidelines;
      if (specRefs.length) pack.specRefs = specRefs;
      else caveats.push('변경 엔티티에 대한 승인 스펙 미발견 (No approved spec found)');
    } else {
      caveats.push('지식 그라운딩(search) 조회 실패 (Knowledge grounding unavailable)');
    }
  }

  // §4 토폴로지/영향 (T2+)
  if (options.tier >= 2 && names.length > 0) {
    const topology = await withKhalaFallback<ImpactAnalysis | null>(
      () => analyzeImpact(client, names, { hops: options.graphHops ?? 2 }),
      null, 'impact',
    );
    if (topology) pack.topology = topology;
  }

  // §5 설계-관측 갭 (doc_only는 T2+, observed_only/conflict는 T3)
  if (options.tier >= 2 && names.length > 0) {
    const gaps = await withKhalaFallback(
      () => fetchEntityGaps(client, names),
      null, 'diff',
    );
    if (gaps) {
      pack.designObservationGaps = options.tier >= 3
        ? gaps
        : gaps.filter((g) => g.flag === 'doc_only');
    } else {
      caveats.push('설계-관측 갭(diff) 조회 실패 (Design-observation gap unavailable)');
    }
  }

  // §6 도메인 claim drift — Archon seam (미연동 시 생략 + caveat)
  if (!pack.claimDrift) {
    caveats.push('도메인 claim drift 그라운딩은 Archon 미연동으로 생략됨 (Archon not integrated)');
  }

  return pack;
}
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `npx vitest run tests/review-grounder.test.ts`
Expected: PASS

- [ ] **Step 5: 커밋**

```bash
git add src/khala/review-grounder.ts tests/review-grounder.test.ts
git commit -m "feat: add review-grounder (ChangedEntity[] -> ReviewGroundingPack)"
```

---

## Chunk 2: core 오케스트레이션 + enrichWithKhala 수렴

### Task 5: buildChangedEntities + runReviewGround (core/review-ground.ts)

**Files:**
- Create: `src/core/review-ground.ts`
- Test: `tests/core-review-ground.test.ts`

- [ ] **Step 1: 실패 테스트 작성**

`tests/core-review-ground.test.ts`:
```typescript
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { buildChangedEntities, runReviewGround } from '../src/core/review-ground.js';
import { KhalaClient } from '../src/khala/client.js';
import type { DetectedGroup } from '../src/core/scope-analyzer.js';

describe('buildChangedEntities', () => {
  it('응집 그룹+변경파일에서 엔티티와 귀속 파일을 만든다', () => {
    const groups: DetectedGroup[] = [
      { groupName: 'domain-crud', cohesionKeyValue: 'Order', files: [{ path: 'src/order/OrderService.java', role: 'Service' }] },
    ];
    const entities = buildChangedEntities(groups, ['src/order/OrderService.java', 'README.md']);
    const order = entities.find((e) => e.entityName === 'order-service');
    expect(order).toBeDefined();
    expect(order!.changedFiles).toContain('src/order/OrderService.java');
    expect(order!.changedFiles).not.toContain('README.md');
  });
});

describe('runReviewGround', () => {
  let orig: typeof globalThis.fetch;
  beforeEach(() => { orig = globalThis.fetch; });
  afterEach(() => { globalThis.fetch = orig; });

  it('엔티티 0개면 ok:false', async () => {
    const client = new KhalaClient({ baseUrl: 'http://t:8000' });
    const r = await runReviewGround([], client);
    expect(r.ok).toBe(false);
  });

  it('Khala 미가용이면 T0 + changedEntities만', async () => {
    globalThis.fetch = vi.fn().mockRejectedValue(new Error('down')) as unknown as typeof globalThis.fetch;
    const client = new KhalaClient({ baseUrl: 'http://t:8000' });
    const r = await runReviewGround([{ entityName: 'order-service', changedFiles: ['a.ts'] }], client);
    expect(r.ok).toBe(true);
    if (r.ok) {
      expect(r.pack.tier).toBe(0);
      expect(r.pack.changedEntities[0]!.entityName).toBe('order-service');
    }
  });
});
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `npx vitest run tests/core-review-ground.test.ts`
Expected: FAIL — 모듈 없음

- [ ] **Step 3: core/review-ground.ts 구현**

`src/core/review-ground.ts`:
```typescript
/**
 * 리뷰 그라운딩 오케스트레이션 (v0.6) — 변경 엔티티 빌드, 티어 결정, grounder 호출.
 *
 * Probe는 diff 소스를 의미 분석하지 않는다 — 변경 파일→엔티티 라우팅까지만.
 * 규정 문서: docs/superpowers/specs/2026-06-07-grounded-code-review-design.md
 */
import { KhalaClient } from '../khala/client.js';
import { determineTier } from '../khala/tier.js';
import { groundReview, type ReviewGroundOptions } from '../khala/review-grounder.js';
import { extractServiceNames, fileBelongsToService } from '../khala/context-enricher.js';
import type { ChangedEntity, ReviewGroundingPack } from '../khala/types.js';
import type { DetectedGroup } from './scope-analyzer.js';

/** 응집 그룹 + 변경 파일에서 ChangedEntity[]를 만든다 (순수 — 소스 의미분석 없음). */
export function buildChangedEntities(
  groups: DetectedGroup[], changedFiles: string[],
): ChangedEntity[] {
  const groupOf = new Map<string, string>(); // entityName → cohesionGroup
  const entities: ChangedEntity[] = [];
  for (const group of groups) {
    for (const name of extractServiceNames([group])) {
      if (!groupOf.has(name)) groupOf.set(name, group.groupName);
    }
  }
  for (const name of new Set(groupOf.keys())) {
    const files = changedFiles.filter((f) => fileBelongsToService(f, name));
    entities.push({ entityName: name, changedFiles: files, cohesionGroup: groupOf.get(name) });
  }
  return entities;
}

/** 리뷰 그라운딩 전체 실행. */
export async function runReviewGround(
  changedEntities: ChangedEntity[],
  client: KhalaClient,
  options?: Partial<ReviewGroundOptions>,
): Promise<{ ok: false; reason: string } | { ok: true; pack: ReviewGroundingPack }> {
  if (changedEntities.length === 0) {
    return { ok: false, reason: '변경 엔티티를 귀속하지 못함 (No changed entities). 파일 경로/플랫폼 프로파일을 확인하세요.' };
  }

  const probe = await client.getStatusProbe();
  const status = probe.ok ? probe.status : null;
  const tierDecision = determineTier(status, probe.ok ? undefined : probe.reason);

  const pack = await groundReview(client, changedEntities, {
    tier: tierDecision.tier,
    searchTopK: options?.searchTopK,
    graphHops: options?.graphHops,
    specMarkers: options?.specMarkers,
  });
  pack.tierReason = tierDecision.reason;

  return { ok: true, pack };
}
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `npx vitest run tests/core-review-ground.test.ts`
Expected: PASS

- [ ] **Step 5: 커밋**

```bash
git add src/core/review-ground.ts tests/core-review-ground.test.ts
git commit -m "feat: add core review-ground orchestration (buildChangedEntities/runReviewGround)"
```

### Task 6: enrichWithKhala를 groundReview 위임 어댑터로 수렴

**근거(스펙 §1.3/§5.1):** v0.4 enrichWithKhala는 전역 `/diff`를 써 노이즈가 크다. groundReview에 위임해 엔티티 스코프 diff로 교정하고, 결과를 레거시 `EnrichmentResult`로 투영한다. EnrichmentResult 형태는 불변 → MCP scope 도구 호환.

**Files:**
- Modify: `src/khala/context-enricher.ts` (`enrichWithKhala` 본문 교체; `extractServiceNames`/`fileBelongsToService`/검색 헬퍼는 유지)
- Test: `tests/context-enricher.test.ts` (기존 enrichWithKhala 테스트 + 신규 위임/투영 회귀)

> ⚠️ 순환 주의: `context-enricher.ts`(khala)가 `review-grounder`(khala)·`tier`(khala)·`buildChangedEntities`(core)를 import. `buildChangedEntities`는 `context-enricher`를 import하므로 **core→khala 단방향 유지**를 위해, 어댑터는 `buildChangedEntities`를 쓰지 말고 엔티티를 `context-enricher` 로컬에서 직접 만든다(이미 `extractServiceNames`/`fileBelongsToService` 보유). 즉 core를 import하지 않는다.

- [ ] **Step 1: 기존 enrichWithKhala 테스트의 `/status` 목 갱신 (필수 — 회귀 방지)**

신규 어댑터는 `isAvailable()`(`.ok`만 검사) 대신 `getStatusProbe()`(`await response.json()` + `{success,data}` 요구)를 쓴다. 기존 테스트 2개는 `/status`(또는 availability)를 `{ ok: true, status: 200 }`(json 메서드 없음)로 목킹해 **신규 코드에서 깨진다**. `tests/context-enricher.test.ts`에서 다음을 갱신한다:

1. **"서비스명을 추출할 수 없으면 빈 결과와 khalaAvailable=true를 반환한다"** — `globalThis.fetch = vi.fn().mockResolvedValue({ ok: true, status: 200 })`를 아래로 교체:
```typescript
globalThis.fetch = vi.fn().mockResolvedValue({
  ok: true, status: 200,
  json: () => Promise.resolve({ success: true, data: { db_connected: true, documents_count: 0, edges_count: 0 }, error: null, meta: {} }),
}) as unknown as typeof fetch;
```
(엔티티 추출 0개라 grounder 호출 전에 `{ ...EMPTY_ENRICHMENT, khalaAvailable: true }` 반환 — 단언 유지.)

2. **"칼라가 가용하면 3개 조회를 병렬 수행한다"** — `/status` 분기 `return Promise.resolve({ ok: true, status: 200 });`를 아래로 교체(T3 도달해 search/impact/diff 모두 실행):
```typescript
if (urlStr.includes('/status')) {
  return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({ success: true, data: { db_connected: true, documents_count: 5, edges_count: 3, observed_edges_count: 2 }, error: null, meta: {} }) });
}
```
이 테스트의 단언이 전역 `/diff` 기준(예: 호출 횟수)이면 엔티티 스코프 호출 수에 맞게 갱신한다.

- [ ] **Step 2: 위임/투영 회귀 테스트 작성**

`tests/context-enricher.test.ts`의 `enrichWithKhala` describe에 추가:
```typescript
it('엔티티 스코프 diff로 갭과 영향 서비스를 투영한다 (수렴 + Q6 평탄화)', async () => {
  // T3, /diff는 entity_filter 쿼리에서만 갭 반환 (전역 호출이면 빈 결과)
  globalThis.fetch = vi.fn((url: string) => {
    const u = new URL(url);
    if (u.pathname.startsWith('/status')) return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({ success: true, data: { db_connected: true, documents_count: 1, edges_count: 3, observed_edges_count: 2 }, error: null, meta: {} }) });
    if (u.pathname.startsWith('/diff')) {
      const hasFilter = u.searchParams.has('entity_filter');
      return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({ success: true, data: { diffs: hasFilter ? [{ flag: 'observed_only', from_name: 'order-service', to_name: 'inventory-service', edge_type: 'CALLS_OBSERVED', detail: 'd', designed_evidence: [], observed_evidence: { sample_trace_ids: ['t'], trace_query_ref: 'r' } }] : [] }, error: null, meta: {} }) });
    }
    if (u.pathname.startsWith('/graph')) return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({ success: true, data: { center_entity: { rid: 'e', name: 'order-service' }, edges: [{ rid: 'e1', edge_type: 'CALLS', from_name: 'order-service', to_name: 'inventory-service', from_rid: 'a', to_rid: 'b', confidence: 0.9, hop: 1, evidence: [] }], observed_edges: [] }, error: null, meta: {} }) });
    return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({ success: true, data: { results: [] }, error: null, meta: {} }) });
  }) as unknown as typeof globalThis.fetch;

  const groups = makeGroups(['Order']);
  const result = await enrichWithKhala(groups, ['src/order/OrderService.java'], { khalaConfig: { baseUrl: 'http://t:8000' } });
  expect(result.khalaAvailable).toBe(true);
  expect(result.designObservationGaps.some((g) => g.flag === 'observed_only')).toBe(true); // 엔티티 스코프라 발견
  expect(result.impactedServices.some((s) => s.name === 'inventory-service')).toBe(true); // Q6: topology → 평탄 impactedServices 투영
});
```

- [ ] **Step 3: 테스트 실패 확인**

Run: `npx vitest run tests/context-enricher.test.ts`
Expected: FAIL (신규 테스트) — 현재 enrichWithKhala는 전역 getDiff()라 entity_filter 미전송 → 갭 0. (Step 1 갱신분은 신규 코드 적용 전엔 통과/무관)

- [ ] **Step 4: enrichWithKhala 어댑터 구현**

`src/khala/context-enricher.ts`의 `enrichWithKhala` 본문을 교체(상단 import에 `determineTier`, `groundReview` 추가; 기존 `analyzeImpact`/`fetchDesignGaps`/`searchRelevantDocs` 등 전역 diff 의존 비공개 헬퍼는 제거 또는 미사용).
> ⚠️ 시그니처의 두 번째 파라미터를 `_changedFiles`(현재 미사용 prefix)에서 **`changedFiles`로 리네임**한다 — 신규 본문이 `fileBelongsToService`에 실제로 사용한다. 호출부(`mcp/tools.ts`)는 위치 인자라 무영향.
```typescript
import { determineTier } from './tier.js';
import { groundReview } from './review-grounder.js';
// ... 기존 import 유지 (KhalaClient, withKhalaFallback, types)

export async function enrichWithKhala(
  groups: DetectedGroup[],
  changedFiles: string[],
  options?: EnrichmentOptions,
): Promise<EnrichmentResult> {
  const client = new KhalaClient(options?.khalaConfig);

  const probe = await client.getStatusProbe();
  if (!probe.ok) {
    logger.debug(`칼라 미가용(${probe.reason}) — 보강 없이 진행`);
    return EMPTY_ENRICHMENT;
  }
  const tier = determineTier(probe.status).tier;

  // 변경 엔티티 빌드 (core 의존 금지 — 로컬 헬퍼 사용)
  const names = extractServiceNames(groups);
  if (names.length === 0) {
    return { ...EMPTY_ENRICHMENT, khalaAvailable: true };
  }
  const changedEntities = names.map((name) => ({
    entityName: name,
    changedFiles: changedFiles.filter((f) => fileBelongsToService(f, name)),
  }));

  const pack = await groundReview(client, changedEntities, {
    tier,
    searchTopK: options?.searchTopK,
    graphHops: options?.graphHops,
  });

  // ReviewGroundingPack → 레거시 EnrichmentResult 투영 (back-compat)
  return {
    relevantDocs: pack.applicableGuidelines ?? [],
    impactedServices: pack.topology
      ? pack.topology.directImpact.concat(pack.topology.indirectImpact)
      : [],
    designObservationGaps: pack.designObservationGaps ?? [],
    khalaAvailable: true,
  };
}
```
사용하지 않게 된 비공개 헬퍼(`fetchImpact`/`fetchDesignGaps`/`searchRelevantDocs` 중 전역 diff 쓰던 것)는 제거한다. `extractServiceNames`/`fileBelongsToService`는 **유지(export 그대로)** — core/review-ground와 테스트가 의존.

- [ ] **Step 5: 전체 테스트 통과 + 타입체크**

Run: `npx vitest run tests/context-enricher.test.ts && npx tsc --noEmit`
Expected: PASS (갱신된 기존 테스트 + 신규 위임 테스트) + 타입 에러 없음 (순환 import 없음 확인)

- [ ] **Step 6: 커밋**

```bash
git add src/khala/context-enricher.ts tests/context-enricher.test.ts
git commit -m "refactor: converge enrichWithKhala onto review-grounder (entity-scoped diff)"
```

---

## Chunk 3: CLI + MCP 표면 + 시그니처 + 문서

### Task 7: CLI 포맷터 (formatReviewGroundingPackMarkdown/Brief)

**Files:**
- Modify: `src/cli/formatters.ts` (formatGroundingPack* 뒤에 추가; import에 ReviewGroundingPack 추가)
- Test: `tests/cli-formatters.test.ts`

- [ ] **Step 1: 실패 테스트 작성**

`tests/cli-formatters.test.ts`에 추가:
```typescript
import { formatReviewGroundingPackMarkdown, formatReviewGroundingPackBrief } from '../src/cli/formatters.js';
import type { ReviewGroundingPack } from '../src/khala/types.js';

const pack: ReviewGroundingPack = {
  tier: 3, tierReason: 'r',
  changedEntities: [{ entityName: 'order-service', changedFiles: ['a.ts'] }],
  designObservationGaps: [{ flag: 'observed_only', fromName: 'order-service', toName: 'inventory-service', edgeType: 'CALLS_OBSERVED', detail: 'd' }],
  specRefs: [{ docTitle: 'Order Spec', sectionPath: '2', snippet: 's', classification: 'INTERNAL' }],
  caveats: ['c1'],
};

it('마크다운에 변경 엔티티/갭/스펙/한계가 포함된다', () => {
  const md = formatReviewGroundingPackMarkdown(pack);
  expect(md).toContain('order-service');
  expect(md).toContain('observed_only');
  expect(md).toContain('Order Spec');
  expect(md).toContain('c1');
  expect(md).toMatch(/판정.*Claude|증거/);
});

it('brief는 한 줄 요약이다', () => {
  expect(formatReviewGroundingPackBrief(pack)).toContain('T3');
});
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `npx vitest run tests/cli-formatters.test.ts`
Expected: FAIL — 함수 없음

- [ ] **Step 3: 포맷터 구현**

`src/cli/formatters.ts`의 import에 `ReviewGroundingPack` 추가, `formatGroundingPackBrief` 뒤에 추가:
```typescript
/** ReviewGroundingPack → 마크다운 (증거만, 정합 판정은 Claude) */
export function formatReviewGroundingPackMarkdown(pack: ReviewGroundingPack): string {
  const lines: string[] = [];
  lines.push(`## 🧭 리뷰 그라운딩 (T${pack.tier})`);
  lines.push('');
  lines.push(`> ${pack.tierReason}`);
  lines.push('> ⚠️ 이건 조직 컨텍스트 증거 모음입니다 — diff↔스펙/그래프/claim 정합 판정은 Claude/리뷰어가 합니다.');
  lines.push('');

  lines.push('### 변경 엔티티');
  for (const e of pack.changedEntities) {
    lines.push(`- \`${e.entityName}\`${e.cohesionGroup ? ` (${e.cohesionGroup})` : ''} — ${e.changedFiles.length}개 파일`);
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

  if (pack.specRefs?.length) {
    lines.push('### 승인 스펙 참조 (diff를 이 스펙에 비춰 검토)');
    for (const s of pack.specRefs) {
      lines.push(`- ${s.docTitle} > ${s.sectionPath}${s.approvedHash ? ` (hash ${s.approvedHash})` : ''}`);
    }
    lines.push('');
  }

  if (pack.applicableGuidelines?.length) {
    lines.push('### 적용 규정/문서');
    for (const d of pack.applicableGuidelines) lines.push(`- ${d.docTitle} > ${d.sectionPath} (score ${d.score.toFixed(2)})`);
    lines.push('');
  }

  if (pack.topology) {
    lines.push(`### 토폴로지 영향: ${pack.topology.summary}`);
    lines.push('');
  }

  if (pack.claimDrift?.length) {
    lines.push('### 도메인 claim drift (Archon)');
    for (const c of pack.claimDrift) {
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

/** ReviewGroundingPack → 한 줄 요약 */
export function formatReviewGroundingPackBrief(pack: ReviewGroundingPack): string {
  const names = pack.changedEntities.map((e) => e.entityName).join(', ') || '(엔티티 없음)';
  const gaps = pack.designObservationGaps?.length ?? 0;
  const specs = pack.specRefs?.length ?? 0;
  return `리뷰 그라운딩 T${pack.tier}: 엔티티 [${names}], 설계-관측 갭 ${gaps}개, 승인 스펙 ${specs}개`;
}
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `npx vitest run tests/cli-formatters.test.ts`
Expected: PASS

- [ ] **Step 5: 커밋**

```bash
git add src/cli/formatters.ts tests/cli-formatters.test.ts
git commit -m "feat: add ReviewGroundingPack formatters (markdown/brief)"
```

### Task 8: CLI parse-args (parseReviewGroundArgs)

**Files:**
- Modify: `src/cli/parse-args.ts`
- Test: `tests/cli-parse-args.test.ts`

- [ ] **Step 1: 실패 테스트 작성**

`tests/cli-parse-args.test.ts`에 추가:
```typescript
import { parseReviewGroundArgs } from '../src/cli/parse-args.js';

it('parseReviewGroundArgs는 --base/--format을 파싱한다', () => {
  const o = parseReviewGroundArgs(['--base', 'main', '--format', 'json']);
  expect(o.base).toBe('main');
  expect(o.format).toBe('json');
});
it('기본 format은 markdown, base는 undefined', () => {
  const o = parseReviewGroundArgs([]);
  expect(o.format).toBe('markdown');
  expect(o.base).toBeUndefined();
});
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `npx vitest run tests/cli-parse-args.test.ts`
Expected: FAIL — 함수 없음

- [ ] **Step 3: 구현**

`src/cli/parse-args.ts`에 추가(`OutputFormat` 타입 재사용):
```typescript
export interface ReviewGroundCliOptions {
  base?: string;
  format: OutputFormat;
}

export function parseReviewGroundArgs(args: string[]): ReviewGroundCliOptions {
  const o: ReviewGroundCliOptions = { format: 'markdown' };
  for (let i = 0; i < args.length; i++) {
    const arg = args[i]!;
    if (arg === '--base' && i + 1 < args.length) {
      o.base = args[++i]!;
    } else if (arg === '--format' && i + 1 < args.length) {
      const f = args[++i]!;
      if (f === 'markdown' || f === 'json' || f === 'brief') o.format = f;
    }
  }
  return o;
}
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `npx vitest run tests/cli-parse-args.test.ts`
Expected: PASS

- [ ] **Step 5: 커밋**

```bash
git add src/cli/parse-args.ts tests/cli-parse-args.test.ts
git commit -m "feat: add parseReviewGroundArgs (--base/--format)"
```

### Task 9: CLI 커맨드 배선 (review:ground)

**Files:**
- Modify: `src/cli/index.ts` (runReviewGroundCmd 추가 + switch에 'review:ground' case)

> 참고: 이 태스크는 git/프로파일 통합 배선이라 단위 테스트 대신 빌드+수동 스모크로 검증한다(기존 troubleshoot 커맨드도 동일 패턴). 순수 로직(buildChangedEntities/runReviewGround/포맷터)은 Task 5·7에서 이미 테스트됨.

- [ ] **Step 1: runReviewGroundCmd 구현**

`src/cli/index.ts`에 추가(기존 import에 `parseReviewGroundArgs`, `buildChangedEntities`/`runReviewGround`, `formatReviewGroundingPackMarkdown`/`Brief` 추가):
```typescript
/**
 * review:ground 커맨드 — git diff → Review Grounding Pack
 */
async function runReviewGroundCmd(args: string[]): Promise<void> {
  const o = parseReviewGroundArgs(args);
  const config = await loadConfigAsync();
  const { profile } = await resolveProfileForCli(config);
  if (!profile) {
    logger.error('플랫폼을 감지할 수 없습니다 (Platform not detected)');
    process.exitCode = 1;
    return;
  }

  const changedFiles = getChangedFiles(o.base);
  if (changedFiles.length === 0) {
    logger.info('변경 파일이 없습니다 (No changed files).');
    return;
  }

  const scope = analyzeScope(changedFiles, profile, getDiffLines(o.base));
  const entities = buildChangedEntities(scope.groups, changedFiles);

  const khalaConfig = resolveKhalaConfig(config);
  const client = new KhalaClient(khalaConfig);
  const result = await runReviewGround(entities, client, {
    searchTopK: khalaConfig.searchTopK, graphHops: khalaConfig.graphHops,
  });

  if (!result.ok) {
    logger.error(result.reason);
    process.exitCode = 1;
    return;
  }

  switch (o.format) {
    case 'json': logger.info(JSON.stringify(result.pack, null, 2)); break;
    case 'brief': logger.info(formatReviewGroundingPackBrief(result.pack)); break;
    case 'markdown':
    default: logger.info(formatReviewGroundingPackMarkdown(result.pack)); break;
  }
}
```
switch 문에 추가:
```typescript
  case 'review:ground':
    void runReviewGroundCmd(args.slice(1));
    break;
```

- [ ] **Step 2: 빌드 + 스모크 (Khala 없이 T0 경로)**

Run: `npx tsc --noEmit && npx tsup && node dist/cli/index.js review:ground --format brief` (또는 빌드 산출 경로에 맞게)
Expected: 타입/빌드 통과; Khala 미가용 시 "리뷰 그라운딩 T0: ..." 한 줄 또는 "변경 파일 없음". 비-제로 종료 아님.

- [ ] **Step 3: 커밋**

```bash
git add src/cli/index.ts
git commit -m "feat: wire 'probe review:ground' CLI command"
```

### Task 10: MCP 8번째 도구 (probe.groundReview)

**Files:**
- Modify: `src/mcp/tools.ts` (probe.groundTroubleshooting 뒤에 추가; import에 runReviewGround/buildChangedEntities/analyzeScope/getDiffLines 추가)
- Create: `tests/mcp-registration.test.ts` (신규 — `registerTools` 도구 등록 검증)

> 참고: 기존 `tests/mcp-tools.test.ts`는 **도구를 등록하지 않고** 코어 함수만 직접 검증한다(server.tool 스파이/헬퍼 없음). 따라서 등록 검증은 신규 파일에 가벼운 `server.tool` 스파이 하니스로 작성한다. 핸들러 코어 경로(`buildChangedEntities`+`runReviewGround`)는 Task 5에서 이미 테스트됨.

- [ ] **Step 1: 등록 검증 테스트 작성 (신규 하니스)**

`tests/mcp-registration.test.ts`:
```typescript
import { describe, it, expect } from 'vitest';
import { registerTools } from '../src/mcp/tools.js';
import type { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js';

/** registerTools가 등록하는 도구 이름을 수집하는 최소 스파이 서버.
 *  registerTools는 server.tool(name, desc, schema, handler)만 호출하므로
 *  tool 메서드만 있으면 충분하다 (핸들러는 등록 시 호출되지 않음). */
function collectToolNames(): string[] {
  const names: string[] = [];
  const fakeServer = { tool: (name: string) => { names.push(name); } } as unknown as McpServer;
  registerTools(fakeServer);
  return names;
}

describe('MCP 도구 등록', () => {
  it('probe.groundReview를 포함해 8개 도구가 등록된다', () => {
    const names = collectToolNames();
    expect(names).toContain('probe.groundReview');
    expect(names).toContain('probe.groundTroubleshooting');
    expect(names.length).toBe(8);
  });
});
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `npx vitest run tests/mcp-registration.test.ts`
Expected: FAIL — `probe.groundReview` 미등록, length 7

- [ ] **Step 3: 도구 등록 구현**

`src/mcp/tools.ts` `probe.groundTroubleshooting` 등록 뒤에 추가:
```typescript
  // ─── probe.groundReview (v0.6) ───
  server.tool(
    'probe.groundReview',
    'git diff를 받아 변경 엔티티의 조직 컨텍스트(설계-관측 갭·규정·토폴로지·승인 스펙·claim drift)를 묶은 Review Grounding Pack을 반환한다. diff의 소스 의미 분석/정합 판정은 하지 않는다 — 그건 호출자(Claude)가 한다.',
    {
      base: z.string().optional().describe('git diff base (예: origin/main)'),
    },
    async ({ base }) => {
      const { profile, config } = await resolveProfile();
      if (!profile) {
        return { content: [{ type: 'text' as const, text: '플랫폼을 감지할 수 없습니다 (Platform not detected)' }] };
      }
      const changedFiles = getChangedFiles(base);
      if (changedFiles.length === 0) {
        return { content: [{ type: 'text' as const, text: JSON.stringify({ error: '변경 파일 없음 (No changed files)' }) }] };
      }
      const scope = analyzeScope(changedFiles, profile, getDiffLines(base));
      const entities = buildChangedEntities(scope.groups, changedFiles);
      const khalaConfig = resolveKhalaConfig(config);
      const client = new KhalaClient(khalaConfig);
      const result = await runReviewGround(entities, client, {
        searchTopK: khalaConfig.searchTopK, graphHops: khalaConfig.graphHops,
      });
      const payload = result.ok ? result.pack : { error: result.reason };
      return { content: [{ type: 'text' as const, text: JSON.stringify(payload, null, 2) }] };
    },
  );
```
파일 상단 도구 카운트 주석 "7개 도구"→"8개 도구", 목록에 `groundReview` 추가. import에 `runReviewGround`, `buildChangedEntities`(`../core/review-ground.js`), `analyzeScope`(이미 있음), `getDiffLines`(`../utils/git.js`) 추가.

- [ ] **Step 4: 테스트 통과 + 타입체크**

Run: `npx vitest run tests/mcp-registration.test.ts && npx tsc --noEmit`
Expected: PASS (8개 등록) + 타입 에러 없음

- [ ] **Step 5: 커밋**

```bash
git add src/mcp/tools.ts tests/mcp-registration.test.ts
git commit -m "feat: add probe.groundReview MCP tool (8th)"
```

### Task 11: 시그니처 시나리오 (해자 실증 SR1·SR3)

**Files:**
- Test: `tests/signature-review-scenario.test.ts`

> SR2(승인 스펙 정합)는 Task 4의 review-grounder 테스트에서 스펙 분리로 이미 커버. 여기서는 SR1(설계-관측 갭 모트)·SR3(T0 정직성)을 그라운딩 경로 통합으로 고정.

- [ ] **Step 1: SR1·SR3 테스트 작성**

`tests/signature-review-scenario.test.ts`:
```typescript
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { runReviewGround } from '../src/core/review-ground.js';
import { KhalaClient } from '../src/khala/client.js';

describe('시그니처 리뷰 시나리오', () => {
  let orig: typeof globalThis.fetch;
  beforeEach(() => { orig = globalThis.fetch; });
  afterEach(() => { globalThis.fetch = orig; });

  it('SR1 (T3 모트): order-service 변경이 observed_only order→inventory 갭을 드러낸다', async () => {
    globalThis.fetch = vi.fn((url: string) => {
      const u = new URL(url);
      if (u.pathname.startsWith('/status')) return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({ success: true, data: { db_connected: true, edges_count: 5, observed_edges_count: 3 }, error: null, meta: {} }) });
      if (u.pathname.startsWith('/diff')) return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({ success: true, data: { diffs: [{ flag: 'observed_only', from_name: 'order-service', to_name: 'inventory-service', edge_type: 'CALLS_OBSERVED', detail: '설계 문서에 없음', designed_evidence: [], observed_evidence: { sample_trace_ids: ['t1'], trace_query_ref: 'r' } }] }, error: null, meta: {} }) });
      if (u.pathname.startsWith('/graph')) return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({ success: true, data: { center_entity: { rid: 'e', name: 'order-service' }, edges: [], observed_edges: [{ rid: 'o1', edge_type: 'CALLS_OBSERVED', from_name: 'order-service', to_name: 'inventory-service', call_count: 1500, error_rate: 0.2, latency_p95: 850, sample_trace_ids: ['t1'], trace_query_ref: 'r' }] }, error: null, meta: {} }) });
      return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({ success: true, data: { results: [] }, error: null, meta: {} }) });
    }) as unknown as typeof globalThis.fetch;

    const r = await runReviewGround([{ entityName: 'order-service', changedFiles: ['OrderService.java'] }], new KhalaClient({ baseUrl: 'http://t:8000' }));
    expect(r.ok).toBe(true);
    if (r.ok) {
      expect(r.pack.tier).toBe(3);
      const gap = r.pack.designObservationGaps?.find((g) => g.flag === 'observed_only' && g.toName === 'inventory-service');
      expect(gap).toBeDefined(); // 제네릭 리뷰가 구조적으로 못 보는 발견
    }
  });

  it('SR3 (T0 정직성): Khala 미가용이면 changedEntities만 + T0 명시', async () => {
    globalThis.fetch = vi.fn().mockRejectedValue(new Error('down')) as unknown as typeof globalThis.fetch;
    const r = await runReviewGround([{ entityName: 'order-service', changedFiles: ['a.ts'] }], new KhalaClient({ baseUrl: 'http://t:8000' }));
    expect(r.ok).toBe(true);
    if (r.ok) {
      expect(r.pack.tier).toBe(0);
      expect(r.pack.tierReason).toMatch(/T0/);
      expect(r.pack.designObservationGaps).toBeUndefined();
    }
  });
});
```

- [ ] **Step 2: 테스트 통과 확인 (구현은 이미 존재)**

Run: `npx vitest run tests/signature-review-scenario.test.ts`
Expected: PASS (Task 4·5 구현으로 통과)

- [ ] **Step 3: 커밋**

```bash
git add tests/signature-review-scenario.test.ts
git commit -m "test: pin v0.6 signature scenarios SR1 (gap moat) / SR3 (T0 honesty)"
```

### Task 12: 전체 검증 + 로드맵 문서 갱신

**Files:**
- Modify: `README.md`, `CLAUDE.md`

- [ ] **Step 1: 전체 스위트 + 타입체크**

Run: `npx vitest run && npx tsc --noEmit`
Expected: 전체 스위트 PASS(기존 + 신규 모두 green), 타입 에러 없음. (실제 케이스 수는 실행으로 확인 — 기존 베이스라인에 본 플랜 신규 케이스가 더해진다.)

- [ ] **Step 2: 로드맵/버전 표기 갱신**

`README.md`: 로드맵 표의 v0.6 행 상태 `Not Started`→`Done`, "현재" 표시 이동.
`CLAUDE.md`: "현재 버전: v0.5"→"v0.6", 버전 목록에 v0.6 그라운디드 코드 리뷰 추가, 로드맵 코드블록 v0.6 ✅ 현재, "프로젝트 구조"의 MCP 도구 "7개"→"8개" 및 신규 파일(`review-grounder.ts`, `core/review-ground.ts`, `grounding-sections.ts`, `khala/tier.ts`) 반영, 테스트 카운트 갱신.

- [ ] **Step 3: 커밋**

```bash
git add README.md CLAUDE.md
git commit -m "docs: mark v0.6 grounded code review done; update structure/counts"
```

---

## Done Criteria
- 전체 vitest green, `tsc --noEmit` clean.
- `probe review:ground` CLI + `probe.groundReview` MCP 동작 (T0 강등 정직성 포함).
- `enrichWithKhala`가 엔티티 스코프 diff로 수렴(전역 diff 버그 제거), 기존 MCP scope 도구 회귀 green.
- SR1(설계-관측 갭 모트)·SR3(T0 정직성) 시그니처 고정.
- Probe는 diff 소스를 의미 분석하지 않음(엣지 추출 없음) — 철학 경계 준수.
