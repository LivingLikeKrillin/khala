import { describe, it, expect } from 'vitest';
import { determineTier } from '../src/nexus/tier.js';
import type { NexusStatusResult } from '../src/nexus/types.js';

describe('determineTier (nexus/tier)', () => {
  it('null+timeout이면 T0이고 미가용과 사유가 다르다', () => {
    expect(determineTier(null, 'timeout').tier).toBe(0);
    expect(determineTier(null, 'timeout').reason).not.toBe(determineTier(null, 'unreachable').reason);
  });
  it('관측 엣지가 있으면 T3', () => {
    const s: NexusStatusResult = { db_connected: true, edges_count: 3, observed_edges_count: 2 };
    expect(determineTier(s).tier).toBe(3);
  });
});
