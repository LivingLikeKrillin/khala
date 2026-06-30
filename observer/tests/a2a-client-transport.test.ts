import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { NexusClient } from '../src/nexus/client.js';
import { mapTaskToAnswerResult } from '../src/nexus/a2a/mapping.js';
import type { A2ATask } from '../src/nexus/a2a/types.js';

/**
 * searchAnswer 전송 전환 + 파리티 테스트 (Phase 1 → SPEC §17)
 *
 * A2A가 기본 전송이다(SPEC §17). 설정/환경변수 없이 → A2A retrieve_grounded.
 * HTTP /search/answer로 opt-out: config.transport='http' 또는 OBSERVER_NEXUS_TRANSPORT=http.
 */

const BASE = 'http://test:8000';
const CARD_PATH = '/.well-known/agent-card.json';

const HTTP_ANSWER = {
  answer: '결제 서비스는 payment.events 토픽을 발행합니다.',
  evidence_snippets: [
    {
      chunk_rid: 'chunk_1',
      doc_title: 'Payment',
      section_path: 'Topics',
      source_uri: 'git://docs/payment.md',
      text: 'payment.events 발행',
      score: 0.9,
    },
  ],
  graph_findings: null,
  provenance: [{ doc_rid: 'd1', source_uri: 'git://docs/payment.md', source_version: 'v2' }],
  route_used: 'graph',
  timing_ms: { total: 120 },
};

function a2aTaskForSameAnswer(): A2ATask {
  return {
    id: 't1',
    status: { state: 'completed' },
    artifacts: [
      {
        parts: [
          { kind: 'text', text: HTTP_ANSWER.answer },
          {
            kind: 'data',
            data: {
              evidence: [
                {
                  doc_title: 'Payment',
                  section_path: 'Topics',
                  text: 'payment.events 발행',
                  score: 0.9,
                  source_uri: 'git://docs/payment.md',
                },
              ],
              provenance: [{ source_uri: 'git://docs/payment.md', source_version: 'v2', doc_rid: 'd1' }],
              confidence: 'LOW',
              route: 'graph',
              policy: { tenant: 'acme', clearance_applied: 'INTERNAL' },
            },
          },
        ],
      },
    ],
  };
}

function cardJson() {
  return {
    name: 'Nexus',
    url: `${BASE}/a2a`,
    skills: [{ id: 'retrieve_grounded' }],
    capabilities: { streaming: false },
  };
}

/** card GET / a2a POST / http /search/answer를 URL로 구분하는 fetch 모킹. */
function routedFetch(rpcBody: unknown) {
  return vi.fn((url: string) => {
    const u = String(url);
    if (u.includes(CARD_PATH)) {
      return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(cardJson()) });
    }
    if (u.endsWith('/a2a')) {
      return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(rpcBody) });
    }
    // HTTP /search/answer
    return Promise.resolve({
      ok: true,
      status: 200,
      json: () => Promise.resolve({ success: true, data: HTTP_ANSWER, error: null, meta: {} }),
    });
  });
}

describe('NexusClient.searchAnswer transport switch', () => {
  let originalFetch: typeof globalThis.fetch;
  beforeEach(() => {
    originalFetch = globalThis.fetch;
  });
  afterEach(() => {
    globalThis.fetch = originalFetch;
    delete process.env.OBSERVER_NEXUS_TRANSPORT;
    delete process.env.OBSERVER_NEXUS_TOKEN;
  });

  it('기본(설정 없음)은 A2A retrieve_grounded를 사용한다', async () => {
    const fetchMock = routedFetch({ jsonrpc: '2.0', id: '1', result: a2aTaskForSameAnswer() });
    globalThis.fetch = fetchMock as unknown as typeof fetch;

    const client = new NexusClient({ baseUrl: BASE, nexusToken: 'tok' });
    const result = await client.searchAnswer('결제 토픽?');

    expect(result).not.toBeNull();
    expect(result!.route_used).toBe('graph');
    const urls = fetchMock.mock.calls.map((c) => String(c[0]));
    expect(urls.some((u) => u.includes(CARD_PATH))).toBe(true);
    expect(urls.some((u) => u.endsWith('/a2a'))).toBe(true);
    expect(urls.some((u) => u.includes('/search/answer'))).toBe(false);
  });

  it('config.transport="http"이면 POST /search/answer로 opt-out한다', async () => {
    const fetchMock = routedFetch({ jsonrpc: '2.0', id: '1', result: a2aTaskForSameAnswer() });
    globalThis.fetch = fetchMock as unknown as typeof fetch;

    const client = new NexusClient({ baseUrl: BASE, transport: 'http' });
    const result = await client.searchAnswer('결제 토픽?');

    expect(result).not.toBeNull();
    expect(result!.answer).toBe(HTTP_ANSWER.answer);
    const url = String(fetchMock.mock.calls[0]![0]);
    expect(url).toContain('/search/answer');
    expect(url).not.toContain(CARD_PATH);
  });

  it('OBSERVER_NEXUS_TRANSPORT=http 환경변수로 HTTP로 opt-out한다', async () => {
    process.env.OBSERVER_NEXUS_TRANSPORT = 'http';
    const fetchMock = routedFetch({ jsonrpc: '2.0', id: '1', result: a2aTaskForSameAnswer() });
    globalThis.fetch = fetchMock as unknown as typeof fetch;

    const client = new NexusClient({ baseUrl: BASE });
    const result = await client.searchAnswer('q');

    expect(result).not.toBeNull();
    const urls = fetchMock.mock.calls.map((c) => String(c[0]));
    expect(urls.some((u) => u.includes('/search/answer'))).toBe(true);
    expect(urls.some((u) => u.endsWith('/a2a'))).toBe(false);
  });

  it('config.transport="a2a"이면 A2A retrieve_grounded를 사용한다 (명시)', async () => {
    const fetchMock = routedFetch({ jsonrpc: '2.0', id: '1', result: a2aTaskForSameAnswer() });
    globalThis.fetch = fetchMock as unknown as typeof fetch;

    const client = new NexusClient({ baseUrl: BASE, transport: 'a2a', nexusToken: 'tok' });
    const result = await client.searchAnswer('결제 토픽?');

    expect(result).not.toBeNull();
    expect(result!.route_used).toBe('graph');
    const urls = fetchMock.mock.calls.map((c) => String(c[0]));
    expect(urls.some((u) => u.endsWith('/a2a'))).toBe(true);
    expect(urls.some((u) => u.includes('/search/answer'))).toBe(false);
  });

  it('A2A 경로 실패 시 null을 반환한다 (graceful degradation parity)', async () => {
    globalThis.fetch = vi.fn().mockRejectedValue(new Error('ECONNREFUSED')) as unknown as typeof fetch;
    const client = new NexusClient({ baseUrl: BASE, transport: 'a2a', nexusToken: 'tok' });
    expect(await client.searchAnswer('q')).toBeNull();
  });

  it('파리티: 같은 답변을 HTTP와 A2A가 소비 필드에서 동일하게 산출한다', () => {
    const httpResult = HTTP_ANSWER;
    const a2aResult = mapTaskToAnswerResult(a2aTaskForSameAnswer())!;

    // 소비 필드: answer / route_used / provenance / evidence 투영(공통 필드)
    expect(a2aResult.answer).toBe(httpResult.answer);
    expect(a2aResult.route_used).toBe(httpResult.route_used);
    expect(a2aResult.provenance).toEqual(httpResult.provenance);

    const project = (e: unknown) => {
      const s = e as { doc_title: string; section_path: string; text: string; score: number; source_uri: string };
      return {
        doc_title: s.doc_title,
        section_path: s.section_path,
        text: s.text,
        score: s.score,
        source_uri: s.source_uri,
      };
    };
    expect(a2aResult.evidence_snippets.map(project)).toEqual(httpResult.evidence_snippets.map(project));
  });
});
