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

  // ---------------------------------- 판정의 기준 (2026-09-11)
  //
  // ⛔ 이 묶음이 없어서 배지가 "모두 현재 코드에 그대로 있습니다" 라고 적고 있었다.
  // 비교 대상은 현재 코드가 아니라 마지막 스캔이고, 라이브에서 그 스캔은 리포당 한 번만
  // 돌아 있었다. 앵커가 전부 일치로 나온 것은 코드가 안 바뀌어서가 아니라 비교 대상이
  // 안 움직여서였다. 배지는 모른다고 하지 않고 안심시키고 있었다.

  const scan = { commit: '780f94d6a7d5aaaa', at: '2026-08-18' };

  it('일치 배지가 무엇과 비교했는지 라벨에 적는다 — 툴팁에 숨기면 아무도 안 본다', () => {
    const sig = anchorSignal({ total: 27, fresh: 27, changed: [], orphaned: [], ambiguous_now: [], scan });

    expect(sig.label).toContain('27');
    expect(sig.label).toContain('2026-08-18');
    expect(sig.note).toContain('780f94d6a7d5');
  });

  it('어긋남 배지도 기준을 적는다 — 어긋난 수만 말하면 언제 기준인지 모른다', () => {
    const sig = anchorSignal({
      total: 40, fresh: 38, changed: ['Beta'], orphaned: ['Gamma'], ambiguous_now: [], scan,
    });

    expect(sig.label).toContain('2/40');
    expect(sig.label).toContain('2026-08-18');
    expect(sig.note).toContain('Gamma');
  });

  it('⛔ 「현재 코드」라고 단정하지 않는다 — 요청 경로는 배포된 코드가 어느 커밋인지 모른다', () => {
    const sig = anchorSignal({ total: 3, fresh: 3, changed: [], orphaned: [], ambiguous_now: [], scan });

    expect(sig.note).not.toContain('현재 코드');
    expect(`${sig.label} ${sig.note}`).toContain('2026-08-18');
  });

  it('기준이 없으면 미상이라고 말한다 — 모르는 것을 조용히 넘기면 안심시키는 쪽으로 읽힌다', () => {
    const sig = anchorSignal({ total: 3, fresh: 3, changed: [], orphaned: [], ambiguous_now: [] });

    expect(sig.tone).toBe('ok');
    expect(sig.label).toContain('미상');
    expect(sig.note).not.toContain('현재 코드');
  });

  it('지워진 이름 배지에는 스캔 기준을 안 붙인다 — 그 목록은 git 이력에서 온다', () => {
    const sig = anchorSignal({ total: 5, fresh: 5, deleted: [gone('Avatar', '2026-02-19')], scan });

    expect(sig.label).not.toContain('2026-08-18');
  });
});
