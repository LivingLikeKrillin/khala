-- 임베딩이 거부된 청크의 **사실 기록**.
--
-- `index/embed.py` 는 예외를 삼키고 `False` 를 돌려주고, `embed_health` 는 `IS NOT NULL` 만 센다.
-- 그래서 벡터 다리에서 영구히 안 보이는 청크가 어디에도 남지 않았다 — KOREAN_SEARCH_QUALITY.md
-- §3.2 가 기록한 상태. 2026-08-07 에 실물에서 터졌다: 정책 문서의 18,751자 청크를 사이드카가
-- `413 max_seq_length(8192)` 로 거부했다.
--
-- **`embed_waivers` 와 다르다.** waiver 는 사람이 이름을 걸고 **영구히 포기한 결정**이고, 그래서
-- 자동으로 만들어지지 않는다(008 의 주석이 그렇게 못박았다). 이 표는 반대다 — **기계가 낸 사실**
-- 이고, 사람의 판단이 아니며, 다음 시도가 성공하면 **사라져야 한다.** 둘을 한 표에 섞으면
-- "포기했다" 와 "이번에 실패했다" 가 구분되지 않는다.
--
-- 성공 시 삭제는 코드가 한다(embed.py). 낡은 거부 기록이 남으면 멀쩡한 청크가 병들어 보인다.
--
-- 멱등.

CREATE TABLE IF NOT EXISTS embed_refusals (
    chunk_rid   TEXT NOT NULL,
    column_name TEXT NOT NULL,          -- 세대마다 다르게 거부될 수 있다(차원·창 크기가 다르다)
    model       TEXT NOT NULL DEFAULT '',
    reason      TEXT NOT NULL,          -- 백엔드가 준 메시지 그대로. 요약하지 않는다
    chars       INTEGER NOT NULL DEFAULT 0,
    refused_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (chunk_rid, column_name)
);

CREATE INDEX IF NOT EXISTS idx_embed_refusals_at ON embed_refusals (refused_at DESC);

COMMENT ON TABLE embed_refusals IS
    '임베딩 거부의 기계적 사실 기록. 사람의 포기 결정인 embed_waivers 와 구분된다. 재시도 성공 시 삭제.';
