/**
 * 코드 앵커 신호 — 이 근거가 부른 코드 이름이 **지금도 그 코드에 있는가**.
 *
 * 서버가 `evidence_snippets[].code_anchors` 로 이미 판정과 셈을 끝내 보낸다
 * (`nexus/search/anchor_status.py`). 여기서 다시 세지 않는다 — 표현계층이 판정을 흉내 내면
 * 두 개의 답이 생기고, 그중 하나는 반드시 뒤처진다. 이 파일이 하는 일은 **말로 바꾸는 것**뿐.
 *
 * 배지가 뜨는 조건: 앵커가 하나라도 있을 때. 앵커가 없는 코퍼스(코드 스캔을 안 한 테넌트)에서는
 * `code_anchors` 가 null 이고 화면은 오늘과 같다 — 기본이 조용해야 표시가 뜻을 갖는다.
 *
 * 로컬 검증: `npm test` (vitest, `anchor-signal.test.js`).
 */

/** 이름을 몇 개까지 툴팁에 부를 것인가. 40건짜리 문단이 툴팁을 채우면 아무도 안 읽는다. */
const MAX_NAMES = 6;

function joinNames(names) {
  const head = names.slice(0, MAX_NAMES).join(', ');
  const rest = names.length - MAX_NAMES;
  return rest > 0 ? `${head} 외 ${rest}개` : head;
}

/**
 * @param {?{total:number, fresh:number, changed:string[], orphaned:string[],
 *           ambiguous_now:string[]}} summary 서버가 보낸 요약. 없으면 null.
 * @returns {?{label:string, tone:'ok'|'drift', note:string}} 배지를 숨기려면 null.
 */
export function anchorSignal(summary) {
  if (!summary) return null;

  const changed = summary.changed || [];
  const orphaned = summary.orphaned || [];
  const ambiguous = summary.ambiguous_now || [];
  const deleted = summary.deleted || [];
  const drifted = changed.length + orphaned.length + ambiguous.length;

  if (!summary.total && !deleted.length) return null;

  const parts = [];
  // 지워진 이름이 먼저다 — 날짜와 사유가 붙어 있어 유일하게 바로 처분할 수 있는 항목이다.
  if (deleted.length) {
    parts.push(`지워진 이름: ${joinNames(deleted.map(d => `${d.name}(${d.date} 삭제)`))}`);
  }
  if (orphaned.length) parts.push(`코드에 없음: ${joinNames(orphaned)}`);
  if (changed.length) parts.push(`내용이 바뀜: ${joinNames(changed)}`);
  if (ambiguous.length) parts.push(`같은 이름이 여럿: ${joinNames(ambiguous)}`);

  if (deleted.length) {
    // 분모를 붙이지 않는다 — 지워진 이름은 바인딩된 적이 없어 total 의 일부가 아니다.
    return { label: `지워진 이름 ${deleted.length}개`, tone: 'drift', note: parts.join(' · ') };
  }
  if (drifted === 0) {
    return {
      label: `코드 ${summary.total}개 일치`,
      tone: 'ok',
      note: `이 근거가 부른 코드 이름 ${summary.total}개가 모두 현재 코드에 그대로 있습니다`,
    };
  }
  return { label: `코드 ${drifted}/${summary.total} 어긋남`, tone: 'drift', note: parts.join(' · ') };
}
