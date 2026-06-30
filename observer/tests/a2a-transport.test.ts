import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { A2ANexusTransport } from '../src/nexus/a2a/transport.js';

/**
 * A2A 클라이언트 전송 테스트 (Phase 1, SPEC §5.3)
 *
 * 실제 Nexus 없이 fetch를 라우팅 모킹한다. card 발견 → message/send → 매핑.
 * 모든 실패는 null로 강등한다(Nexus 선택성).
 */

const BASE = 'http://test:8000';
const CARD_PATH = '/.well-known/agent-card.json';

function cardJson() {
  return {
    name: 'Nexus',
    url: `${BASE}/a2a`,
    version: '0.1.0-spike',
    skills: [{ id: 'retrieve_grounded', name: 'Grounded knowledge retrieval' }],
    capabilities: { streaming: false },
  };
}

function groundedTaskResult() {
  return {
    id: 't1',
    contextId: 'c1',
    kind: 'task',
    status: { state: 'completed' },
    artifacts: [
      {
        name: 'grounded_answer',
        parts: [
          { kind: 'text', text: '답변 텍스트' },
          {
            kind: 'data',
            data: {
              evidence: [{ doc_title: 'D', section_path: 'S', text: 't', score: 0.9, source_uri: 'git://d.md' }],
              provenance: [{ source_uri: 'git://d.md', source_version: 'v1', doc_rid: 'd' }],
              confidence: 'LOW',
              route: 'vector',
              policy: { tenant: 'acme', clearance_applied: 'INTERNAL' },
            },
          },
        ],
      },
    ],
  };
}

/** URL로 라우팅하는 fetch 모킹. card GET과 a2a POST를 구분해 응답을 돌려준다. */
function routedFetch(handlers: {
  card?: () => { ok: boolean; status?: number; body: unknown };
  rpc?: (init: RequestInit) => { ok: boolean; status?: number; body: unknown };
}) {
  return vi.fn((url: string, init?: RequestInit) => {
    const u = String(url);
    if (u.includes(CARD_PATH)) {
      const r = handlers.card?.() ?? { ok: true, body: cardJson() };
      return Promise.resolve({ ok: r.ok, status: r.status ?? (r.ok ? 200 : 500), json: () => Promise.resolve(r.body) });
    }
    const r = handlers.rpc?.(init ?? {}) ?? {
      ok: true,
      body: { jsonrpc: '2.0', id: '1', result: groundedTaskResult() },
    };
    return Promise.resolve({ ok: r.ok, status: r.status ?? (r.ok ? 200 : 500), json: () => Promise.resolve(r.body) });
  });
}

describe('A2ANexusTransport', () => {
  let originalFetch: typeof globalThis.fetch;
  beforeEach(() => {
    originalFetch = globalThis.fetch;
  });
  afterEach(() => {
    globalThis.fetch = originalFetch;
  });

  it('카드를 발견하고 message/send로 grounded 답변을 받아 매핑한다', async () => {
    let rpcInit: RequestInit = {};
    const fetchMock = routedFetch({
      rpc: (init) => {
        rpcInit = init;
        return { ok: true, body: { jsonrpc: '2.0', id: '1', result: groundedTaskResult() } };
      },
    });
    globalThis.fetch = fetchMock as unknown as typeof fetch;

    const transport = new A2ANexusTransport({ baseUrl: BASE, token: 'tok', timeoutMs: 5000 });
    const result = await transport.retrieveGrounded('결제 토픽?');

    expect(result).not.toBeNull();
    expect(result!.answer).toBe('답변 텍스트');
    expect(result!.route_used).toBe('vector');

    // card GET + a2a POST
    expect(fetchMock).toHaveBeenCalledTimes(2);
    const rpcUrl = String(fetchMock.mock.calls[1]![0]);
    expect(rpcUrl).toBe(`${BASE}/a2a`);
    // bearer 토큰 + message/send + 쿼리
    const headers = rpcInit.headers as Record<string, string>;
    expect(headers.Authorization).toBe('Bearer tok');
    const body = JSON.parse(String(rpcInit.body));
    expect(body.method).toBe('message/send');
    expect(body.params.message.parts[0].text).toBe('결제 토픽?');
  });

  it('토큰이 없으면 Authorization 헤더를 보내지 않는다', async () => {
    let rpcInit: RequestInit = {};
    globalThis.fetch = routedFetch({
      rpc: (init) => {
        rpcInit = init;
        return { ok: true, body: { jsonrpc: '2.0', id: '1', result: groundedTaskResult() } };
      },
    }) as unknown as typeof fetch;

    const transport = new A2ANexusTransport({ baseUrl: BASE, timeoutMs: 5000 });
    await transport.retrieveGrounded('q');
    const headers = (rpcInit.headers as Record<string, string>) ?? {};
    expect(headers.Authorization).toBeUndefined();
  });

  it('카드 발견 실패(HTTP 오류) 시 null, RPC를 호출하지 않는다', async () => {
    const fetchMock = routedFetch({ card: () => ({ ok: false, status: 404, body: {} }) });
    globalThis.fetch = fetchMock as unknown as typeof fetch;

    const transport = new A2ANexusTransport({ baseUrl: BASE, token: 'tok', timeoutMs: 5000 });
    expect(await transport.retrieveGrounded('q')).toBeNull();
    expect(fetchMock).toHaveBeenCalledTimes(1); // card만 시도
  });

  it('카드에 retrieve_grounded skill이 없으면 null', async () => {
    globalThis.fetch = routedFetch({
      card: () => ({ ok: true, body: { name: 'Nexus', url: `${BASE}/a2a`, skills: [{ id: 'other' }] } }),
    }) as unknown as typeof fetch;

    const transport = new A2ANexusTransport({ baseUrl: BASE, token: 'tok', timeoutMs: 5000 });
    expect(await transport.retrieveGrounded('q')).toBeNull();
  });

  it('JSON-RPC error 응답 시 null', async () => {
    globalThis.fetch = routedFetch({
      rpc: () => ({ ok: true, body: { jsonrpc: '2.0', id: '1', error: { code: -32001, message: 'unauthorized' } } }),
    }) as unknown as typeof fetch;

    const transport = new A2ANexusTransport({ baseUrl: BASE, timeoutMs: 5000 });
    expect(await transport.retrieveGrounded('q')).toBeNull();
  });

  it('401(HTTP) 응답 시 null (default-deny graceful)', async () => {
    globalThis.fetch = routedFetch({
      rpc: () => ({ ok: false, status: 401, body: { error: { code: -32001, message: 'unauthorized' } } }),
    }) as unknown as typeof fetch;

    const transport = new A2ANexusTransport({ baseUrl: BASE, timeoutMs: 5000 });
    expect(await transport.retrieveGrounded('q')).toBeNull();
  });

  it('failed task는 null로 매핑된다', async () => {
    globalThis.fetch = routedFetch({
      rpc: () => ({
        ok: true,
        body: {
          jsonrpc: '2.0',
          id: '1',
          result: {
            id: 't',
            status: { state: 'failed' },
            artifacts: [{ parts: [{ kind: 'data', data: { evidence: [] } }] }],
          },
        },
      }),
    }) as unknown as typeof fetch;

    const transport = new A2ANexusTransport({ baseUrl: BASE, timeoutMs: 5000 });
    expect(await transport.retrieveGrounded('q')).toBeNull();
  });

  it('네트워크 에러 시 null (graceful degradation)', async () => {
    globalThis.fetch = vi.fn().mockRejectedValue(new Error('ECONNREFUSED')) as unknown as typeof fetch;
    const transport = new A2ANexusTransport({ baseUrl: BASE, token: 'tok', timeoutMs: 5000 });
    expect(await transport.retrieveGrounded('q')).toBeNull();
  });

  it('카드를 인스턴스 단위로 캐시한다 (두 번째 호출은 card GET을 재사용)', async () => {
    const fetchMock = routedFetch({});
    globalThis.fetch = fetchMock as unknown as typeof fetch;

    const transport = new A2ANexusTransport({ baseUrl: BASE, token: 'tok', timeoutMs: 5000 });
    await transport.retrieveGrounded('q1');
    await transport.retrieveGrounded('q2');

    // card GET 1회 + RPC 2회 = 3회 (card 캐시됨)
    expect(fetchMock).toHaveBeenCalledTimes(3);
    const cardCalls = fetchMock.mock.calls.filter((c) => String(c[0]).includes(CARD_PATH));
    expect(cardCalls).toHaveLength(1);
  });
});
