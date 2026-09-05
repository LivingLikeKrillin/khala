-- 040: **단계별 span** — 어느 단계에서 잃었는지를 사후에 물을 수 있게 한다.
--
-- **무엇이 막혔나.** `search_log` 는 요청당 한 행이라 *풀에 못 들어왔다* 와 *융합에서 밀렸다*
-- 와 *프롬프트에 안 실렸다* 가 전부 같아 보인다. 라이브 답이 틀렸을 때 단계를 물으려면 라벨
-- 있는 질의로 재현해야 했다 (SPEC-nexus-stage-spans §1).
--
-- **꺼진 채로 온다.** `spans.enabled` 기본값이 false 다. 이 마이그레이션은 자리를 만들 뿐
-- 아무것도 쌓지 않는다 — 스키마·제약·파괴 경로를 프로덕션 행이 생기기 전에 두들기기 위해서다.
--
-- **보존은 3일**(소유자 결정, SPEC §7). `chunk_rid` 는 남긴다 — 상관 노출을 해상도가 아니라
-- 시간으로 묶는 쪽이 Unit 2 의 청크 단위 귀속을 지킨다.

ALTER TABLE search_log
    ADD COLUMN IF NOT EXISTS spans_expected INTEGER;
COMMENT ON COLUMN search_log.spans_expected IS
    'NULL = 캡처 꺼짐. 값이 있는데 span 행이 0 이면 배치가 통째로 유실된 것이다.';

-- detail 은 스칼라만 담는다. CHECK 에 서브쿼리를 못 쓰므로 IMMUTABLE 함수로 감싼다.
CREATE OR REPLACE FUNCTION jsonb_values_all_scalar(j jsonb) RETURNS boolean
    LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$
    SELECT bool_and(jsonb_typeof(value) NOT IN ('object','array')) IS NOT FALSE
    FROM jsonb_each(j)
$$;

CREATE TABLE IF NOT EXISTS search_span (
    id                   BIGSERIAL PRIMARY KEY,
    search_log_id        BIGINT      NOT NULL REFERENCES search_log(id) ON DELETE CASCADE,
    ts                   TIMESTAMPTZ NOT NULL DEFAULT now(),
    seq                  INTEGER     NOT NULL,
    stage                TEXT        NOT NULL,
    channel              TEXT,
    leg                  TEXT,
    n_in                 INTEGER,
    n_out                INTEGER,
    fired                BOOLEAN     NOT NULL DEFAULT true,
    score_kind           TEXT,
    index_generation     TEXT,
    candidates_expected  INTEGER,
    candidates_cap       INTEGER,
    candidates_purged_at TIMESTAMPTZ,
    detail               JSONB       NOT NULL DEFAULT '{}',
    UNIQUE (search_log_id, seq),
    CONSTRAINT span_stage_known CHECK (stage IN
        ('leg','fusion','diversify','section_fill','packet','answer')),
    CONSTRAINT span_score_kind_known CHECK (score_kind IS NULL OR score_kind IN
        ('ts_rank_cd','cosine_distance','rrf')),
    CONSTRAINT span_leg_fields CHECK (
        (stage = 'leg' AND leg IN ('bm25','vector') AND channel IS NOT NULL AND channel <> '')
     OR (stage <> 'leg' AND leg IS NULL AND channel IS NULL)),
    -- 최상위 타입 검사가 먼저다: jsonb_each 는 object 가 아니면 **런타임 에러**를 내고,
    -- 그러면 깔끔한 제약 위반 대신 배치가 통째로 죽는다.
    CONSTRAINT span_detail_scalar CHECK (
        jsonb_typeof(detail) = 'object' AND jsonb_values_all_scalar(detail))
);

CREATE INDEX IF NOT EXISTS idx_search_span_ts  ON search_span (ts);
CREATE INDEX IF NOT EXISTS idx_search_span_log ON search_span (search_log_id, seq);
-- **AT MOST one** per non-leg stage. "at least one" 은 부분 유니크 인덱스로 표현할 수 없고,
-- writer 불변식과 테스트가 맡는다.
CREATE UNIQUE INDEX IF NOT EXISTS idx_search_span_singleton
    ON search_span (search_log_id, stage) WHERE stage <> 'leg';

CREATE TABLE IF NOT EXISTS search_span_candidate (
    span_id   BIGINT  NOT NULL REFERENCES search_span(id) ON DELETE CASCADE,
    rank      INTEGER NOT NULL,
    chunk_rid TEXT,
    doc_rid   TEXT    NOT NULL,
    raw_score DOUBLE PRECISION,
    dropped   BOOLEAN NOT NULL DEFAULT false,
    -- rank 다. chunk_rid 가 아니다 — 보존 옵션 3 은 chunk_rid 를 지우고, 그러면 행에
    -- 신원이 없어진다.
    PRIMARY KEY (span_id, rank)
);
COMMENT ON COLUMN search_span_candidate.raw_score IS
    '부모 span 의 score_kind 로 해석한다. **span 안에서만 비교 가능**하다 — ts_rank_cd 는 클수록 좋고 cosine_distance 는 작을수록 좋다.';
