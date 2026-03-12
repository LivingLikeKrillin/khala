import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { KhalaClient, withKhalaFallback } from '../src/khala/client.js';

/**
 * 칼라 클라이언트 테스트
 *
 * 실제 칼라 서버 없이 fetch를 모킹하여 테스트한다.
 */

// fetch 모킹 헬퍼
function mockFetchResponse(data: unknown, ok = true, status = 200) {
  return vi.fn().mockResolvedValue({
    ok,
    status,
    json: () => Promise.resolve({ success: ok, data, error: ok ? null : 'error', meta: {} }),
  });
}

function mockFetchError(error: string) {
  return vi.fn().mockRejectedValue(new Error(error));
}

describe('KhalaClient', () => {
  let originalFetch: typeof globalThis.fetch;

  beforeEach(() => {
    originalFetch = globalThis.fetch;
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
  });

  describe('isAvailable', () => {
    it('서버가 응답하면 true를 반환한다', async () => {
      globalThis.fetch = vi.fn().mockResolvedValue({ ok: true, status: 200 }) as unknown as typeof fetch;
      const client = new KhalaClient({ baseUrl: 'http://test:8000' });

      expect(await client.isAvailable()).toBe(true);
    });

    it('서버가 없으면 false를 반환한다', async () => {
      globalThis.fetch = mockFetchError('ECONNREFUSED') as unknown as typeof fetch;
      const client = new KhalaClient({ baseUrl: 'http://test:8000' });

      expect(await client.isAvailable()).toBe(false);
    });
  });

  describe('search', () => {
    it('검색 결과를 반환한다', async () => {
      const mockData = {
        results: [
          { rid: 'r1', doc_rid: 'd1', doc_title: 'Test', section_path: '1', source_uri: '', snippet: 'hello', score: 0.9, bm25_rank: 1, vector_rank: 2, classification: 'INTERNAL' },
        ],
        graph_findings: null,
        route_used: 'hybrid_only',
        timing_ms: { total: 100 },
      };
      globalThis.fetch = mockFetchResponse(mockData) as unknown as typeof fetch;
      const client = new KhalaClient({ baseUrl: 'http://test:8000' });

      const result = await client.search('test query');

      expect(result).not.toBeNull();
      expect(result!.results).toHaveLength(1);
      expect(result!.results[0].doc_title).toBe('Test');
    });

    it('서버 에러 시 null을 반환한다', async () => {
      globalThis.fetch = mockFetchResponse(null, false, 500) as unknown as typeof fetch;
      const client = new KhalaClient({ baseUrl: 'http://test:8000' });

      const result = await client.search('test');

      expect(result).toBeNull();
    });

    it('네트워크 에러 시 null을 반환한다', async () => {
      globalThis.fetch = mockFetchError('network error') as unknown as typeof fetch;
      const client = new KhalaClient({ baseUrl: 'http://test:8000' });

      const result = await client.search('test');

      expect(result).toBeNull();
    });
  });

  describe('getGraph', () => {
    it('그래프 결과를 반환한다', async () => {
      const mockData = {
        center_entity: { rid: 'ent_payment', name: 'payment-service' },
        edges: [
          { rid: 'e1', edge_type: 'CALLS', from_rid: 'ent_order', from_name: 'order-service', to_rid: 'ent_payment', to_name: 'payment-service', confidence: 0.9, hop: 1, evidence: [] },
        ],
        observed_edges: [],
      };
      globalThis.fetch = mockFetchResponse(mockData) as unknown as typeof fetch;
      const client = new KhalaClient({ baseUrl: 'http://test:8000' });

      const result = await client.getGraph('ent_payment');

      expect(result).not.toBeNull();
      expect(result!.center_entity.name).toBe('payment-service');
      expect(result!.edges).toHaveLength(1);
    });
  });

  describe('getDiff', () => {
    it('diff 결과를 반환한다', async () => {
      const mockData = {
        total_designed_edges: 5,
        total_observed_edges: 3,
        diffs: [
          { flag: 'doc_only', edge_rid: 'e1', observed_edge_rid: null, from_name: 'a', to_name: 'b', edge_type: 'CALLS', detail: 'test', designed_evidence: [], observed_evidence: null },
        ],
        generated_at: '2026-03-11T00:00:00Z',
      };
      globalThis.fetch = mockFetchResponse(mockData) as unknown as typeof fetch;
      const client = new KhalaClient({ baseUrl: 'http://test:8000' });

      const result = await client.getDiff();

      expect(result).not.toBeNull();
      expect(result!.diffs).toHaveLength(1);
      expect(result!.diffs[0].flag).toBe('doc_only');
    });
  });
});

describe('withKhalaFallback', () => {
  it('성공 시 결과를 반환한다', async () => {
    const result = await withKhalaFallback(
      () => Promise.resolve('ok'),
      'fallback',
      'test',
    );
    expect(result).toBe('ok');
  });

  it('실패 시 fallback을 반환한다', async () => {
    const result = await withKhalaFallback(
      () => Promise.reject(new Error('fail')),
      'fallback',
      'test',
    );
    expect(result).toBe('fallback');
  });
});
