-- SPEC-nexus-kure-embedding-swap §4.5
--
-- 임베딩을 영구히 포기한 청크의 명단. **행이지 플래그가 아니다.**
--
-- 컷오버 조건은 "모든 활성 청크가 임베딩됐다" 인데, 한 청크가 영구히 실패하면(과대 입력·깨진
-- 인코딩·OOM) 그 조건이 영원히 안 서고 코퍼스가 절반만 이전된 채 멈춘다. 그렇다고 조용히 빼면
-- 그건 이 작업이 계속 잡아낸 실패 유형 그 자체다 — 내용이 검색에서 사라졌는데 아무도 모르는 상태.
--
-- 그래서 **사람이 이름을 걸고** 빼고, 그 사실이 남는다. `embed_health` 가 이후로 그 수를 보고한다.
-- 재임베딩 CLI 는 waiver 를 만들지 않는다(후보만 보고한다) — 만드는 것은 사람의 명시적 명령이다.
--
-- 멱등.

CREATE TABLE IF NOT EXISTS embed_waivers (
    chunk_rid  TEXT PRIMARY KEY,
    model      TEXT NOT NULL,
    reason     TEXT NOT NULL,          -- 백엔드가 준 메시지 그대로
    waived_by  TEXT NOT NULL,          -- 승인이 쓰는 서명 관례와 같다
    waived_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE embed_waivers IS
    '임베딩을 포기한 청크. 벡터 검색에서 빠진다는 사실을 사람이 서명으로 인정한 기록.';
