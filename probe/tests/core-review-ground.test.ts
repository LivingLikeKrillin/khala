import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { buildChangedEntities, runReviewGround } from '../src/core/review-ground.js';
import { KhalaClient } from '../src/khala/client.js';
import type { DetectedGroup } from '../src/core/scope-analyzer.js';

describe('buildChangedEntities', () => {
  it('응집 그룹+변경파일에서 엔티티와 귀속 파일을 만든다', () => {
    const groups: DetectedGroup[] = [
      { groupName: 'domain-crud', cohesionKeyValue: 'Order', files: [{ path: 'src/order/OrderService.java', role: 'Service' }] },
    ];
    const entities = buildChangedEntities(groups, ['src/order/OrderService.java', 'README.md']);
    const order = entities.find((e) => e.entityName === 'order-service');
    expect(order).toBeDefined();
    expect(order!.changedFiles).toContain('src/order/OrderService.java');
    expect(order!.changedFiles).not.toContain('README.md');
  });
});

describe('runReviewGround', () => {
  let orig: typeof globalThis.fetch;
  beforeEach(() => { orig = globalThis.fetch; });
  afterEach(() => { globalThis.fetch = orig; });

  it('엔티티 0개면 ok:false', async () => {
    const client = new KhalaClient({ baseUrl: 'http://t:8000' });
    const r = await runReviewGround([], client);
    expect(r.ok).toBe(false);
  });

  it('Khala 미가용이면 T0 + changedEntities만', async () => {
    globalThis.fetch = vi.fn().mockRejectedValue(new Error('down')) as unknown as typeof globalThis.fetch;
    const client = new KhalaClient({ baseUrl: 'http://t:8000' });
    const r = await runReviewGround([{ entityName: 'order-service', changedFiles: ['a.ts'] }], client);
    expect(r.ok).toBe(true);
    if (r.ok) {
      expect(r.pack.tier).toBe(0);
      expect(r.pack.changedEntities[0]!.entityName).toBe('order-service');
    }
  });
});
