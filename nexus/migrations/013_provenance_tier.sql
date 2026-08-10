-- 013_provenance_tier: 이 텍스트가 **어떻게 존재하게 됐는가** (ADR-0010, SPEC-nexus-screenshot-text-extraction).
--
-- ADR-0010 이 정한 것: 그림에서 기계가 읽은 텍스트는 증거이되 **낮은 등급**이고, 그 등급이 텍스트를
-- 따라다녀야 한다. 지금까지 Nexus 가 색인한 모든 chunk 는 사람이 쓴 텍스트였고, 그래서 "grounded"
-- 는 조용히 "저자가 쓴 문장으로 추적된다" 를 뜻했다. 인용이 약속하는 것이 바뀐다:
--
--     이전  이 문장은 사람이 썼다
--     이후  이 문장이 **어느 종류인지** 밝힌다
--
-- **거버넌스 등급과 다른 축이다.** ADR-0006 의 "doc_type tier derivation stays in Arbiter" 는
-- memo/canonical — 문서가 조직에서 무엇으로 **취급되는가** — 이고 Arbiter 가 유도한다. 이 컬럼은
-- 텍스트가 **어떻게 만들어졌는가**이고 적재 시점에 정해진다. canonical 문서가 기계가 읽은 텍스트를
-- 담을 수 있고, memo 가 전부 사람이 쓴 것일 수 있다.
--
-- 멱등.

-- ── 1. chunk 당 세 필드 (ADR-0010 §3.1 — 등급 하나로는 부족하다) ──────────────
--
-- 등급만 저장한 초안이 비평에 걸렸다. 셋이 다 있어야 하는 이유가 각각 다르다.

-- (a) 어떻게 만들어졌는가.
DO $$
BEGIN
    CREATE TYPE provenance_tier AS ENUM ('authored', 'machine_read');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

-- NOT NULL + 기본 'authored': **부재가 불가능해야 한다.** 읽을 수 없는 소비자가 기계 텍스트를
-- 저자 텍스트로 제시하는 것이 ADR-0010 §4 가 "추출 안 하느니만 못하다" 고 한 결과다.
-- 기존 chunk 는 전부 'authored' 로 백필된다 — 이 결정 이전에 색인된 모든 chunk 에 대해 참이다.
-- (다만 그 주장은 **검증된 것이 아니라 단언**이다: 적재 경로가 여럿이고, ADR-0010 §1 은 기존
--  변환도 저자가 안 쓴 텍스트를 만들 수 있음을 인정한다. ADR 의 Open items 에 그렇게 적혀 있다.)
ALTER TABLE chunks ADD COLUMN IF NOT EXISTS
    provenance_tier provenance_tier NOT NULL DEFAULT 'authored';

-- (b) **무엇이** 만들었는가. ADR-0010 §5 는 추출기 교체를 "마이그레이션" 이라 부르는데,
--     마이그레이션은 **무엇을 무효화할지 셀 수 있어야** 성립한다. 이것 없이는 recall 범위를
--     못 정하고, 문제된 문장이 어느 모델의 주장인지도 못 밝힌다.
--     authored chunk 에서는 빈 문자열이다.
ALTER TABLE chunks ADD COLUMN IF NOT EXISTS
    extractor_identity TEXT NOT NULL DEFAULT '';

-- (c) **원본을 다시 읽을 수 있는가.** ADR-0010 §2 가 기계 텍스트를 받아들이는 근거가
--     "이미지를 원본에서 다시 읽어라" 이고, ADR-0004 는 Nexus 를 저장소가 아니라 색인으로 못박는다.
--     Notion 이미지 URL 은 한 시간이면 만료된다. 바이트 해시는 **어느** 이미지였는지 증명할 뿐
--     가져오지 못하므로, 소스 URI + 블록 id 가 함께 있어야 한다.
ALTER TABLE chunks ADD COLUMN IF NOT EXISTS source_ref TEXT NOT NULL DEFAULT '';

COMMENT ON COLUMN chunks.provenance_tier IS
    '이 텍스트가 어떻게 존재하게 됐는가. authored = 사람이 씀, machine_read = 그림에서 기계가 읽음. '
    '거버넌스 등급(doc_type)과 다른 축이며 그쪽은 Arbiter 가 유도한다 (ADR-0010 §0). '
    'machine_read 를 저자 텍스트와 같은 것으로 제시하면 안 된다.';
COMMENT ON COLUMN chunks.extractor_identity IS
    '{model}/{prompt_sha} — 이 텍스트를 만든 추출기. authored 는 빈 문자열. '
    '추출기 교체 시 무엇을 무효화할지 세는 근거 (ADR-0010 §3.1, §5).';
COMMENT ON COLUMN chunks.source_ref IS
    '원본을 다시 읽기 위한 참조: {source_uri}#{block_id}#{image_sha256}. '
    '이것이 없으면 낮은 등급은 뒤에 아무것도 없는 이름표다 (ADR-0010 §2, §3.1).';

-- 등급별 조회(코퍼스 구성 보고, recall 범위 산정)를 위한 부분 인덱스. authored 가 절대다수다.
CREATE INDEX IF NOT EXISTS idx_chunks_machine_read
    ON chunks (tenant, extractor_identity)
    WHERE provenance_tier = 'machine_read';

-- ── 2. 추출 결과의 **durable** 저장 ────────────────────────────────────────────
--
-- 초안은 이것을 "캐시" 라 부르고 불변식을 그 위에 세웠다. 그러면 척추가 보존 정책에 걸린다:
-- 미스 한 번이 비결정적 판독기를 다시 돌리고, 드리프트한 텍스트가 **바뀌지 않은 신원** 아래로
-- 들어간다 — 신원이 안 움직였기 때문에 정확히 안 보인다. 그래서 eviction 없는 테이블이다.
--
-- **tenant 가 키에 있다.** 바이트가 같은 이미지는 드물지 않다(같은 UI 스크린샷·같은 템플릿).
-- 전역 저장소면 한 테넌트의 추출 텍스트가 — 그 테넌트의 quarantine 이 **거부한 것까지** —
-- 다른 테넌트에게 제공되고, 이미지의 존재 자체가 경계를 넘어 샌다. 중복 추출 비용이 경계의 값이다.
CREATE TABLE IF NOT EXISTS vision_extractions (
    tenant             TEXT NOT NULL,
    image_sha256       TEXT NOT NULL,
    extractor_identity TEXT NOT NULL,
    -- 성공 시 추출 텍스트. 실패 행은 NULL 이고 error 가 채워진다.
    text               TEXT,
    -- 실패도 **기록한다**. 안 그러면 실패한 적재(맨 `![]()`)와 나중의 성공 적재(블록 포함)가
    -- 서로 다른 body 를 만들고 content_hash 가 왕복해, 아무도 안 고친 문서가 수정된 것으로 읽힌다.
    -- fetch 실패와 추출 실패를 함께 담는다 — 만료된 presigned URL 도 같은 증상을 만든다.
    error              TEXT,
    truncated          BOOLEAN NOT NULL DEFAULT false,
    at                 TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant, image_sha256, extractor_identity)
);

COMMENT ON TABLE vision_extractions IS
    '이미지 바이트 → 추출 텍스트, tenant 별. **캐시가 아니라 durable 저장이다** — eviction 없음. '
    '불변식: 같은 (tenant, bytes, extractor_identity) 에 대해 한 번 저장된 결과는 다시 읽어서 '
    '교체되지 않는다 (ADR-0010 §5). 캐시 분실은 성능 사건이어야지 내용 사건이면 안 된다. '
    '유일한 예외는 **삭제**다: 나중에 격리된 내용은 행이 지워진다(재작성이 아니라 제거이므로 '
    '바뀌지 않은 신원 아래로 드리프트한 텍스트가 들어갈 수 없다).';
COMMENT ON COLUMN vision_extractions.error IS
    '실패 사유(fetch 실패 포함). 실패 행은 **끈적하다** — 지우는 것이 명시적 재시도다. '
    '안 그러면 presigned URL 이 협조할 때마다 body 가 바뀐다.';
