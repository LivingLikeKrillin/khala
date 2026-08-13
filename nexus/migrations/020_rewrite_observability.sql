-- 재작성을 사후에 볼 수 있게 한다 (SPEC-nexus-multi-turn-retrieval §3.5, U4).
--
-- 이 설계의 가장 큰 위험은 **재작성이 조용히 의도를 바꾸는 것**이다. 남기지 않으면 사후에
-- 볼 수 없고, 볼 수 없으면 고칠 수도 없다.

-- ── 신호: 텍스트가 아닌 것만 ──────────────────────────────────────────────────
-- `search_log` 는 "raw query 를 절대 저장하지 않는다" 고 선언된 테이블이다(init.sql, 원칙 #3).
-- 재작성문은 원 질문보다 **더** 민감하다 — §3.2 항목 3 이 사용자가 앞 턴에 준 사실을 일부러
-- 채워 넣기 때문이다. 게다가 같은 행이 `query_sha256` 을 들고 있고 `a2a_audit` 가 그것을
-- `principal` 옆에 갖고 있어, 보존 아키텍처가 소금키로 막아 둔 결합이 되살아난다.
ALTER TABLE search_log ADD COLUMN IF NOT EXISTS rewrite_applied  BOOLEAN NOT NULL DEFAULT false;
ALTER TABLE search_log ADD COLUMN IF NOT EXISTS rephrased_sha256 TEXT    NOT NULL DEFAULT '';
ALTER TABLE search_log ADD COLUMN IF NOT EXISTS rephrased_len    INTEGER NOT NULL DEFAULT 0;
-- 재작성이 **실제로 문장을 바꿨는가**. 보수적 재작성의 정상 결과는 "원문과 같음" 이므로,
-- 이 값이 갑자기 늘면 재작성기가 얌전하지 않게 된 것이다.
ALTER TABLE search_log ADD COLUMN IF NOT EXISTS rewrite_changed  BOOLEAN NOT NULL DEFAULT false;

-- ── 비용: 별도 칸 ─────────────────────────────────────────────────────────────
-- `prompt_tokens`/`completion_tokens`/`cost_usd` 는 행당 하나뿐이고
-- `nexus/llm/budget.py::measured_averages` 가 그 전체 평균을 "답변 1회 비용" 으로 쓴다.
-- 재작성 호출을 같은 칸에 접으면 그 추정기가 조용히 편향된다.
-- NULL = 미측정(0 아님) — 지어내지 않는다.
ALTER TABLE search_log ADD COLUMN IF NOT EXISTS rewrite_prompt_tokens     INTEGER;
ALTER TABLE search_log ADD COLUMN IF NOT EXISTS rewrite_completion_tokens INTEGER;
ALTER TABLE search_log ADD COLUMN IF NOT EXISTS rewrite_cost_usd          DOUBLE PRECISION;

-- ── 보존: 사람이 쓴 것과 기계가 쓴 것을 가른다 ────────────────────────────────
-- `search_query_text` 는 **실사용 질문**을 모으려고 만든 곳이다(SPEC-nexus-query-text-retention:
-- "평가 천장을 낮추는 유일한 재료"). 재작성문을 구분 없이 같은 테이블에 넣으면 기계가 쓴 문장이
-- 사람 질문에 섞이고, 그 코퍼스로 만든 평가셋은 자기 재작성기를 채점하게 된다.
-- 기본값이 'user' 인 이유: 지금까지 쌓인 행은 전부 사람이 친 것이다.
ALTER TABLE search_query_text ADD COLUMN IF NOT EXISTS kind TEXT NOT NULL DEFAULT 'user';
