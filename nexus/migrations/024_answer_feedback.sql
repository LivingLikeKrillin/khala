-- 024_answer_feedback: 👍/👎 를 받는다 — **지표가 아니라 결함 신고 채널로**.
-- (SPEC-nexus-answer-feedback §3.3, approved 2026-08-14, 안 B)
--
-- 팀이 5명이라 만족률은 영원히 안 나온다(월 10표 남짓). 그 수로 비율을 계산하는 것은 잡음에
-- 이름을 붙이는 짓이고, 이 리포가 반복한 실패다. 그래서 여기 쌓이는 것은 **수와 사유 코드**뿐이고
-- 비율 산출은 SPEC §5.2 가 문턱을 넘기 전까지 금지한다.
--
-- **텍스트 컬럼이 하나도 없다.** 질의도 답변도 담지 않는다. 조사 아티팩트는 슬랙 스레드에 이미
-- 있고, 이 표는 그곳을 가리키는 포인터(channel_id·message_ts)만 든다.
--
-- **신원 컬럼도 없다.** 초안은 답변 안 중복투표를 막으려 `sha256(answer_key‖user_id)` 를 두려
-- 했는데, `answer_key` 가 DB 에 평문으로 있고 팀이 5명이라 후보 다섯을 해시해 보면 투표자가
-- 특정된다. 소금은 오프라인 대입을 막지 못한다 → 신원 파생값을 아예 두지 않는다(SPEC §3.4).
-- 대가는 명시적이다: 같은 사람의 반복 투표를 못 막고, 한 사람이 다 눌러도 못 본다.

CREATE TABLE IF NOT EXISTS answer_offered (
    tenant         text NOT NULL,
    -- 128비트 CSPRNG. 질의·답변·신원 어느 것에서도 파생되지 않는다 — 이 키로 조인할 수 있는
    -- 것이 아무 데도 없다는 것이 설계의 전부다.
    answer_key     text NOT NULL,
    offered_at     timestamptz NOT NULL DEFAULT now(),
    -- 그때 보여준 고지 문구의 식별자. 슬랙 메시지는 편집·삭제되므로 "그때 무엇을 보여줬나" 를
    -- 나중에 가리킬 수 있어야 한다. orphan 행에서는 모르므로 NULL 이다.
    notice_version text,
    -- 제안 행 없이 투표가 먼저 온 경우. **분모에서 뺀다** — 제안이 아니었던 것을 제안으로
    -- 세면 분모가 부풀고, offered_at 이 발급 시각이 아니라 투표 시각이라 만료도 못 잰다.
    synthesized    boolean NOT NULL DEFAULT false,
    -- 안 B(§3.5): 조사 아티팩트로 가는 포인터. 90일 뒤 NULL 로 지운다 — 이것이 질문자 추정
    -- 경로이고, 수와 사유 코드는 그 뒤에도 남는다(§4 I12).
    channel_id     text,
    message_ts     text,
    PRIMARY KEY (tenant, answer_key)
);

COMMENT ON TABLE answer_offered IS
    '피드백 버튼을 붙여 내보낸 답변 하나 = 한 행. 분모다. 텍스트도 신원도 담지 않는다.';

CREATE TABLE IF NOT EXISTS answer_vote (
    -- **CSPRNG 다. bigserial 이 아니다.** 이 값은 사유 버튼의 value 로 나가고, 사유 UPDATE 의
    -- 가드 셋(verdict='down' · reason IS NULL · 1시간 이내)은 **남의 최근 👎 행에서도 전부
    -- 참**이다. 열거 가능한 id 면 조작된 페이로드가 타인의 투표에 사유를 적는다.
    id         text PRIMARY KEY,
    tenant     text NOT NULL,
    answer_key text NOT NULL,
    verdict    text NOT NULL CHECK (verdict IN ('up', 'down')),
    -- 사유 집합은 스키마가 강제한다. 자유 텍스트 컬럼이 되면 "자유 텍스트를 수집하지 않는다"
    -- 는 비목표와 마찰한다. NULL = 사유 미상 부정(무효표가 아니다 — 분자에 들어간다).
    reason     text CHECK (reason IS NULL OR reason IN
                   ('wrong_evidence', 'not_my_question', 'ignored_format', 'not_found')),
    CONSTRAINT only_down_votes_carry_a_reason CHECK (verdict = 'down' OR reason IS NULL),
    voted_at   timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (tenant, answer_key) REFERENCES answer_offered (tenant, answer_key)
);

COMMENT ON TABLE answer_vote IS
    '투표 하나 = 한 행. INSERT 만 한다 — 덮어쓰면 분모는 남고 분자가 조용히 유실된다.';

CREATE INDEX IF NOT EXISTS idx_answer_vote_tenant ON answer_vote (tenant, voted_at DESC);
CREATE INDEX IF NOT EXISTS idx_answer_offered_age ON answer_offered (tenant, offered_at);
