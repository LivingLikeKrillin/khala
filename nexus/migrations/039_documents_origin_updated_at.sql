-- 문서 **자신의** 마지막 수정 시각. 원본(Notion 등)이 말하는 값이다.
--
-- ⛔ **`documents.updated_at` 은 우리 적재 시각이다** (실측 2026-09-02). 그래서 그 칸으로는
-- *"문서가 낡았나"* 를 **구조상 물을 수 없다** — 내용이 그대로여도 재적재할 때마다 모든 문서가
-- 새것이 된다. 오늘 그 칸으로 재고 하마터면 "126건 전부 3개월 이내, 문서는 안 낡았다" 고
-- 보고할 뻔했다. 그 수가 말한 것은 **우리가 8월에 적재했다** 뿐이다.
--
-- 값 자체는 이미 오고 있었다 — 노션 커넥터가 `origin_last_edited` 로 frontmatter 에 싣는다.
-- **저장되는 자리가 없었을 뿐이고**, 그래서 코드 전체에서 그 이름이 두 곳에만 나온다.
-- 이 리포가 반복해서 겪은 모양이다: 신호는 만들어지는데 읽을 자리가 없다.
--
-- ⚠ **이 칸은 판정을 안 바꾼다.** 신선도 경고(`documents/staleness.py`)는 오늘과 똑같이
-- 적재 시각으로 돈다. 경고를 바꾸는 것은 사용자가 보는 것을 바꾸는 일이라 별도 결정이다.
-- 여기서 하는 것은 **질문을 물을 수 있게 만드는 것**까지다.
--
-- ⚠ 기존 행은 NULL 이다. 다음 적재에서 채워지고, NULL 은 "모른다" 이지 "새것" 이 아니다 —
-- 읽는 쪽이 그 둘을 갈라야 한다.
ALTER TABLE documents ADD COLUMN IF NOT EXISTS origin_updated_at TIMESTAMPTZ;
CREATE INDEX IF NOT EXISTS idx_documents_origin_updated
    ON documents (tenant, origin_updated_at DESC);
