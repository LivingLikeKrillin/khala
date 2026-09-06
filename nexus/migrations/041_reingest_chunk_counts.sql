-- 041 — 재적재가 청크 수를 바꿨는가 (`OPEN.md` A90)
--
-- ⛔ **왜 필요한가.** 2026-09-06 측정(`scripts/rechunk_churn.py`): 청크 rid 이탈의 트리거는
-- 편집 위치가 아니라 **청크 수 변화**다. 작은 편집은 rid 를 하나도 안 바꾸고, 청크를 하나라도
-- 늘리는 편집은 그 지점 뒤를 거의 전부 바꾼다(문서 6건에서 22중 21 · 36중 24 · 15중 14 …).
-- 그리고 그 이탈은 사실상 전량이 낭비다 — 본문이 실제로 바뀐 청크는 매번 1개였다.
--
-- 그래서 **처방을 고르기 전에 남은 미지수**가 이것이다: 청크 수를 바꾸는 편집이 실제로 얼마나
-- 자주 오는가. 드물면 이 낭비는 안 물고, 잦으면 문다. 지금 `doc_reingest_events` 는 콘텐츠
-- 해시 전후만 적고 **청크 수를 안 적어서** 그 질문에 답할 수 없다.
--
-- ⚠ **NULL 은 "안 바뀜" 이 아니라 "기록 안 됨" 이다.** 이 마이그레이션 이전의 81건은 영원히
-- NULL 이고, 그것을 0 으로 채우면 없는 사실을 만들어 낸다. 읽는 쪽이 세 상태를 갈라야 한다 —
-- 안 기록됨 · 같음 · 다름.

ALTER TABLE doc_reingest_events
    ADD COLUMN IF NOT EXISTS chunks_before INTEGER,
    ADD COLUMN IF NOT EXISTS chunks_after  INTEGER;

COMMENT ON COLUMN doc_reingest_events.chunks_before IS
    '재적재 직전 이 문서의 active 청크 수. NULL = 기록 이전(041 이전) 또는 청크 단계에 도달하지 못한 재적재';
COMMENT ON COLUMN doc_reingest_events.chunks_after IS
    '재적재 직후 저장된 청크 수. NULL 의 뜻은 chunks_before 와 같다';

-- 둘 다 있거나 둘 다 없다. 한쪽만 있는 행은 어느 쪽으로도 읽을 수 없다.
ALTER TABLE doc_reingest_events
    DROP CONSTRAINT IF EXISTS reingest_chunk_counts_together;
ALTER TABLE doc_reingest_events
    ADD CONSTRAINT reingest_chunk_counts_together CHECK (
        (chunks_before IS NULL) = (chunks_after IS NULL));

-- 답하려는 질문이 "수가 바뀐 재적재가 몇 건인가" 이므로, 그 조건으로 거르는 부분 인덱스.
CREATE INDEX IF NOT EXISTS idx_reingest_chunk_count_changed
    ON doc_reingest_events (tenant, at)
    WHERE chunks_before IS DISTINCT FROM chunks_after;
