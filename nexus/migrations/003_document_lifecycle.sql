-- SPEC-nexus-document-lifecycle §4.1 · §4.2
--
-- 멱등 DDL — 빈 DB(init.sql 직후)와 기존 DB 양쪽에서 안전.

-- hold: 사람이 "이 문서는 검색에 있으면 안 된다" 고 결정했다는 표시. status 와 직교한다.
-- 재조정은 hold=true 인 문서를 절대 되살리지 않는다. 이게 없으면 사람이 손으로 숨긴 Notion
-- 문서를 다음 동기화가 조용히 되살린다(그 페이지는 여전히 live 이므로).
ALTER TABLE documents ADD COLUMN IF NOT EXISTS hold BOOLEAN NOT NULL DEFAULT false;

-- 숨김/prune 목록 조회용. active 만 보는 기존 인덱스로는 못 찾는다.
CREATE INDEX IF NOT EXISTS idx_doc_hold ON documents (tenant, status, hold);

-- supersession 의 append-only 원장.
--
-- v_entropy_signals.supersessions 는 `superseded_by <> ''` 를 **현재 상태에서** 세므로
-- unsupersede 가 그 수치를 자동으로 되돌린다(낡은 값이 남지 않는다). 빠져 있던 것은
-- **되돌림 그 자체의 기록**이다 — 거버넌스 행위를 취소했는데 흔적이 없었다.
-- structlog 은 기록이 아니다. 회전한다.
CREATE TABLE IF NOT EXISTS doc_supersession_events (
    id            BIGSERIAL PRIMARY KEY,
    rid           TEXT NOT NULL,
    tenant        TEXT NOT NULL,
    action        TEXT NOT NULL CHECK (action IN ('superseded', 'unsuperseded')),
    superseded_by TEXT NOT NULL DEFAULT '',   -- 설정된 rid, 또는 버려진 rid
    reason        TEXT NOT NULL DEFAULT '',
    at            TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_supersession_events_rid
    ON doc_supersession_events (tenant, rid, at);
