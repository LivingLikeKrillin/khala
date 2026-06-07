import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { groundReview, partitionDocs } from '../src/nexus/review-grounder.js';
import { NexusClient } from '../src/nexus/client.js';
import type { RelevantDoc } from '../src/nexus/types.js';

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

    const client = new NexusClient({ baseUrl: 'http://t:8000' });
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
    const client = new NexusClient({ baseUrl: 'http://t:8000' });
    const pack = await groundReview(client, [{ entityName: 'order-service', changedFiles: [] }], { tier: 3 });
    expect(pack.caveats.some((c) => c.includes('승인 스펙') || c.toLowerCase().includes('spec'))).toBe(true);
    expect(pack.applicableGuidelines?.some((g) => g.docTitle === '결제 규정')).toBe(true);
  });

  it('Archon 미연동 caveat를 항상 남긴다', async () => {
    globalThis.fetch = mockByPath({ '/search': { results: [] }, '/graph': { center_entity: { rid: 'e', name: 'x' }, edges: [], observed_edges: [] }, '/diff': { diffs: [] } }) as unknown as typeof globalThis.fetch;
    const client = new NexusClient({ baseUrl: 'http://t:8000' });
    const pack = await groundReview(client, [{ entityName: 'x', changedFiles: [] }], { tier: 2 });
    expect(pack.caveats.some((c) => c.includes('Archon'))).toBe(true);
  });
});
