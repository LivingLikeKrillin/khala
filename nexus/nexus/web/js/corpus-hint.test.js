import { describe, expect, it } from 'vitest';
import { corpusHint } from './corpus-hint.js';

describe('corpusHint', () => {
  it('코퍼스가 비었으면 문서를 올리라고 안내한다', () => {
    const h = corpusHint(0);
    expect(h).not.toBeNull();
    expect(h.empty).toBe(true);
    expect(h.title).toMatch(/문서/);          // "먼저 문서를 올리세요" 류
  });

  it('문서가 있으면 안내하지 않는다 (예시 질문 그대로)', () => {
    expect(corpusHint(20)).toBeNull();
    expect(corpusHint(1)).toBeNull();
  });

  it('알 수 없는 수(폴링 전, undefined/null)는 안내하지 않는다 — 0 으로 착각해 깜빡이지 않게', () => {
    expect(corpusHint(undefined)).toBeNull();
    expect(corpusHint(null)).toBeNull();
  });

  it('음수 같은 이상값도 안내하지 않는다 (0 만 빈 코퍼스)', () => {
    expect(corpusHint(-1)).toBeNull();
  });
});
