import { describe, expect, it } from 'vitest';
import { freshnessLabel } from './freshness.js';

const NOW = Date.parse('2026-07-10T12:00:00Z');

describe('freshnessLabel', () => {
  it('30초 전은 "방금 적재"', () => {
    expect(freshnessLabel('2026-07-10T11:59:30Z', NOW)).toBe('방금 적재');
  });
  it('15분 전', () => {
    expect(freshnessLabel('2026-07-10T11:45:00Z', NOW)).toBe('15분 전 적재');
  });
  it('3시간 전', () => {
    expect(freshnessLabel('2026-07-10T09:00:00Z', NOW)).toBe('3시간 전 적재');
  });
  it('2일 전', () => {
    expect(freshnessLabel('2026-07-08T12:00:00Z', NOW)).toBe('2일 전 적재');
  });
  it('경계: 정확히 60초는 분 단위로 넘어간다', () => {
    expect(freshnessLabel('2026-07-10T11:59:00Z', NOW)).toBe('1분 전 적재');
  });
  it('null/빈값/undefined는 빈 문자열 (배지를 숨긴다)', () => {
    expect(freshnessLabel(null, NOW)).toBe('');
    expect(freshnessLabel('', NOW)).toBe('');
    expect(freshnessLabel(undefined, NOW)).toBe('');
  });
  it('파싱 불가는 빈 문자열', () => {
    expect(freshnessLabel('garbage', NOW)).toBe('');
  });
  it('미래 시각은 빈 문자열 — 시계 어긋남을 "N분 전"으로 거짓말하지 않는다', () => {
    expect(freshnessLabel('2026-07-10T13:00:00Z', NOW)).toBe('');
  });
});
