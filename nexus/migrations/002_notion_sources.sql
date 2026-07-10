-- SPEC-nexus-notion-source-console §4.1 · §4.2
--
-- 등록된 Notion root 목록과 동기화 실행 기록. 웹 UI 가 root 를 고쳐야 하므로 config.yaml 이
-- 아니라 DB 가 정본이다. 멱등 DDL — 빈 DB(init.sql 직후)와 기존 DB 양쪽에서 안전.

CREATE TABLE IF NOT EXISTS notion_sources (
    tenant     TEXT NOT NULL,
    root_id    TEXT NOT NULL,                    -- canonical dashed page id
    label      TEXT NOT NULL DEFAULT '',
    added_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant, root_id)
);

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'sync_status') THEN
        CREATE TYPE sync_status AS ENUM ('running', 'succeeded', 'failed', 'refused');
    END IF;
END$$;

CREATE TABLE IF NOT EXISTS notion_sync_runs (
    run_id       TEXT PRIMARY KEY,               -- uuid4 hex
    tenant       TEXT NOT NULL,
    started_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at  TIMESTAMPTZ,
    status       sync_status NOT NULL DEFAULT 'running',
    dry_run      BOOLEAN NOT NULL DEFAULT false,
    reconcile    BOOLEAN NOT NULL DEFAULT false,
    force        BOOLEAN NOT NULL DEFAULT false,
    since        TEXT NOT NULL DEFAULT '',
    walked_roots TEXT[] NOT NULL DEFAULT '{}',
    counts       JSONB NOT NULL DEFAULT '{}'::jsonb,
    plan         JSONB NOT NULL DEFAULT '{}'::jsonb,
    plan_hash    TEXT NOT NULL DEFAULT '',
    reason       TEXT NOT NULL DEFAULT ''
);

-- tenant 당 살아있는 run 은 최대 하나. advisory lock 과 **독립인** 데이터 레벨 백스톱이다:
-- lock 을 우회하는 버그가 생겨도 두 번째 running 행은 여기서 거부된다.
CREATE UNIQUE INDEX IF NOT EXISTS uq_notion_sync_running
    ON notion_sync_runs (tenant) WHERE status = 'running';

CREATE INDEX IF NOT EXISTS idx_notion_sync_latest
    ON notion_sync_runs (tenant, started_at DESC);
