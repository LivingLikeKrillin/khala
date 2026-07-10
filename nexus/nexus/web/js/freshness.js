/**
 * 코퍼스 신선도 신호 — SPEC 없음, 감사 §9 "실패를 보이게"의 Reader 몫.
 *
 * `last_ingest_at`(마지막 적재 시각)을 사람이 읽는 상대시간으로. 이게 Reader 신호인 이유:
 * "이 검색 결과가 최근 것인가"에 답한다. 지난주 코퍼스를 통째로 날렸을 때, 화면은 아무 말도
 * 하지 않았다 — 문서 수는 20에서 8로 조용히 줄었을 뿐. 신선도를 보이면 그런 침묵이 사라진다.
 *
 * health dot(db/ollama/tempo)과 달리 이건 운영자 신호가 아니다. Reader 가 자기 결과를
 * 얼마나 믿을지 정하는 신호다.
 *
 * 로컬 검증(웹 JS 를 도는 CI 잡이 아직 없다):
 *   node --input-type=module -e "import {freshnessLabel} from './nexus/web/js/freshness.js';
 *     const n=Date.parse('2026-07-10T12:00:00Z');
 *     console.log(freshnessLabel('2026-07-10T09:00:00Z',n))"   // → '3시간 전 적재'
 */

/** ISO 시각 → 상대시간 라벨. null/미래/파싱실패는 빈 문자열(배지를 숨긴다). */
export function freshnessLabel(iso, nowMs = Date.now()) {
  if (!iso) return '';
  const then = Date.parse(iso);
  if (Number.isNaN(then)) return '';

  const diffSec = Math.floor((nowMs - then) / 1000);
  if (diffSec < 0) return '';                 // 미래 시각 — 시계 어긋남, 말하지 않는다
  if (diffSec < 60) return '방금 적재';
  const min = Math.floor(diffSec / 60);
  if (min < 60) return `${min}분 전 적재`;
  const hr = Math.floor(min / 60);
  if (hr < 24) return `${hr}시간 전 적재`;
  const day = Math.floor(hr / 24);
  return `${day}일 전 적재`;
}
