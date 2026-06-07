import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { determineTier, validateInput } from '../src/core/troubleshoot.js';
import type { NexusStatusResult } from '../src/nexus/types.js';

describe('determineTier', () => {
  it('Nexus 미가용이면 T0', () => {
    expect(determineTier(null).tier).toBe(0);
  });
  it('문서만 있으면 T1', () => {
    const s: NexusStatusResult = { db_connected: true, documents_count: 5, edges_count: 0 };
    expect(determineTier(s).tier).toBe(1);
  });
  it('설계 엣지가 있으면 T2', () => {
    const s: NexusStatusResult = { db_connected: true, documents_count: 5, edges_count: 3, observed_edges_count: 0 };
    expect(determineTier(s).tier).toBe(2);
  });
  it('관측 엣지가 있으면 T3', () => {
    const s: NexusStatusResult = { db_connected: true, edges_count: 3, observed_edges_count: 2 };
    expect(determineTier(s).tier).toBe(3);
  });
  it('타임아웃 실패는 T0이지만 미가용과 사유를 구분한다', () => {
    const slow = determineTier(null, 'timeout');
    const down = determineTier(null, 'unreachable');
    expect(slow.tier).toBe(0);
    expect(down.tier).toBe(0);
    expect(slow.reason).toMatch(/시간 초과|타임아웃|느림|timeout/i);
    expect(slow.reason).not.toBe(down.reason);
  });
});

describe('validateInput', () => {
  it('빈 신호를 거부한다', () => {
    expect(validateInput({ signal: '   ' }).ok).toBe(false);
  });
  it('과대 입력을 절단하고 caveat를 남긴다', () => {
    const r = validateInput({ signal: 'x'.repeat(50_000) });
    expect(r.ok).toBe(true);
    expect(r.signal!.length).toBeLessThan(50_000);
    expect(r.caveats.length).toBeGreaterThan(0);
  });
});

import { runTroubleshoot } from '../src/core/troubleshoot.js';
import { NexusClient } from '../src/nexus/client.js';

describe('runTroubleshoot 경로', () => {
  let originalFetch: typeof globalThis.fetch;
  beforeEach(() => {
    originalFetch = globalThis.fetch;
  });
  afterEach(() => {
    globalThis.fetch = originalFetch;
  });

  it('빈 입력은 ok:false', async () => {
    const client = new NexusClient({ baseUrl: 'http://test:8000' });
    const r = await runTroubleshoot({ signal: '' }, client);
    expect(r.ok).toBe(false);
  });

  it('Nexus 미가용이면 T0 + 국소화만', async () => {
    globalThis.fetch = vi.fn().mockRejectedValue(new Error('down'));
    const client = new NexusClient({ baseUrl: 'http://test:8000' });
    const r = await runTroubleshoot(
      { signal: 'at com.shop.order.OrderService.checkout(OrderService.java:88)' },
      client,
    );
    expect(r.ok).toBe(true);
    if (r.ok) {
      expect(r.pack.tier).toBe(0);
      expect(r.pack.suspects[0]!.entityName).toBe('order-service');
    }
  });

  it('kind 힌트가 본문과 모순되면 caveat를 남긴다', async () => {
    globalThis.fetch = vi.fn().mockRejectedValue(new Error('down'));
    const client = new NexusClient({ baseUrl: 'http://test:8000' });
    // 본문은 스택트레이스인데 kind=incident로 모순 지정
    const r = await runTroubleshoot(
      { signal: 'at com.shop.order.OrderService.checkout(OrderService.java:88)', kind: 'incident' },
      client,
    );
    expect(r.ok).toBe(true);
    if (r.ok) expect(r.pack.caveats.some((c) => c.includes('kind'))).toBe(true);
  });
});
