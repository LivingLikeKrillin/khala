import { describe, it, expect } from 'vitest';
import type { GroundingPack, Suspect } from '../src/khala/types.js';

describe('트러블슈팅 타입', () => {
  it('GroundingPack을 최소 형태로 구성할 수 있다', () => {
    const suspect: Suspect = { entityName: 'order-service', evidence: [], confidence: 0.9 };
    const pack: GroundingPack = {
      tier: 0,
      tierReason: 'Khala 미가용',
      suspects: [suspect],
      caveats: [],
    };
    expect(pack.suspects[0]!.entityName).toBe('order-service');
    expect(pack.tier).toBe(0);
  });
});
