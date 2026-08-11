-- 014_index_generation: 이 코퍼스는 **어느 임베딩 세대에 있는가** (SPEC-nexus-generation-of-record).
--
-- 2026-08-10 에 같은 리포 코드가 두 곳에서 서로 다른 세대로 해석됐다:
--
--     호스트     column=embedding       model=nomic-embed-text  (768)   출처=config
--     컨테이너   column=embedding_1024  model=KURE-v1           (1024)  출처=env
--
-- 호스트에서 적재하면 배포가 **검색하지 않는 컬럼**으로 들어간다. 두 프로세스 다 자기가 아는 한
-- 올바르게 설정돼 있었고, 어느 쪽도 상대가 존재한다는 것을 알 방법이 없었다. DB 에 "이 코퍼스는
-- 이 세대로 서빙된다" 고 적힌 곳이 없었기 때문이다.
--
-- **append-only 다.** 테넌트당 한 행을 덮어쓰면 세대가 언제 바뀌었는지가 사라지는데, 그것이
-- 이번 사고를 푸는 데 실제로 필요했던 증거다 (§3.1). `doc_reingest_events` 와 같은 이유.
--
-- 현재 세대 = 그 테넌트의 **가장 최근 행**. 행이 없으면 "선언된 적 없음" 이고, 그것은 "기본값"
-- 과 다르다 — 아무도 결정하지 않은 상태라서 적재를 막지 않는다 (§3.2).
--
-- 멱등.

CREATE TABLE IF NOT EXISTS index_generation_events (
    id           BIGSERIAL PRIMARY KEY,
    tenant       TEXT NOT NULL,
    column_name  TEXT NOT NULL,
    model        TEXT NOT NULL,
    declared_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    declared_by  TEXT NOT NULL,
    reason       TEXT NOT NULL DEFAULT ''
);

-- 조회는 언제나 "이 테넌트의 최신 한 건" 이다. 정렬을 인덱스가 준다.
CREATE INDEX IF NOT EXISTS idx_index_generation_tenant
    ON index_generation_events (tenant, id DESC);
