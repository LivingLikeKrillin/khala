import { describe, it, expect } from 'vitest';
import { forRequest, MAX_TURNS, MAX_BYTES } from './history.js';

const turn = (role, content) => ({ role, content });

describe('forRequest', () => {
  it('drops the turns the caller has already pushed for this exchange', () => {
    // 채팅 화면은 전송 **직전에** 이번 질문과 빈 어시스턴트 버블을 넣는다. 그 둘을 안 빼면
    // 이번 질의가 이력으로도 한 번 더 가고, 재작성기는 자기 자신을 맥락으로 읽는다.
    const bubbles = [
      turn('user', '앞 질문'),
      turn('assistant', '앞 답변'),
      turn('user', '이번 질문'),
      { role: 'assistant', content: '', id: 'msg-1' },
    ];
    expect(forRequest(bubbles)).toEqual([
      turn('user', '앞 질문'),
      turn('assistant', '앞 답변'),
    ]);
  });

  it('strips view-only fields so the body matches the server contract', () => {
    const bubbles = [
      { role: 'user', content: '질문', id: 'msg-9' },
      turn('assistant', '답변'),
      turn('user', 'x'), turn('assistant', ''),
    ];
    expect(forRequest(bubbles)[0]).toEqual({ role: 'user', content: '질문' });
  });

  it('never sends an empty bubble — that is an answer that has not arrived', () => {
    const bubbles = [
      turn('user', '질문'), { role: 'assistant', content: '', id: 'streaming' },
      turn('user', 'x'), turn('assistant', ''),
    ];
    expect(forRequest(bubbles)).toEqual([turn('user', '질문')]);
  });

  it('keeps the most recent turns when there are more than the cap', () => {
    const bubbles = [];
    for (let i = 0; i < 20; i += 1) bubbles.push(turn(i % 2 ? 'assistant' : 'user', `t${i}`));
    bubbles.push(turn('user', '이번'), turn('assistant', ''));

    const out = forRequest(bubbles);
    expect(out).toHaveLength(MAX_TURNS);
    // 오래된 맥락보다 최근 맥락이 이번 질문을 푼다.
    expect(out[out.length - 1].content).toBe('t19');
  });

  it('trims by bytes too — one long answer can blow the cap on its own', () => {
    // 답변은 길다. 턴 수만 세면 8턴짜리 긴 대화가 상한을 훌쩍 넘고 서버가 413 을 준다.
    const long = '가'.repeat(4000);          // 12000 바이트 (한글 3바이트)
    const bubbles = [
      turn('user', long), turn('assistant', long),
      turn('user', '이번'), turn('assistant', ''),
    ];
    const out = forRequest(bubbles);
    const total = out.reduce((n, t) => n + new TextEncoder().encode(t.content).length, 0);
    expect(total).toBeLessThanOrEqual(MAX_BYTES);
  });

  it('counts Korean in utf-8 bytes, not characters', () => {
    // 문자 수로 세면 상한이 조용히 3배가 된다 — 서버는 바이트로 세므로 413 이 난다.
    const almost = '가'.repeat(Math.floor(MAX_BYTES / 3) - 1);   // ~8Ki 바이트
    const out = forRequest([turn('user', almost), turn('user', '이번'), turn('assistant', '')]);
    const total = out.reduce((n, t) => n + new TextEncoder().encode(t.content).length, 0);
    expect(total).toBeLessThanOrEqual(MAX_BYTES);
  });

  it('is empty for a first question — U2 must change nothing for single-turn use', () => {
    expect(forRequest([turn('user', '첫 질문'), turn('assistant', '')])).toEqual([]);
    expect(forRequest([])).toEqual([]);
    expect(forRequest(undefined)).toEqual([]);
  });
});
