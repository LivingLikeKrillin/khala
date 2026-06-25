/**
 * doc_type(축-A 타입) → 리더용 신뢰 신호.
 *
 * ⚠️ 미러: 타입→tier 그룹핑의 정본은 specledger `document_types.yaml`(거버넌스 경계)이다.
 * 여기엔 검색 리더용 *짧은 신뢰 신호*만 둔다(풀 운용 가이드는 specledger `guide(type)`).
 * S3 결정(nexus는 tier 파생 안 함)을 지키려 이 매핑은 뷰 계층 표현물로만 존재한다.
 * — 기존 nexus a2a/external_ingest_skill.py `_KIND_ALIASES` 미러와 동일한 디커플링 패턴.
 */

const _GOVERNED = {
  tier: '거버넌스', tone: 'governed', label: '승인된 거버넌스 결정',
  note: '승인 게이트를 거친 정본 결정 — 상태(accepted/superseded) 확인',
};
const _TRACKED = {
  tier: '추적', tone: 'tracked', label: '추적 문서',
  note: '리뷰되나 승인 게이트 없음 — drift/staleness 주의',
};
const _MEMO = {
  tier: '메모', tone: 'memo', label: '비거버넌스 메모',
  note: '정본 아님 — 인덱싱·검색용 참고. 정본이면 promote 필요',
};

// 축-A 타입 → 신뢰 등급. 미등록/빈값은 보수적으로 메모(specledger default_tier=T3 정책과 일치).
const _BY_TYPE = {
  ADR: _GOVERNED, DESIGN: _GOVERNED, RFC: _GOVERNED,
  PRD: _TRACKED, RUNBOOK: _TRACKED, POSTMORTEM: _TRACKED,
  NOTE: _MEMO,
};

/**
 * @param {string} docType 축-A 타입(대소문자/공백 무시). 미지/빈값 → 메모.
 * @returns {{label:string, tier:string, tone:'governed'|'tracked'|'memo', note:string}}
 */
export function trustSignal(docType) {
  const key = String(docType || '').trim().toUpperCase();
  return _BY_TYPE[key] || _MEMO;
}
