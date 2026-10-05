-- 요청자가 준 **검색 글**(`search_text`)의 흔적 — 길이와 해시뿐이다.
--
-- 검색 글은 검색 쪽(원문 경로 · 식별자 채널 · 엔티티 · 묶음의 코드 값 맞추기)에만 쓰이고, 답변
-- 프롬프트의 질문 자리는 계속 `query` 다(nexus/api.py `AnswerRequest.search_text`). 그래서
-- `query_sha256` 은 계속 **질문**의 값이고, 같은 질문을 다른 검색 글로 돌린 행은 이 두 칸으로
-- 갈린다 — 호출자가 견주는 두 실험군이 그렇게 생겼다.
--
-- 본문은 남기지 않는다. `answer_context`(046)와 같은 방식이고 이유도 같다.
--
-- 0 · 빈 문자열 = 안 줬다, 또는 이 칸이 생기기 전의 행. 옛 행을 채우지 않는다 — 그때는 이 칸이
-- 요청에 없었으므로 0 이 사실이다.
ALTER TABLE search_log ADD COLUMN IF NOT EXISTS search_text_len    INTEGER NOT NULL DEFAULT 0;
ALTER TABLE search_log ADD COLUMN IF NOT EXISTS search_text_sha256 TEXT    NOT NULL DEFAULT '';
