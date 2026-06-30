import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { enrichWithNexus, extractServiceNames, fileBelongsToService } from '../src/nexus/context-enricher.js';
import type { DetectedGroup } from '../src/core/scope-analyzer.js';

/**
 * Nexus 컨텍스트 보강 테스트
 */

// 테스트용 응집 그룹
function makeGroups(keys: string[]): DetectedGroup[] {
  return keys.map((key) => ({
    groupName: 'domain-crud',
    cohesionKeyValue: key,
    files: [{ path: `src/service/${key}Service.ts`, role: 'Service' }],
  }));
}

describe('fileBelongsToService', () => {
  it('서비스 디렉터리 세그먼트에 속하면 매칭한다', () => {
    expect(fileBelongsToService('services/order-service/checkout.ts', 'order-service')).toBe(true);
    expect(fileBelongsToService('apps/payment/src/index.ts', 'payment')).toBe(true);
  });

  it('CamelCase 파일명을 kebab 서비스명과 매칭한다', () => {
    expect(fileBelongsToService('src/order/OrderService.java', 'order-service')).toBe(true);
  });

  it('하이픈 제거 substring 과대매칭을 하지 않는다', () => {
    // 'api'가 'rapid'/'therapist' 안에 substring으로 들어가도 매칭하지 않는다
    expect(fileBelongsToService('src/rapid-loader.ts', 'api')).toBe(false);
    expect(fileBelongsToService('src/therapist.ts', 'api')).toBe(false);
    // 'order-service' → 'orderservice'가 무관 파일에 매칭되지 않는다
    expect(fileBelongsToService('src/reorderserviceutil.ts', 'order-service')).toBe(false);
  });

  it('경계가 맞는 compact/세그먼트 형태는 매칭한다', () => {
    expect(fileBelongsToService('src/api/routes.ts', 'api')).toBe(true);
    expect(fileBelongsToService('src/orderservice/index.ts', 'order-service')).toBe(true);
  });
});

describe('extractServiceNames', () => {
  it('cohesionKeyValue에서 서비스명을 추출한다', () => {
    const groups = makeGroups(['Payment', 'Order']);
    const names = extractServiceNames(groups);

    expect(names).toContain('payment');
    expect(names).toContain('payment-service');
    expect(names).toContain('order');
    expect(names).toContain('order-service');
  });

  it('CamelCase를 kebab-case로 변환한다', () => {
    const groups = makeGroups(['UserProfile']);
    const names = extractServiceNames(groups);

    expect(names).toContain('user-profile');
    expect(names).toContain('user-profile-service');
  });

  it('unknown 키는 무시한다', () => {
    const groups = makeGroups(['unknown']);
    const names = extractServiceNames(groups);

    expect(names).toHaveLength(0);
  });

  it('빈 그룹이면 빈 배열을 반환한다', () => {
    expect(extractServiceNames([])).toHaveLength(0);
  });

  it('중복을 제거한다', () => {
    const groups = makeGroups(['payment', 'payment']);
    const names = extractServiceNames(groups);
    const paymentCount = names.filter((n) => n === 'payment').length;

    expect(paymentCount).toBe(1);
  });

  it('-service 접미사가 이미 있으면 중복 추가하지 않는다', () => {
    const groups: DetectedGroup[] = [
      {
        groupName: 'domain-crud',
        cohesionKeyValue: 'payment-service',
        files: [{ path: 'src/PaymentService.ts', role: 'Service' }],
      },
    ];
    const names = extractServiceNames(groups);

    expect(names).toContain('payment-service');
    // "payment-service-service" 가 없어야 함
    expect(names.some((n) => n === 'payment-service-service')).toBe(false);
  });
});

describe('enrichWithNexus', () => {
  let originalFetch: typeof globalThis.fetch;

  beforeEach(() => {
    originalFetch = globalThis.fetch;
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
  });

  it('Nexus 미가용 시 빈 결과와 nexusAvailable=false를 반환한다', async () => {
    // 모든 fetch 호출이 실패하도록
    globalThis.fetch = vi.fn().mockRejectedValue(new Error('ECONNREFUSED')) as unknown as typeof fetch;

    const groups = makeGroups(['Payment']);
    const result = await enrichWithNexus(groups, ['src/PaymentService.ts'], {
      nexusConfig: { baseUrl: 'http://fake:9999', timeoutMs: 100 },
    });

    expect(result.nexusAvailable).toBe(false);
    expect(result.relevantDocs).toHaveLength(0);
    expect(result.impactedServices).toHaveLength(0);
    expect(result.designObservationGaps).toHaveLength(0);
  });

  it('서비스명을 추출할 수 없으면 빈 결과와 nexusAvailable=true를 반환한다', async () => {
    // getStatusProbe 성공 (json 포함)
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: () =>
        Promise.resolve({
          success: true,
          data: { db_connected: true, documents_count: 0, edges_count: 0 },
          error: null,
          meta: {},
        }),
    }) as unknown as typeof fetch;

    const groups = makeGroups(['unknown']);
    const result = await enrichWithNexus(groups, [], {
      nexusConfig: { baseUrl: 'http://fake:8000', timeoutMs: 100 },
    });

    expect(result.nexusAvailable).toBe(true);
    expect(result.relevantDocs).toHaveLength(0);
  });

  it('Nexus가 가용하면 3개 조회를 병렬 수행한다', async () => {
    let callCount = 0;
    globalThis.fetch = vi.fn().mockImplementation((url: string) => {
      callCount++;
      const urlStr = String(url);

      // /status → 가용
      if (urlStr.includes('/status')) {
        return Promise.resolve({
          ok: true,
          status: 200,
          json: () =>
            Promise.resolve({
              success: true,
              data: { db_connected: true, documents_count: 5, edges_count: 3, observed_edges_count: 2 },
              error: null,
              meta: {},
            }),
        });
      }

      // /search → 결과
      if (urlStr.includes('/search')) {
        return Promise.resolve({
          ok: true,
          status: 200,
          json: () =>
            Promise.resolve({
              success: true,
              data: {
                results: [
                  {
                    rid: 'r1',
                    doc_rid: 'd1',
                    doc_title: 'API Guide',
                    section_path: '2.3',
                    source_uri: '',
                    snippet: 'nullable 필드 표기',
                    score: 0.8,
                    bm25_rank: 1,
                    vector_rank: 2,
                    classification: 'INTERNAL',
                  },
                ],
                graph_findings: null,
                route_used: 'hybrid_only',
                timing_ms: {},
              },
              error: null,
              meta: {},
            }),
        });
      }

      // /graph → 404 (엔티티 없음)
      if (urlStr.includes('/graph')) {
        return Promise.resolve({ ok: false, status: 404 });
      }

      // /diff → 빈 결과
      if (urlStr.includes('/diff')) {
        return Promise.resolve({
          ok: true,
          status: 200,
          json: () =>
            Promise.resolve({
              success: true,
              data: { total_designed_edges: 0, total_observed_edges: 0, diffs: [], generated_at: '' },
              error: null,
              meta: {},
            }),
        });
      }

      return Promise.resolve({ ok: false, status: 404 });
    }) as unknown as typeof fetch;

    const groups = makeGroups(['Payment']);
    const result = await enrichWithNexus(groups, ['src/PaymentService.ts'], {
      nexusConfig: { baseUrl: 'http://fake:8000', timeoutMs: 1000 },
    });

    expect(result.nexusAvailable).toBe(true);
    expect(result.relevantDocs).toHaveLength(1);
    expect(result.relevantDocs[0].docTitle).toBe('API Guide');
    // /status + /search + /graph(payment) + /graph(payment-service) + /diff = 최소 4회
    expect(callCount).toBeGreaterThanOrEqual(4);
  });

  it('엔티티 스코프 diff로 갭과 영향 서비스를 투영한다 (수렴 + 평탄화)', async () => {
    globalThis.fetch = vi.fn((url: string) => {
      const u = new URL(url);
      if (u.pathname.startsWith('/status'))
        return Promise.resolve({
          ok: true,
          status: 200,
          json: () =>
            Promise.resolve({
              success: true,
              data: { db_connected: true, documents_count: 1, edges_count: 3, observed_edges_count: 2 },
              error: null,
              meta: {},
            }),
        });
      if (u.pathname.startsWith('/diff')) {
        const hasFilter = u.searchParams.has('entity_filter');
        return Promise.resolve({
          ok: true,
          status: 200,
          json: () =>
            Promise.resolve({
              success: true,
              data: {
                diffs: hasFilter
                  ? [
                      {
                        flag: 'observed_only',
                        from_name: 'order-service',
                        to_name: 'inventory-service',
                        edge_type: 'CALLS_OBSERVED',
                        detail: 'd',
                        designed_evidence: [],
                        observed_evidence: { sample_trace_ids: ['t'], trace_query_ref: 'r' },
                      },
                    ]
                  : [],
              },
              error: null,
              meta: {},
            }),
        });
      }
      if (u.pathname.startsWith('/graph'))
        return Promise.resolve({
          ok: true,
          status: 200,
          json: () =>
            Promise.resolve({
              success: true,
              data: {
                center_entity: { rid: 'e', name: 'order-service' },
                edges: [
                  {
                    rid: 'e1',
                    edge_type: 'CALLS',
                    from_name: 'order-service',
                    to_name: 'inventory-service',
                    from_rid: 'a',
                    to_rid: 'b',
                    confidence: 0.9,
                    hop: 1,
                    evidence: [],
                  },
                ],
                observed_edges: [],
              },
              error: null,
              meta: {},
            }),
        });
      return Promise.resolve({
        ok: true,
        status: 200,
        json: () => Promise.resolve({ success: true, data: { results: [] }, error: null, meta: {} }),
      });
    }) as unknown as typeof globalThis.fetch;

    const groups = makeGroups(['Order']);
    const result = await enrichWithNexus(groups, ['src/order/OrderService.java'], {
      nexusConfig: { baseUrl: 'http://t:8000' },
    });
    expect(result.nexusAvailable).toBe(true);
    expect(result.designObservationGaps.some((g) => g.flag === 'observed_only')).toBe(true);
    expect(result.impactedServices.some((s) => s.name === 'inventory-service')).toBe(true);
  });
});
