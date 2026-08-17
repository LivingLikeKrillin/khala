import { describe, expect, it } from 'vitest';
import { anchorSignal } from './anchor-signal.js';

describe('anchorSignal', () => {
  it('앵커가 없으면 배지를 숨긴다 — 기본이 조용해야 표시가 뜻을 갖는다', () => {
    expect(anchorSignal(null)).toBe(null);
    expect(anchorSignal(undefined)).toBe(null);
    expect(anchorSignal({ total: 0, fresh: 0 })).toBe(null);
  });

  it('전부 일치하면 분모를 말한다', () => {
    const sig = anchorSignal({ total: 27, fresh: 27, changed: [], orphaned: [], ambiguous_now: [] });

    expect(sig.tone).toBe('ok');
    expect(sig.label).toContain('27');
  });

  it('어긋난 것이 있으면 몇 개 중 몇 개인지 — "1개 없어짐"만으로는 1/1 인지 1/40 인지 모른다', () => {
    const sig = anchorSignal({
      total: 40, fresh: 38, changed: ['Beta'], orphaned: ['Gamma'], ambiguous_now: [],
    });

    expect(sig.tone).toBe('drift');
    expect(sig.label).toContain('2/40');
    expect(sig.note).toContain('Gamma');
    expect(sig.note).toContain('Beta');
  });

  it('세 종류를 뭉뚱그리지 않는다 — 처방이 다르다', () => {
    const sig = anchorSignal({
      total: 3, fresh: 0, changed: ['B'], orphaned: ['A'], ambiguous_now: ['C'],
    });

    expect(sig.note).toContain('코드에 없음: A');
    expect(sig.note).toContain('내용이 바뀜: B');
    expect(sig.note).toContain('같은 이름이 여럿: C');
  });

  it('이름 목록에 상한이 있다', () => {
    const names = Array.from({ length: 12 }, (_, i) => `Sym${i}`);
    const sig = anchorSignal({ total: 12, fresh: 0, changed: [], orphaned: names, ambiguous_now: [] });

    expect(sig.note).toContain('Sym0');
    expect(sig.note).not.toContain('Sym11');
    expect(sig.note).toContain('외 6개');
  });

  it('서버가 목록 필드를 빠뜨려도 죽지 않는다', () => {
    expect(anchorSignal({ total: 2, fresh: 2 }).tone).toBe('ok');
  });
});

describe('anchorSignal — 지워진 이름', () => {
  const gone = (name, date) => ({ name, date, commit: 'abc1234', subject: 'refactor: drop it' });

  it('앵커가 없어도 지워진 이름만으로 배지가 뜬다 — 그게 최악의 문단이다', () => {
    const sig = anchorSignal({ total: 0, fresh: 0, deleted: [gone('Avatar', '2026-02-19')] });

    expect(sig.tone).toBe('drift');
    expect(sig.label).toContain('1개');
    expect(sig.note).toContain('2026-02-19');
  });

  it('분모를 붙이지 않는다 — 지워진 이름은 바인딩된 적이 없어 total 의 일부가 아니다', () => {
    const sig = anchorSignal({ total: 5, fresh: 5, deleted: [gone('Avatar', '2026-02-19')] });

    expect(sig.label).not.toContain('/5');
  });

  it('지워진 이름이 툴팁 맨 앞에 온다 — 유일하게 바로 처분할 수 있는 항목', () => {
    const sig = anchorSignal({
      total: 3, fresh: 2, changed: ['Beta'], deleted: [gone('Avatar', '2026-02-19')],
    });

    expect(sig.note.indexOf('Avatar')).toBeLessThan(sig.note.indexOf('Beta'));
  });

  it('deleted 가 없으면 예전과 똑같이 군다', () => {
    expect(anchorSignal({ total: 2, fresh: 2, deleted: [] }).tone).toBe('ok');
    expect(anchorSignal({ total: 0, fresh: 0, deleted: [] })).toBe(null);
  });
});
