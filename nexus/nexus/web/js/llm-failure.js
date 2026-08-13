// LLM 생성 실패를 사용자에게 어떻게 말할 것인가 (서버: nexus/llm/failure.py).
//
// 서버가 사유를 **한 번** 분류해 `done` 이벤트에 실어 준다. 웹은 그 코드만 보고, 공급자 문구를
// 문자열 매칭하지 않는다 — 그 문구는 공급자가 바꾸고, 그때 조용히 오분류가 시작된다.
//
// 왜 갈라야 하는가: 2026-08-13 파일럿에서 크레딧이 소진됐는데 사용자가 본 문장은 "잠시 후 다시
// 시도하세요" 였다. 기다려도 영원히 안 된다. 반대로 진짜 일시 장애에 "운영자에게" 라고 하면
// 아무 일도 없는데 사람을 부른다.

const MESSAGES = {
  quota: '답변 생성 크레딧이 소진되었습니다 — 운영자에게 알리세요. 재시도해도 해결되지 않습니다.',
  auth: '답변 생성 키 설정이 잘못되었습니다 — 운영자에게 알리세요. 재시도해도 해결되지 않습니다.',
  rate_limit: '답변 생성이 일시적으로 밀렸습니다. 잠시 후 다시 시도하세요.',
  unavailable: '답변 생성이 일시적으로 불가합니다. 잠시 후 다시 시도하세요.',
};

const RETRYABLE = new Set(['rate_limit', 'unavailable']);

/** 이 사유는 기다리면 나아지는가. 모르는 사유는 **아니라고** 답한다. */
export function isTransient(reason) {
  return RETRYABLE.has(reason);
}

/**
 * `done` 이벤트 → 사용자에게 보일 실패 안내. 실패가 아니면 null.
 *
 * 근거는 검색됐다는 사실을 함께 말한다 — 화면에 이미 근거 패널이 떠 있는데 "실패" 만 보이면
 * 사용자는 아무것도 못 얻은 줄 안다.
 */
export function failureNotice(done) {
  if (!done || !done.llm_failed) return null;
  const known = MESSAGES[done.llm_failure_reason];
  return known || '근거는 찾았지만 답변 생성에 실패했습니다 — 운영자에게 알리세요.';
}
