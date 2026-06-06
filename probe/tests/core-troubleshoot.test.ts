import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { determineTier, validateInput } from '../src/core/troubleshoot.js';
import type { KhalaStatusResult } from '../src/khala/types.js';

describe('determineTier', () => {
  it('Khala 미가용이면 T0', () => {
    expect(determineTier(null).tier).toBe(0);
  });
  it('문서만 있으면 T1', () => {
    const s: KhalaStatusResult = { db_connected: true, documents_count: 5, edges_count: 0 };
    expect(determineTier(s).tier).toBe(1);
  });
  it('설계 엣지가 있으면 T2', () => {
    const s: KhalaStatusResult = { db_connected: true, documents_count: 5, edges_count: 3, observed_edges_count: 0 };
    expect(determineTier(s).tier).toBe(2);
  });
  it('관측 엣지가 있으면 T3', () => {
    const s: KhalaStatusResult = { db_connected: true, edges_count: 3, observed_edges_count: 2 };
    expect(determineTier(s).tier).toBe(3);
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
import { KhalaClient } from '../src/khala/client.js';

describe('runTroubleshoot 경로', () => {
  let originalFetch: typeof globalThis.fetch;
  beforeEach(() => { originalFetch = globalThis.fetch; });
  afterEach(() => { globalThis.fetch = originalFetch; });

  it('빈 입력은 ok:false', async () => {
    const client = new KhalaClient({ baseUrl: 'http://test:8000' });
    const r = await runTroubleshoot({ signal: '' }, client);
    expect(r.ok).toBe(false);
  });

  it('Khala 미가용이면 T0 + 국소화만', async () => {
    globalThis.fetch = vi.fn().mockRejectedValue(new Error('down'));
    const client = new KhalaClient({ baseUrl: 'http://test:8000' });
    const r = await runTroubleshoot(
      { signal: 'at com.shop.order.OrderService.checkout(OrderService.java:88)' }, client,
    );
    expect(r.ok).toBe(true);
    if (r.ok) {
      expect(r.pack.tier).toBe(0);
      expect(r.pack.suspects[0]!.entityName).toBe('order-service');
    }
  });
});
