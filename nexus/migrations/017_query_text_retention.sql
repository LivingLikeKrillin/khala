-- 017_query_text_retention: 질문을 남긴다 — 옵트인으로, 사람과 이어붙일 수 없는 키로.
-- (SPEC-nexus-query-text-retention §3.1~§3.2, approved 2026-08-12)
--
-- `search_log` 은 946행을 쌓고도 질문을 한 문장도 못 준다: `query_sha256` 과 `query_len` 만
-- 남기기 때문이다. 그것이 옳은 기본값이었고 여기서도 기본값은 바뀌지 않는다 — 이 테이블에
-- 행이 없는 테넌트는 아무것도 저장하지 않는다.
--
-- **키가 설계의 핵심이다.** 초안은 `search_log` 과 같은 `query_sha256` 을 키로 삼고 "principal
-- 컬럼을 두지 않으니 사람 로그가 아니다" 라고 적었다. 확인에 쿼리 한 번이 들었다:
--
--     a2a_audit | principal, query_sha256
--
-- 한쪽에 텍스트, 다른 쪽에 신원, 공유하는 해시로 조인 — 설계가 막았다고 주장한 바로 그 로그가
-- 복원된다. 그래서 여기 키는 테넌트로 소금 친 별도 해시이고, 어디에도 같은 값이 없다.
-- 조인할 대상이 없는 것이 약속보다 강하다.

CREATE TABLE IF NOT EXISTS query_retention (
    tenant       text PRIMARY KEY,
    enabled_at   timestamptz NOT NULL DEFAULT now(),
    -- 누가 켰는가. env 변수로는 이 질문에 답할 수 없어서 테이블에 둔다.
    enabled_by   text NOT NULL,
    -- 질문한 사람들에게 **어디서** 알렸는가(슬랙 메시지 링크·온보딩 페이지). 비어 있으면
    -- 쓰기가 거부된다 — 가리킬 수 없는 동의는 동의가 아니다.
    notice_shown text NOT NULL DEFAULT '',
    retain_days  integer NOT NULL DEFAULT 90
);

COMMENT ON TABLE query_retention IS
    '질의 텍스트 보존 옵트인. 행이 없는 테넌트는 아무것도 저장하지 않는다.';

CREATE TABLE IF NOT EXISTS search_query_text (
    tenant        text NOT NULL,
    -- sha256(tenant || E'\0' || query_text). **search_log.query_sha256 과 다른 값이다.**
    retention_key text NOT NULL,
    query_text    text NOT NULL,
    first_seen    timestamptz NOT NULL DEFAULT now(),
    last_seen     timestamptz NOT NULL DEFAULT now(),
    seen_count    integer NOT NULL DEFAULT 1,
    PRIMARY KEY (tenant, retention_key)
);

COMMENT ON COLUMN search_query_text.retention_key IS
    '테넌트로 소금 친 해시. 다른 어느 테이블의 키와도 같지 않다 — principal 과 이어붙일 수 없게.';

-- 만료는 `first_seen` 을 본다(§3.3). `last_seen` 을 보면 반복되는 질문이 영원히 안 지워지고,
-- 반복되는 질문이야말로 내보내질 가능성이 높다.
CREATE INDEX IF NOT EXISTS idx_search_query_text_first_seen
    ON search_query_text (tenant, first_seen);
