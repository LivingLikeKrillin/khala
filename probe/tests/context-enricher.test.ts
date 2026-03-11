import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { enrichWithKhala, extractServiceNames } from '../src/khala/context-enricher.js';
import type { DetectedGroup } from '../src/core/scope-analyzer.js';

/**
 * 칼라 컨텍스트 보강 테스트
 */

// 테스트용 응집 그룹
function makeGroups(keys: string[]): DetectedGroup[] {
  return keys.map((key) => ({
    groupName: 'domain-crud',
    cohesionKeyValue: key,
    files: [{ path: `src/service/${key}Service.ts`, role: 'Service' }],
  }));
}

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
    const groups: DetectedGroup[] = [{
      groupName: 'domain-crud',
      cohesionKeyValue: 'payment-service',
      files: [{ path: 'src/PaymentService.ts', role: 'Service' }],
    }];
    const names = extractServiceNames(groups);

    expect(names).toContain('payment-service');
    // "payment-service-service" 가 없어야 함
    expect(names.some((n) => n === 'payment-service-service')).toBe(false);
  });
});

describe('enrichWithKhala', () => {
  let originalFetch: typeof globalThis.fetch;

  beforeEach(() => {
    originalFetch = globalThis.fetch;
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
  });

  it('칼라 미가용 시 빈 결과와 khalaAvailable=false를 반환한다', async () => {
    // 모든 fetch 호출이 실패하도록
    globalThis.fetch = vi.fn().mockRejectedValue(new Error('ECONNREFUSED')) as unknown as typeof fetch;

    const groups = makeGroups(['Payment']);
    const result = await enrichWithKhala(groups, ['src/PaymentService.ts'], {
      khalaConfig: { baseUrl: 'http://fake:9999', timeoutMs: 100 },
    });

    expect(result.khalaAvailable).toBe(false);
    expect(result.relevantDocs).toHaveLength(0);
    expect(result.impactedServices).toHaveLength(0);
    expect(result.designObservationGaps).toHaveLength(0);
  });

  it('서비스명을 추출할 수 없으면 빈 결과와 khalaAvailable=true를 반환한다', async () => {
    // isAvailable만 성공
    globalThis.fetch = vi.fn().mockResolvedValue({ ok: true, status: 200 }) as unknown as typeof fetch;

    const groups = makeGroups(['unknown']);
    const result = await enrichWithKhala(groups, [], {
      khalaConfig: { baseUrl: 'http://fake:8000', timeoutMs: 100 },
    });

    expect(result.khalaAvailable).toBe(true);
    expect(result.relevantDocs).toHaveLength(0);
  });

  it('칼라가 가용하면 3개 조회를 병렬 수행한다', async () => {
    let callCount = 0;
    globalThis.fetch = vi.fn().mockImplementation((url: string) => {
      callCount++;
      const urlStr = String(url);

      // /status → 가용
      if (urlStr.includes('/status')) {
        return Promise.resolve({ ok: true, status: 200 });
      }

      // /search → 결과
      if (urlStr.includes('/search')) {
        return Promise.resolve({
          ok: true,
          status: 200,
          json: () => Promise.resolve({
            success: true,
            data: {
              results: [{ rid: 'r1', doc_rid: 'd1', doc_title: 'API Guide', section_path: '2.3', source_uri: '', snippet: 'nullable 필드 표기', score: 0.8, bm25_rank: 1, vector_rank: 2, classification: 'INTERNAL' }],
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
          json: () => Promise.resolve({
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
    const result = await enrichWithKhala(groups, ['src/PaymentService.ts'], {
      khalaConfig: { baseUrl: 'http://fake:8000', timeoutMs: 1000 },
    });

    expect(result.khalaAvailable).toBe(true);
    expect(result.relevantDocs).toHaveLength(1);
    expect(result.relevantDocs[0].docTitle).toBe('API Guide');
    // /status + /search + /graph(payment) + /graph(payment-service) + /diff = 최소 4회
    expect(callCount).toBeGreaterThanOrEqual(4);
  });
});
