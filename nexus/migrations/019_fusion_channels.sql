-- 융합에 쓰인 **채널 수** (SPEC-nexus-multi-turn-retrieval §4 I6).
--
-- 멀티턴은 질의 변형을 채널로 얹는다(재작성 + 원문). 채널이 둘이면 RRF 점수의 절대값이
-- 팽창한다 — 순서는 그대로지만 `top_score` 의 크기가 달라진다. 그 값을 절대 임계값으로
-- 쓰는 쪽(신호 분석·게이트)이 U3 이전 행과 이후 행을 **비교 가능한 것으로 착각하지**
-- 않도록, 그 행이 몇 채널로 만들어졌는지 같이 남긴다.
--
-- 1 = 오늘까지의 모든 행(단일 채널). 기본값이 그래서 1 이다.
ALTER TABLE search_log ADD COLUMN IF NOT EXISTS fusion_channels INTEGER NOT NULL DEFAULT 1;
