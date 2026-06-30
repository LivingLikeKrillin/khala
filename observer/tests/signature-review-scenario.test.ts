import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { runReviewGround } from '../src/core/review-ground.js';
import { NexusClient } from '../src/nexus/client.js';

describe('시그니처 리뷰 시나리오', () => {
  let orig: typeof globalThis.fetch;
  beforeEach(() => {
    orig = globalThis.fetch;
  });
  afterEach(() => {
    globalThis.fetch = orig;
  });

  it('SR1 (T3 모트): order-service 변경이 observed_only order→inventory 갭을 드러낸다', async () => {
    globalThis.fetch = vi.fn((url: string) => {
      const u = new URL(url);
      if (u.pathname.startsWith('/status'))
        return Promise.resolve({
          ok: true,
          status: 200,
          json: () =>
            Promise.resolve({
              success: true,
              data: { db_connected: true, edges_count: 5, observed_edges_count: 3 },
              error: null,
              meta: {},
            }),
        });
      if (u.pathname.startsWith('/diff'))
        return Promise.resolve({
          ok: true,
          status: 200,
          json: () =>
            Promise.resolve({
              success: true,
              data: {
                diffs: [
                  {
                    flag: 'observed_only',
                    from_name: 'order-service',
                    to_name: 'inventory-service',
                    edge_type: 'CALLS_OBSERVED',
                    detail: '설계 문서에 없음',
                    designed_evidence: [],
                    observed_evidence: { sample_trace_ids: ['t1'], trace_query_ref: 'r' },
                  },
                ],
              },
              error: null,
              meta: {},
            }),
        });
      if (u.pathname.startsWith('/graph'))
        return Promise.resolve({
          ok: true,
          status: 200,
          json: () =>
            Promise.resolve({
              success: true,
              data: {
                center_entity: { rid: 'e', name: 'order-service' },
                edges: [],
                observed_edges: [
                  {
                    rid: 'o1',
                    edge_type: 'CALLS_OBSERVED',
                    from_name: 'order-service',
                    to_name: 'inventory-service',
                    call_count: 1500,
                    error_rate: 0.2,
                    latency_p95: 850,
                    sample_trace_ids: ['t1'],
                    trace_query_ref: 'r',
                  },
                ],
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

    const r = await runReviewGround(
      [{ entityName: 'order-service', changedFiles: ['OrderService.java'] }],
      new NexusClient({ baseUrl: 'http://t:8000' }),
    );
    expect(r.ok).toBe(true);
    if (r.ok) {
      expect(r.pack.tier).toBe(3);
      const gap = r.pack.designObservationGaps?.find(
        (g) => g.flag === 'observed_only' && g.toName === 'inventory-service',
      );
      expect(gap).toBeDefined();
    }
  });

  it('SR2 (T1 승인 스펙 정합): payment 변경에 대해 승인 스펙을 specRefs로 제시한다', async () => {
    // 문서만 있고(T1) 엣지 0 — /search가 승인 스펙(제목에 spec 마커)을 반환
    globalThis.fetch = vi.fn((url: string) => {
      const u = new URL(url);
      if (u.pathname.startsWith('/status'))
        return Promise.resolve({
          ok: true,
          status: 200,
          json: () =>
            Promise.resolve({
              success: true,
              data: { db_connected: true, documents_count: 4, edges_count: 0 },
              error: null,
              meta: {},
            }),
        });
      if (u.pathname.startsWith('/search'))
        return Promise.resolve({
          ok: true,
          status: 200,
          json: () =>
            Promise.resolve({
              success: true,
              data: {
                results: [
                  {
                    doc_title: 'Payment Idempotency Spec',
                    section_path: '2.3',
                    snippet: '멱등 키 필수',
                    score: 0.91,
                    classification: 'INTERNAL',
                  },
                ],
              },
              error: null,
              meta: {},
            }),
        });
      return Promise.resolve({
        ok: true,
        status: 200,
        json: () =>
          Promise.resolve({
            success: true,
            data: { diffs: [], center_entity: { rid: 'e', name: 'payment-service' }, edges: [], observed_edges: [] },
            error: null,
            meta: {},
          }),
      });
    }) as unknown as typeof globalThis.fetch;

    const r = await runReviewGround(
      [{ entityName: 'payment-service', changedFiles: ['PaymentRetry.java'] }],
      new NexusClient({ baseUrl: 'http://t:8000' }),
    );
    expect(r.ok).toBe(true);
    if (r.ok) {
      expect(r.pack.tier).toBe(1);
      const spec = r.pack.specRefs?.find((s) => s.docTitle === 'Payment Idempotency Spec');
      expect(spec).toBeDefined(); // diff↔스펙 대조용 참조를 Claude에 제시
    }
  });

  it('SR3 (T0 정직성): Nexus 미가용이면 changedEntities만 + T0 명시', async () => {
    globalThis.fetch = vi.fn().mockRejectedValue(new Error('down')) as unknown as typeof globalThis.fetch;
    const r = await runReviewGround(
      [{ entityName: 'order-service', changedFiles: ['a.ts'] }],
      new NexusClient({ baseUrl: 'http://t:8000' }),
    );
    expect(r.ok).toBe(true);
    if (r.ok) {
      expect(r.pack.tier).toBe(0);
      expect(r.pack.tierReason).toMatch(/T0/);
      expect(r.pack.designObservationGaps).toBeUndefined();
    }
  });
});
