import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { localizeError } from '../src/nexus/error-localizer.js';
import { NexusClient } from '../src/nexus/client.js';

describe('시그니처 시나리오 S1 — observed_only 갭 데이터패스', () => {
  let originalFetch: typeof globalThis.fetch;
  beforeEach(() => { originalFetch = globalThis.fetch; });
  afterEach(() => { globalThis.fetch = originalFetch; });

  it('에러→국소화→getDiff(entityFilter)로 order→inventory observed_only 갭을 끌어온다', async () => {
    const suspects = localizeError({
      signal: 'NPE\n\tat com.shop.order.OrderService.checkout(OrderService.java:88)',
      kind: 'stacktrace',
    });
    expect(suspects[0]!.entityName).toBe('order-service');

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

    const client = new NexusClient({ baseUrl: 'http://test:8000' });
    const diff = await client.getDiff({ entityFilter: suspects[0]!.entityName });

    const gap = diff?.diffs.find((d) => d.flag === 'observed_only');
    expect(gap).toBeDefined();
    expect(gap!.from_name).toBe('order-service');
    expect(gap!.to_name).toBe('inventory-service');
  });
});
