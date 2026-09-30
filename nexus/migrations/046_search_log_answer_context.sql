-- 요청자가 준 자료(`answer_context`)의 흔적 — **길이와 해시뿐이다.**
--
-- 자료는 답변 프롬프트에만 들어가고 검색에는 안 닿는다(nexus/llm/prompts.py). 진단 경로는 후보
-- 목록을 여기 싣고 설명 경로는 안 싣는다 — 그래서 이 두 칸으로 **두 경로의 행을 가른다.**
--
-- 본문은 남기지 않는다. 재작성문(`rephrased_sha256` · `rephrased_len`)과 같은 방식이고 이유도
-- 같다: 원 질문보다 민감할 수 있고, 질문 원문 보존은 옵트인 경로로만 간다.
--
-- 0 · 빈 문자열 = 안 줬다, 또는 이 칸이 생기기 전의 행. 옛 행을 채우지 않는다 — 그때는 이 칸이
-- 요청에 없었으므로 0 이 사실이다.
ALTER TABLE search_log ADD COLUMN IF NOT EXISTS answer_context_len    INTEGER NOT NULL DEFAULT 0;
ALTER TABLE search_log ADD COLUMN IF NOT EXISTS answer_context_sha256 TEXT    NOT NULL DEFAULT '';
