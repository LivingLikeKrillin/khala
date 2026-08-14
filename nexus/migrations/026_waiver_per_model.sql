-- 026_waiver_per_model: 웨이버는 **모델별**이다.
-- (SPEC-nexus-embedding-provenance-grain §3.4, approved 2026-08-14)
--
-- 웨이버는 *"이 청크를 **이 모델로** 임베딩하는 것을 포기한다"* 는 사람의 서명인데, PK 가
-- `chunk_rid` 하나라 **청크당 한 줄**이었다. 모델을 바꾼 뒤 같은 청크를 다시 포기할 수 없고,
-- nomic 으로 포기한 청크가 KURE 아래에서도 포기된 것처럼 보인다. `model` 칸은 있었지만
-- **키가 아니라서 아무것도 막지 못했다** — `chunks.embed_model` 이 행당 한 칸이라 컬럼 둘을
-- 설명하지 못한 것과 같은 병이고, 그래서 같은 SPEC 이 둘을 함께 고친다.
--
-- **소급 추정이 없다.** 기존 행은 자기 `model` 값을 그대로 쓴다 — 벡터 출처(§3.3)와 달리
-- 여기는 어느 모델에 대한 포기인지가 이미 기록돼 있다.
--
-- ⚠ **스키마만 고치면 증상은 안 고쳐진다.** 증상은 읽기 경로에 산다 — 후보 조회가 활성
-- 모델로 거르지 않으면 옛 웨이버가 새 모델에서도 면제로 잡히고, 그 청크는 영영 재임베딩되지
-- 않은 채 검색에서 빠진다. `reembed.fetch_candidates`/`pending_summary` 가 같은 PR 에서 바뀐다.

ALTER TABLE embed_waivers DROP CONSTRAINT IF EXISTS embed_waivers_pkey;
ALTER TABLE embed_waivers ADD PRIMARY KEY (chunk_rid, model);

COMMENT ON TABLE embed_waivers IS
    '임베딩을 포기한 청크 — **모델별**. 벡터 검색에서 빠진다는 사실을 사람이 서명으로 인정한 기록. '
    '읽는 쪽은 활성 모델로 걸러야 한다: 옛 모델의 서명은 새 모델에 대한 포기가 아니다.';
