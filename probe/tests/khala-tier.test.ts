import { describe, it, expect } from 'vitest';
import { determineTier } from '../src/khala/tier.js';
import type { KhalaStatusResult } from '../src/khala/types.js';

describe('determineTier (khala/tier)', () => {
  it('null+timeout이면 T0이고 미가용과 사유가 다르다', () => {
    expect(determineTier(null, 'timeout').tier).toBe(0);
    expect(determineTier(null, 'timeout').reason).not.toBe(determineTier(null, 'unreachable').reason);
  });
  it('관측 엣지가 있으면 T3', () => {
    const s: KhalaStatusResult = { db_connected: true, edges_count: 3, observed_edges_count: 2 };
    expect(determineTier(s).tier).toBe(3);
  });
});
