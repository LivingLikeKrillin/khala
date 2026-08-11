-- 016_vision_source_ref: 인용에서 원본 그림으로 돌아가는 길 (SPEC-nexus-vision-source-ref).
--
-- ADR-0010 §2 는 기계가 읽은 텍스트를 코퍼스에 들이는 근거로 **독자가 원본 그림을 다시 읽을 수
-- 있음**을 든다. §3.1 은 재해석 가능한 참조가 없으면 그 등급이 "뒤에 아무것도 없는 이름표" 라고
-- 못박는다.
--
-- `vision.source_ref()` 는 그 문장을 docstring 에 달고 정의돼 있었고 **부르는 곳이 없었다.**
-- 청크 마커에도 블록 id 가 없고, 추출 행에도 없다. 즉 인용을 든 독자도, 시스템도 그림으로
-- 되돌아갈 수 없었다.
--
-- 여기서 두 컬럼을 만든다. 마커에는 조인 키(이미지 해시 앞 16자)만 들어가고 — 본문은 해시되므로
-- 넣는 것은 한 번 비용을 내고 **안정적**이어야 한다 — 긴 참조는 이 행에 산다.
--
-- 유일 인덱스는 **가정이 아니라 강제**다. 16자 핸들이 두 행에 걸리면 인용이 *다른 그림*으로
-- 해석되고, 그것은 못 찾는 것보다 나쁘다.
--
-- 멱등.

ALTER TABLE vision_extractions
    ADD COLUMN IF NOT EXISTS block_id   TEXT NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS source_uri TEXT NOT NULL DEFAULT '';

COMMENT ON COLUMN vision_extractions.block_id IS
    '원본 블록 id — 이것으로 그림을 다시 가져온다. 빈 문자열 = 참조가 기록되지 않음(해석 불가).';
COMMENT ON COLUMN vision_extractions.source_uri IS
    '이 그림이 속한 문서의 canonical uri. block_id 와 함께 source_ref 를 이룬다.';

CREATE UNIQUE INDEX IF NOT EXISTS idx_vision_handle
    ON vision_extractions (tenant, left(image_sha256, 16), extractor_identity);
