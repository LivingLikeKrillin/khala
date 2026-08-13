-- 어떤 프롬프트가 이 답을 만들었는가 (LLMOps: 프롬프트 버전 기록).
--
-- 프롬프트를 고치면 답이 달라진다. 그런데 기록에는 그 경계가 없었다 — `SYSTEM_PROMPT` 한 줄을
-- 바꿔도 어제 행과 오늘 행이 똑같아 보이고, "지난주보다 답이 나빠졌다" 를 조사할 때 무엇이
-- 바뀌었는지 알 방법이 없다. U3 가 턴당 프롬프트를 둘로 늘리면서 더 아파졌다.
--
-- 값은 **프롬프트 텍스트에서 파생**된다(nexus/llm/prompt_version.py). 사람이 올리는 번호가
-- 아니므로 잊을 수 있는 단계가 없다.
--
-- 빈 문자열 = 그 프롬프트가 이 요청에 쓰이지 않았다(검색 전용 경로, 재작성 없는 질의).
-- 기본값이 빈 문자열인 이유: 지금까지 쌓인 행은 어떤 프롬프트였는지 **알 수 없다**.
-- 0 이나 'unknown' 으로 채우면 모르는 것을 아는 것처럼 적게 된다.
ALTER TABLE search_log ADD COLUMN IF NOT EXISTS answer_prompt_sha  TEXT NOT NULL DEFAULT '';
ALTER TABLE search_log ADD COLUMN IF NOT EXISTS rewrite_prompt_sha TEXT NOT NULL DEFAULT '';
