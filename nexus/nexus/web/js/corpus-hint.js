/**
 * 빈 코퍼스 안내 — 감사 §9 5단계(첫 실행 마찰)의 웹 몫.
 *
 * 채팅 빈 화면은 늘 예시 질문을 보여준다. 하지만 아무것도 적재하지 않은 새 사용자에게는
 * 그 질문들이 전부 "결과 없음"으로 끝난다 — 도구가 고장 난 것처럼 보인다. 코퍼스가 0건이면
 * 먼저 무엇을 해야 하는지 말한다.
 *
 * 순수 함수(freshness.js 와 같은 결). DOM 은 chat.js 가 이 결과로 그린다.
 */

/**
 * @param {number|null|undefined} documentsCount `/status` 의 documents_count.
 * @returns {{empty:true,title:string,body:string}|null} 0 이면 안내, 그 외엔 null.
 */
export function corpusHint(documentsCount) {
  // 정확히 0 일 때만 빈 코퍼스다. undefined/null(폴링 전)이나 이상값은 안내하지 않는다 —
  // 로딩 중을 "비었다"로 착각해 화면이 깜빡이지 않도록.
  if (documentsCount !== 0) return null;
  return {
    empty: true,
    title: '아직 문서가 없습니다',
    body: '먼저 문서를 올리면 여기서 질문할 수 있습니다. '
        + '왼쪽 업로드 탭에서 파일을, 소스 탭에서 Notion 페이지를 연결하세요.',
  };
}
