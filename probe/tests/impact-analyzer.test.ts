import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { analyzeImpact } from '../src/khala/impact-analyzer.js';
import { KhalaClient } from '../src/khala/client.js';

/**
 * 칼라 영향 분석 테스트
 */

// fetch 모킹 헬퍼
function mockGraphResponse(edges: unknown[], observedEdges: unknown[] = []) {
  return {
    ok: true,
    status: 200,
    json: () => Promise.resolve({
      success: true,
      data: {
        center_entity: { rid: 'ent_test', name: 'test-service' },
        edges,
        observed_edges: observedEdges,
      },
      error: null,
      meta: {},
    }),
  };
}

describe('analyzeImpact', () => {
  let originalFetch: typeof globalThis.fetch;

  beforeEach(() => {
    originalFetch = globalThis.fetch;
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
  });

  it('서비스명이 없으면 빈 결과를 반환한다', async () => {
    const client = new KhalaClient({ baseUrl: 'http://test:8000' });
    const result = await analyzeImpact(client, []);

    expect(result.severity).toBe('none');
    expect(result.directImpact).toHaveLength(0);
  });

  it('그래프에 이웃이 있으면 영향 서비스를 반환한다', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue(
      mockGraphResponse([
        {
          rid: 'e1', edge_type: 'CALLS',
          from_rid: 'ent_order', from_name: 'order-service',
          to_rid: 'ent_payment', to_name: 'payment-service',
          confidence: 0.9, hop: 1, evidence: [],
        },
      ]),
    ) as unknown as typeof fetch;

    const client = new KhalaClient({ baseUrl: 'http://test:8000' });
    const result = await analyzeImpact(client, ['payment']);

    expect(result.changedServices).toContain('payment');
    expect(result.directImpact.length).toBeGreaterThanOrEqual(1);
    expect(result.directImpact.some((s) => s.name === 'order-service')).toBe(true);
    expect(result.severity).not.toBe('none');
  });

  it('관측 데이터로 영향 서비스를 보강한다', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue(
      mockGraphResponse(
        [{
          rid: 'e1', edge_type: 'CALLS',
          from_rid: 'ent_order', from_name: 'order-service',
          to_rid: 'ent_payment', to_name: 'payment-service',
          confidence: 0.9, hop: 1, evidence: [],
        }],
        [{
          rid: 'o1', edge_type: 'CALLS_OBSERVED',
          from_name: 'order-service', to_name: 'payment-service',
          call_count: 1200, error_rate: 0.001, latency_p95: 150,
          sample_trace_ids: [], trace_query_ref: '',
        }],
      ),
    ) as unknown as typeof fetch;

    const client = new KhalaClient({ baseUrl: 'http://test:8000' });
    const result = await analyzeImpact(client, ['payment']);

    const orderImpact = result.directImpact.find((s) => s.name === 'order-service');
    expect(orderImpact?.observed).toBeDefined();
    expect(orderImpact?.observed?.callCount).toBe(1200);
  });

  it('3개 이상 서비스 영향 시 medium 심각도를 반환한다', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue(
      mockGraphResponse([
        { rid: 'e1', edge_type: 'CALLS', from_rid: 'ent_a', from_name: 'a-service', to_rid: 'ent_payment', to_name: 'payment-service', confidence: 0.9, hop: 1, evidence: [] },
        { rid: 'e2', edge_type: 'CALLS', from_rid: 'ent_b', from_name: 'b-service', to_rid: 'ent_payment', to_name: 'payment-service', confidence: 0.8, hop: 1, evidence: [] },
        { rid: 'e3', edge_type: 'CALLS', from_rid: 'ent_c', from_name: 'c-service', to_rid: 'ent_payment', to_name: 'payment-service', confidence: 0.7, hop: 1, evidence: [] },
      ]),
    ) as unknown as typeof fetch;

    const client = new KhalaClient({ baseUrl: 'http://test:8000' });
    const result = await analyzeImpact(client, ['payment']);

    expect(result.directImpact.length).toBeGreaterThanOrEqual(3);
    expect(result.severity).toBe('medium');
  });

  it('그래프 조회 실패 시 빈 결과를 반환한다', async () => {
    globalThis.fetch = vi.fn().mockRejectedValue(new Error('network error')) as unknown as typeof fetch;

    const client = new KhalaClient({ baseUrl: 'http://test:8000' });
    const result = await analyzeImpact(client, ['payment']);

    expect(result.changedServices).toContain('payment');
    expect(result.directImpact).toHaveLength(0);
    expect(result.severity).toBe('none');
  });

  it('높은 error rate + 3개 이상 서비스면 high 심각도를 반환한다', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue(
      mockGraphResponse(
        [
          { rid: 'e1', edge_type: 'CALLS', from_rid: 'ent_a', from_name: 'a-service', to_rid: 'ent_payment', to_name: 'payment-service', confidence: 0.9, hop: 1, evidence: [] },
          { rid: 'e2', edge_type: 'CALLS', from_rid: 'ent_b', from_name: 'b-service', to_rid: 'ent_payment', to_name: 'payment-service', confidence: 0.8, hop: 1, evidence: [] },
          { rid: 'e3', edge_type: 'CALLS', from_rid: 'ent_c', from_name: 'c-service', to_rid: 'ent_payment', to_name: 'payment-service', confidence: 0.7, hop: 1, evidence: [] },
        ],
        [
          { rid: 'o1', edge_type: 'CALLS_OBSERVED', from_name: 'a-service', to_name: 'payment-service', call_count: 100, error_rate: 0.1, latency_p95: 500, sample_trace_ids: [], trace_query_ref: '' },
        ],
      ),
    ) as unknown as typeof fetch;

    const client = new KhalaClient({ baseUrl: 'http://test:8000' });
    const result = await analyzeImpact(client, ['payment']);

    expect(result.severity).toBe('high');
  });
});
