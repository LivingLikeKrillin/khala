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

/**
 * 이 판정이 **무엇과 비교한 것인가**를 말로 바꾼다.
 *
 * ⛔ **왜 있나 (실측 2026-09-11).** 예전에는 일치일 때 "모두 **현재** 코드에 그대로 있습니다"
 * 라고 적었다. 비교 대상은 현재 코드가 아니라 마지막 코드 스캔이고, 라이브에서 그 스캔은
 * 리포당 **한 번**만 돌아 있었다(2026-08-16 · 2026-08-18). 앵커 5,440건이 전부 일치로 나온
 * 것은 코드가 안 바뀌어서가 아니라 비교 대상이 안 움직여서였다. 배지는 「모름」이라고 하지
 * 않고 「일치」라고 안심시키고 있었다.
 *
 * 요청 경로는 배포된 코드가 지금 어느 커밋인지 알 수 없다(운영자용 `nexus code drift` 는
 * 작업 트리를 확인하고 모르면 보고를 거부한다). 그래서 여기서 하는 일은 판정을 멈추는 것이
 * 아니라 **기준을 같이 적는 것**이다.
 */
function basisPhrase(scan) {
  if (!scan || !scan.at) {
    return { short: '기준 스캔 미상', long: '이 판정이 무엇과 비교한 것인지 기록이 없습니다' };
  }
  const commit = String(scan.commit || '').slice(0, 12);
  const head = `${scan.at} 코드 스캔`;
  return {
    short: `${scan.at} 스캔 기준`,
    long: `${commit ? `${head}(${commit})` : head} 기준이고, 그 뒤의 코드 변경은 여기에 안 들어갑니다`,
  };
}

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
    // 기준 문구도 붙이지 않는다: 이 목록은 코드 스캔이 아니라 git 이력에서 온다.
    return { label: `지워진 이름 ${deleted.length}개`, tone: 'drift', note: parts.join(' · ') };
  }

  const basis = basisPhrase(summary.scan);
  if (drifted === 0) {
    return {
      label: `코드 ${summary.total}개 일치 · ${basis.short}`,
      tone: 'ok',
      note: `이 근거가 부른 코드 이름 ${summary.total}개가 모두 그대로 있습니다. ${basis.long}.`,
    };
  }
  return {
    label: `코드 ${drifted}/${summary.total} 어긋남 · ${basis.short}`,
    tone: 'drift',
    note: `${parts.join(' · ')} · ${basis.long}`,
  };
}
