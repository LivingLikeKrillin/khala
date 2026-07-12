import { describe, expect, it } from 'vitest';
import { citationReport } from './citations.js';

describe('citationReport', () => {
  it('null/undefined/[]/비배열 → null (스트립 숨김)', () => {
    expect(citationReport(null)).toBeNull();
    expect(citationReport(undefined)).toBeNull();
    expect(citationReport([])).toBeNull();
    expect(citationReport('nope')).toBeNull();
    expect(citationReport({})).toBeNull();
  });

  it('전부 verified → tone ok, unverified 0, 전 항목 verified, ok 요약', () => {
    const r = citationReport([
      { title: 'A', section: '', verified: true },
      { title: 'B', section: '개요', verified: true },
    ]);
    expect(r.tone).toBe('ok');
    expect(r.total).toBe(2);
    expect(r.verifiedCount).toBe(2);
    expect(r.unverifiedCount).toBe(0);
    expect(r.items.every(i => i.verified)).toBe(true);
    expect(r.summary).toBe('출처 2개 — 모두 근거에서 확인됨');
  });

  it('혼합 → tone warn, unverifiedCount, warn 요약이 M 명시', () => {
    const r = citationReport([
      { title: 'A', section: '', verified: true },
      { title: '지어낸 문서', section: '', verified: false },
    ]);
    expect(r.tone).toBe('warn');
    expect(r.total).toBe(2);
    expect(r.unverifiedCount).toBe(1);
    expect(r.summary).toBe('출처 2개 중 1개가 근거에서 확인 안 됨');
  });

  it('count/summary 일치 불변식: 요약의 M == items 미검증 수 == unverifiedCount', () => {
    const r = citationReport([
      { title: 'A', verified: true },
      { title: 'B', verified: false },
      { title: 'C', verified: false },
    ]);
    const m = Number(r.summary.match(/중 (\d+)개/)[1]);
    const fromItems = r.items.filter(i => !i.verified).length;
    expect(m).toBe(fromItems);
    expect(m).toBe(r.unverifiedCount);
  });

  it('verified 누락/undefined/false → 미검증(검증 배지 함부로 안 붙임)', () => {
    const r = citationReport([
      { title: 'A' },                       // 누락
      { title: 'B', verified: undefined },  // undefined
      { title: 'C', verified: false },      // false
      { title: 'D', verified: 'yes' },      // truthy이지만 !== true
    ]);
    expect(r.verifiedCount).toBe(0);
    expect(r.unverifiedCount).toBe(4);
    expect(r.items.every(i => !i.verified)).toBe(true);
  });

  it('dedup: 같은 [출처] 반복 → 한 항목', () => {
    const r = citationReport([
      { title: 'A', section: '', verified: true },
      { title: 'A', section: '', verified: true },
      { title: 'A', section: '', verified: true },
    ]);
    expect(r.total).toBe(1);
    expect(r.items).toHaveLength(1);
  });

  it('dedup 충돌: 같은 label 이 verified+unverified → 미검증(보수적)', () => {
    const r = citationReport([
      { title: 'A', section: '', verified: true },
      { title: 'A', section: '', verified: false },
    ]);
    expect(r.total).toBe(1);
    expect(r.unverifiedCount).toBe(1);
    expect(r.tone).toBe('warn');
    expect(r.items[0].verified).toBe(false);
  });

  it('label: section 비어있으면 title, 있으면 "title · section"', () => {
    const r = citationReport([
      { title: '결제 설계', section: '', verified: true },
      { title: '주문 설계', section: '이벤트', verified: true },
    ]);
    expect(r.items[0].label).toBe('결제 설계');
    expect(r.items[1].label).toBe('주문 설계 · 이벤트');
  });

  it('label: 공백/비문자열 section 은 무시 → title 만', () => {
    const r = citationReport([
      { title: 'A', section: '   ', verified: true },
      { title: 'B', section: null, verified: true },
      { title: 'C', section: 42, verified: true },
    ]);
    expect(r.items[0].label).toBe('A');
    expect(r.items[1].label).toBe('B');
    expect(r.items[2].label).toBe('C');
  });

  it('label: title 비어있거나 없으면 (제목 없음)', () => {
    const r = citationReport([
      { title: '', verified: false },
      { title: '   ', verified: false },
      { section: '어딘가', verified: false },
    ]);
    // 셋 다 title 공백 → 같은 label 로 dedup 되어 한 항목
    expect(r.items.every(i => i.label.startsWith('(제목 없음)'))).toBe(true);
  });
});
