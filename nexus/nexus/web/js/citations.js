/**
 * 인용 검증 표시 모델 — SPEC-nexus-web-citation-verification.
 *
 * 스트림 `done` 이벤트의 citations([{title, section, verified}])를 사용자 표시용으로 요약한다.
 * verified 는 backend validate_citations(#134) 판정: 인용한 제목이 근거 스니펫 제목과 일치하면
 * true, 아니면 false(근거에서 확인 안 됨 — 지어낸 인용일 수 있음).
 *
 * 순수 함수(DOM 무관). DOM 배선은 chat.js, 스타일은 style.css.
 */

const NO_TITLE = '(제목 없음)';

function _label(c) {
  const title = String(c && c.title != null ? c.title : '').trim() || NO_TITLE;
  const section = c && typeof c.section === 'string' ? c.section.trim() : '';
  return section ? `${title} · ${section}` : title;
}

/**
 * @param {Array<{title?:string, section?:string, verified?:boolean}>} citations
 * @returns {null | {total:number, verifiedCount:number, unverifiedCount:number,
 *   tone:'ok'|'warn', summary:string, items:Array<{label:string, verified:boolean}>}}
 */
export function citationReport(citations) {
  if (!Array.isArray(citations) || citations.length === 0) return null;

  // label 로 dedup — 같은 [출처] 반복 시 한 번만. 충돌 시 미검증이 이긴다(보수적).
  const byLabel = new Map();
  for (const c of citations) {
    const label = _label(c);
    const verified = (c && c.verified === true);
    if (byLabel.has(label)) {
      byLabel.set(label, byLabel.get(label) && verified);
    } else {
      byLabel.set(label, verified);
    }
  }

  const items = [...byLabel.entries()].map(([label, verified]) => ({ label, verified }));
  const total = items.length;
  const verifiedCount = items.filter(i => i.verified).length;
  const unverifiedCount = total - verifiedCount;
  const tone = unverifiedCount > 0 ? 'warn' : 'ok';
  const summary = unverifiedCount > 0
    ? `출처 ${total}개 중 ${unverifiedCount}개가 근거에서 확인 안 됨`
    : `출처 ${total}개 — 모두 근거에서 확인됨`;

  return { total, verifiedCount, unverifiedCount, tone, summary, items };
}
