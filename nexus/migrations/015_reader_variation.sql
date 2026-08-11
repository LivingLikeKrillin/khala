-- 015_reader_variation: 판독기가 자기 자신을 반복할 수 있는가 (SPEC-nexus-vision-reproducibility).
--
-- ADR-0010 §5 는 "같은 (바이트, 추출기 신원) → 같은 텍스트" 를 전제로 재추출을 금지하고 신원
-- 변경을 마이그레이션으로 다룬다. 2026-08-11 에 그 전제를 처음 재 봤다:
--
--     gemini-3.6-flash (minimal)   44장 · 두 실행 완전 동일 35/44 · 토큰 변동  3.6%
--     claude-sonnet-4-6 (브리지)   20장 · 두 실행 완전 동일  4/20 · 토큰 변동 84.7%
--                                  (양측 Fisher exact p = 1.3e-5)
--
-- 배포 판독기는 같은 그림을 두 번 읽으면 다른 것을 읽는다. 그러면 `extractor_identity` 는
-- 해석 키가 아니고, 저장된 추출은 그날의 한 번 뽑기다.
--
-- 이 컬럼은 그 사실을 **행 옆에** 적어 둔다. NULL 은 "괜찮다" 가 아니라 **"아무도 안 쟀다"** 이고,
-- 지금 44행이 그 상태다. 외삽해서 채우지 않는다 — 재지 않은 것을 잰 것처럼 적는 것이 이 SPEC 이
-- 고치려는 실수 그 자체다.
--
-- 멱등.

ALTER TABLE vision_extractions
    ADD COLUMN IF NOT EXISTS reader_variation NUMERIC;

-- 제약은 따로 건다: `ADD COLUMN IF NOT EXISTS ... CONSTRAINT` 는 컬럼이 이미 있을 때 제약을
-- 만들지 않으므로, 두 번째 실행에서 제약만 없는 상태가 조용히 남는다.
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'chk_reader_variation') THEN
        ALTER TABLE vision_extractions
            ADD CONSTRAINT chk_reader_variation
            CHECK (reader_variation IS NULL
                   OR (reader_variation >= 0 AND reader_variation <= 1));
    END IF;
END $$;
