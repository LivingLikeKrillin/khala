import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { fetchEntityGaps, searchDocs } from '../src/nexus/grounding-sections.js';
import { NexusClient } from '../src/nexus/client.js';

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
    const gaps = await fetchEntityGaps(new NexusClient({ baseUrl: 'http://t:8000' }), ['order-service']);
    expect(gaps[0]!.flag).toBe('doc_only');
  });

  it('fetchEntityGaps는 모든 diff가 null이면 throw한다', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({ ok: false, status: 500, json: () => Promise.resolve({ success: false, error: 'e' }) }) as unknown as typeof globalThis.fetch;
    await expect(fetchEntityGaps(new NexusClient({ baseUrl: 'http://t:8000' }), ['x'])).rejects.toThrow();
  });

  it('searchDocs는 검색 히트를 RelevantDoc[]로 매핑한다', async () => {
    globalThis.fetch = mockByPath({ '/search': { results: [
      { doc_title: 'T', section_path: '1', snippet: 's', score: 0.9, classification: 'INTERNAL' },
    ] } }) as unknown as typeof globalThis.fetch;
    const docs = await searchDocs(new NexusClient({ baseUrl: 'http://t:8000' }), 'q', 5);
    expect(docs?.[0]!.docTitle).toBe('T');
  });
});
