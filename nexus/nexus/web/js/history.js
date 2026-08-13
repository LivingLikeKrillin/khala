// 대화 이력을 서버 계약에 맞게 다듬는다 (SPEC-nexus-multi-turn-retrieval §3.1, U2).
//
// 서버는 상한을 넘긴 요청을 **조용히 자르지 않고 413 으로 거절한다** — 그래야 클라이언트가
// 자기 맥락의 절반이 사라진 것을 관측할 수 있다. 그 대신 자르는 판단은 여기서, 명시적으로 한다.
//
// 상한 두 축은 서버의 `nexus/search/history.py` 가 정본이다. 여기 값이 그보다 크면 사용자는
// 413 을 보고, 작으면 보낼 수 있는 맥락을 스스로 버린다 — 둘 다 조용한 실패라 테스트로 박는다.

export const MAX_TURNS = 8;
export const MAX_BYTES = 8 * 1024;

const bytes = (s) => new TextEncoder().encode(s || '').length;

/**
 * 화면의 말풍선 목록 → 서버에 보낼 이력.
 *
 * @param {Array<{role: string, content: string, id?: string}>} bubbles
 *   가장 오래된 것부터. 화면 전용 필드(`id`)가 섞여 있다.
 * @param {number} dropTrailing
 *   끝에서 제외할 개수. 웹 채팅은 전송 **직전에** 이번 질문과 빈 어시스턴트 버블을 이미
 *   넣어 두므로 기본값이 2 다. 이걸 안 빼면 이번 질의가 이력으로도 한 번 더 간다.
 * @returns {Array<{role: string, content: string}>}
 */
export function forRequest(bubbles, dropTrailing = 2) {
  const kept = (bubbles || []).slice(0, Math.max(0, (bubbles || []).length - dropTrailing));

  // 빈 말풍선은 아직 안 온 답변이다 — 이력이 아니다.
  const turns = kept
    .filter((b) => b && typeof b.content === 'string' && b.content.trim() !== '')
    .filter((b) => b.role === 'user' || b.role === 'assistant')
    .map((b) => ({ role: b.role, content: b.content }));

  // **뒤에서부터** 담는다. 오래된 맥락보다 최근 맥락이 이번 질문을 푸는 데 쓰인다.
  const out = [];
  let total = 0;
  for (let i = turns.length - 1; i >= 0 && out.length < MAX_TURNS; i -= 1) {
    const size = bytes(turns[i].content);
    if (total + size > MAX_BYTES) break;
    total += size;
    out.unshift(turns[i]);
  }
  return out;
}
