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
        edges: [{ rid: 'e1', edge_type: 'CALLS', from_name: 'order-service', to_name: 'inventory-service', from_rid: 'a', to_rid: 'b', confidence: 0.9, hop: 1, evidence: [] }],
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

  it('search 실패 시 지식 그라운딩 caveat를 남긴다', async () => {
    globalThis.fetch = vi.fn((url: string) =>
      String(url).includes('/search')
        ? Promise.reject(new Error('500'))
        : Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({ success: true, data: { diffs: [] }, error: null, meta: {} }) }),
    ) as unknown as typeof globalThis.fetch;
    const client = new KhalaClient({ baseUrl: 'http://test:8000' });
    const pack = await groundTroubleshooting(
      client, [{ entityName: 'order-service', evidence: [], confidence: 0.9 }],
      { signal: 'NPE', tier: 1 },
    );
    expect(pack.caveats.some((c) => c.includes('지식') || c.toLowerCase().includes('search'))).toBe(true);
  });

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
});
