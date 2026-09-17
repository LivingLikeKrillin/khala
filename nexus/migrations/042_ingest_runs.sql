-- 042 — 적재가 **돌았는가** (주기 재적재 배선)
--
-- ⛔ **왜 필요한가 (실측 2026-09-18).** `picasso` 코퍼스를 주기적으로 다시 적재하기로 했다.
-- 그런데 그 잡이 죽었는지 알 방법이 지금 없다. 가진 신호가 전부 **변경 기반**이기 때문이다:
--
--   · `documents.updated_at` — 문서가 바뀔 때만 움직인다
--   · `doc_reingest_events`  — 콘텐츠 해시가 바뀐 문서만 한 줄 남는다
--   · `doc-age`              — `origin_updated_at` 로 보는데 이 코퍼스는 36건 전부 NULL 이다
--                              (파일 적재는 frontmatter 가 시각을 선언할 때만 채운다)
--
-- 코퍼스가 안 바뀐 주는 셋 다 아무것도 안 남긴다. 그래서 **잡이 죽은 것**과 **바뀐 게 없는
-- 것**이 같은 모양이다. 이 리포가 반복해서 데인 자리가 정확히 이것이고
-- (`search_log` 34시간 침묵 · 벡터 색인 0/366 · `jq` 없는 감시), 처방도 이미 정해져 있다 —
-- **"안 측정" 과 "측정한 0" 을 가른다.** 여기서는 *실행 한 건당 한 행*이 그 구분이다.
-- 바뀐 게 없어도 행은 앉는다.
--
-- ⚠ **이 표는 판정하지 않는다.** 임계도, 경보도 없다. `nexus persistence-health` 가
-- 마지막 실행 시각을 사람 앞에 낼 뿐이고, 무엇이 이상한지는 읽는 사람이 정한다
-- (`health/persistence.py` 의 규율 그대로).
--
-- ⚠ 겹침 방지(`notion_sync_runs` 의 부분 유니크 + advisory lock)는 **안 넣었다.** 주기 잡이
-- 순차 반복문이라 자기 자신과 겹칠 수 없고, 사람이 손으로 동시에 돌리는 것은 사람의 선택이다.
-- 필요해지면 그때 `sources/runs_store.py` 의 두 겹을 그대로 가져온다 — 여기 사본을 만들지 말 것.

CREATE TABLE IF NOT EXISTS ingest_runs (
    run_id      TEXT PRIMARY KEY,
    tenant      TEXT NOT NULL,
    -- 무엇을 적재했나. 컨테이너 안 경로다(`/ingest-src`) — 호스트 경로가 아니다.
    source      TEXT        NOT NULL DEFAULT '',
    started_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    -- NULL = 안 끝났다. 크래시한 실행은 이 상태로 남고, 그것이 사실이다.
    finished_at TIMESTAMPTZ,
    status      sync_status NOT NULL DEFAULT 'running',
    -- `IngestResult` 의 수들. 스키마를 안 박는 이유는 세는 것이 자라기 때문이다
    -- (`refused_vendor` 가 2026-09-18 에 그렇게 생겼다).
    counts      JSONB       NOT NULL DEFAULT '{}'::jsonb,
    reason      TEXT        NOT NULL DEFAULT ''
);

COMMENT ON TABLE ingest_runs IS
    '적재 실행 한 건당 한 행. **바뀐 게 없어도 앉는다** — 잡이 죽은 것과 조용한 것을 가르는 유일한 신호';
COMMENT ON COLUMN ingest_runs.status IS
    'running = 안 끝남(크래시 포함) · succeeded · failed · refused(세대 불일치 등, 우리가 막은 것)';
COMMENT ON COLUMN ingest_runs.counts IS
    'IngestResult 요약. found/changed/unchanged/indexed/bm25/vector/quarantined/refused_vendor/failed';

-- 묻는 질문이 "이 테넌트의 마지막 실행은 언제인가" 하나다.
CREATE INDEX IF NOT EXISTS idx_ingest_runs_latest
    ON ingest_runs (tenant, started_at DESC);
