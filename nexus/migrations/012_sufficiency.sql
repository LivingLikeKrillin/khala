-- 012_sufficiency: 근거가 질문에 답했는가 — 검색 1건당 판정 1개 (SPEC-nexus-sufficiency-signal).
--
-- **기록만 한다.** 어떤 코드도 이 값으로 분기하지 않고, 답변은 바뀌지 않으며, 비율·문턱·뷰는
-- 만들지 않는다. 소비자(비율/게이트/대시보드)는 별도 기록이고 ADR-0002 로 정상 게이트된다.
--
-- 왜 필요한가: `abstention-never-fires` 는 "근거가 아예 없을 때" 를 조건으로 하는데 BM25 가 항상
-- 무언가를 돌려주므로 한 번도 안 터졌다. 그런데 **근거가 얼마나 자주 부족한지를 물어볼 저장 데이터가
-- 리포에 하나도 없다** — `abstained` 는 컬럼조차 아니고 AnswerResult 의 필드다. 이 마이그레이션이
-- 그 질문을 처음으로 물어볼 수 있게 한다.
--
-- 기본 off. 켜는 것은 배포가 원문 질의·근거 텍스트의 공급자 egress 를 받아들이는 행위다.
--
-- 멱등.

ALTER TABLE search_log ADD COLUMN IF NOT EXISTS sufficiency          TEXT;
ALTER TABLE search_log ADD COLUMN IF NOT EXISTS sufficiency_at       TIMESTAMPTZ;
ALTER TABLE search_log ADD COLUMN IF NOT EXISTS sufficiency_judge    VARCHAR(128);
ALTER TABLE search_log ADD COLUMN IF NOT EXISTS evidence_fingerprint CHAR(8);

-- 열 개 값 + NULL. 실패를 하나로 뭉치지 않는다 — 운영자가 끈 것과 장애가 같은 값이면
-- 어느 창이든 전부 장애로 읽힌다. `pending`/`uninstrumented` 는 특히 **NULL 에 숨지 않기 위해**
-- 존재한다: NULL 은 오직 "이 마이그레이션 이전 행" 만 뜻해야 한다.
DO $$
BEGIN
    ALTER TABLE search_log ADD CONSTRAINT search_log_sufficiency_check CHECK (
        sufficiency IS NULL OR sufficiency IN (
            'sufficient',       -- 근거로 답할 수 있다                        [judged]
            'insufficient',     -- 없다                                        [judged]
            'unparseable',      -- 판정자가 읽을 수 없는 것을 냈다
            'error',            -- 판정자가 예외를 냈다
            'timeout',          -- 판정 호출이 제한을 넘겼다
            'disabled',         -- 이 배포에서 꺼져 있다 (기본값)
            'not_applicable',   -- 답변을 시도하지 않은 검색 행
            'shed',             -- 동시성 상한이 포화됐다
            'pending',          -- 진행 중이거나 좌초됨 — sufficiency_at 과 함께 읽는다
            'uninstrumented'    -- 계측기 프롤로그가 실패했다; 행은 계측 없이 기록됐다
        ));
EXCEPTION WHEN duplicate_object THEN NULL;   -- 멱등
END $$;

COMMENT ON COLUMN search_log.sufficiency IS
    '이 질의의 근거가 답하기 충분했는가에 대한 **한 LLM 의 의견**이다. 시스템의 판정이 아니다. '
    '어떤 코드도 이 값으로 분기하지 않으며 분기해서도 안 된다 (SPEC-nexus-sufficiency-signal §2.2a). '
    '판정자마다 다르므로 sufficiency_judge 없이 읽지 마라. NULL = 이 컬럼 이전의 행.';

COMMENT ON COLUMN search_log.sufficiency_at IS
    '관측이 **시작된** 시각. 종료 시각이 아니다 — UPDATE 는 이 값을 덮지 않는다. '
    'pending 행의 나이를 재는 기준점이며, 300초를 넘긴 pending 은 좌초(stranded)다.';

COMMENT ON COLUMN search_log.sufficiency_judge IS
    '{backend}/{model}/{prompt_sha} — 어느 클라이언트가 텍스트를 밖으로 날랐는지(backend)까지 담는다. '
    '판정자를 부르지 않은 행(disabled·not_applicable·shed·uninstrumented)은 ''off''.';

COMMENT ON COLUMN search_log.evidence_fingerprint IS
    '검색 스택 설정의 sha256 앞 8자 (임베딩 컬럼·모델·토크나이저·k·rrf_k·스니펫 길이). '
    '컷오버나 토크나이저 교체를 사이에 둔 창이 서로 다른 두 측정을 하나로 평균내는 것을 막는다. '
    '**한계**: 설정만 담고 코퍼스 세대는 안 담는다 — 재적재·재임베딩·supersession 은 이 값이 그대로인 채 '
    '판정자가 보는 근거를 바꾼다. 그런 사건을 가로지르는 비교는 ts 로 직접 잘라야 한다.';
