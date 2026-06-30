import { describe, it, expect } from 'vitest';
import type { GroundingPack, Suspect } from '../src/nexus/types.js';
import type { ReviewGroundingPack, ChangedEntity, SpecRef } from '../src/nexus/types.js';

describe('트러블슈팅 타입', () => {
  it('GroundingPack을 최소 형태로 구성할 수 있다', () => {
    const suspect: Suspect = { entityName: 'order-service', evidence: [], confidence: 0.9 };
    const pack: GroundingPack = {
      tier: 0,
      tierReason: 'Nexus 미가용',
      suspects: [suspect],
      caveats: [],
    };
    expect(pack.suspects[0]!.entityName).toBe('order-service');
    expect(pack.tier).toBe(0);
  });
});

it('ReviewGroundingPack 타입이 구성된다', () => {
  const pack: ReviewGroundingPack = {
    tier: 2,
    tierReason: 'r',
    changedEntities: [{ entityName: 'order-service', changedFiles: ['a.ts'] }],
    caveats: [],
  };
  const spec: SpecRef = { docTitle: 't', sectionPath: 's', snippet: 'x', classification: 'INTERNAL' };
  const e: ChangedEntity = { entityName: 'x', changedFiles: [] };
  expect(pack.tier).toBe(2);
  expect(spec.docTitle).toBe('t');
  expect(e.entityName).toBe('x');
});
