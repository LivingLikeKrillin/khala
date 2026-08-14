-- 025_vector_provenance: 벡터 출처를 **컬럼별로** 적는다.
-- (SPEC-nexus-embedding-provenance-grain §3.1, approved 2026-08-14, 안 B)
--
-- **무엇이 틀렸나.** `chunks.embed_model` 은 행당 한 칸인데 벡터는 컬럼 둘(`embedding` 768 ·
-- `embedding_1024`)에 산다. 쓰기 경로가 `{col}` 은 바꾸면서 라벨은 같은 칸에 쓴다:
--
--     UPDATE chunks SET {col} = $1::vector, embed_model = $2 ...
--
-- 그래서 라벨은 **마지막에 쓴 컬럼의 것**이고 다른 컬럼에 대해서는 거짓이다. 2026-08-14 실측
-- (정책 필터 적용): `default` 309행 중 **111행이 `nomic-embed-text` 라벨을 단 채 1024 벡터를
-- 갖고 있다** — nomic 은 768차원이라 그 벡터를 만들 수 없다. 혼합세대 경고가 거짓인 이유가
-- 이것이다.
--
-- **왜 정규화 표인가.** `index_generation_events` 가 이미 `column_name` 을 키로 잡고 있고
-- ("컬럼은 왔다 간다"), 컬럼마다 라벨 칸을 다는 설계는 세 번째 컬럼이 생기는 날 같은 개정을
-- 다시 부른다.
--
-- **미상을 추정으로 채우지 않는다.** 기존 `embed_model` 이 어느 컬럼의 것인지 알 방법이 없다
-- (컬럼별 쓰기 시각이 없어서 순서조차 모른다). 추정해 채우면 위 거짓말을 새 표에 복사하는
-- 것이므로 **`model = NULL`(미상)** 로 둔다. 재임베딩이 그 행을 다시 쓰면 그때 실제 모델이
-- 기록된다 — 다만 전량 재임베딩을 일으키는 것은 이 SPEC 에 없으므로 미상은 무기한 남을 수
-- 있고, 그 사실은 SPEC §3.3·§7 에 결정으로 적혀 있다.

CREATE TABLE IF NOT EXISTS chunk_vector_provenance (
    chunk_rid   TEXT NOT NULL,
    -- 어느 벡터 컬럼인가. `index_generation_events.column_name` 과 같은 어휘.
    column_name TEXT NOT NULL,
    -- 그 컬럼의 벡터를 만든 모델. **NULL = 미상** — 모르는 것을 지어내지 않는다.
    model       TEXT,
    written_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (chunk_rid, column_name)
);

COMMENT ON TABLE chunk_vector_provenance IS
    '벡터 컬럼별 출처. chunks.embed_model 이 행당 한 칸이라 컬럼 둘을 설명하지 못한 것을 대체한다.';
COMMENT ON COLUMN chunk_vector_provenance.model IS
    'NULL = 미상. 마이그레이션 시점의 기존 벡터는 전부 미상이다 — 어느 컬럼의 라벨인지 알 수 없어 추정하지 않았다.';

-- 백필: **현재 벡터가 있는 (청크, 컬럼) 마다 미상 한 줄.** `embed_model` 을 옮기지 않는다.
INSERT INTO chunk_vector_provenance (chunk_rid, column_name, model)
SELECT rid, 'embedding', NULL FROM chunks WHERE embedding IS NOT NULL
ON CONFLICT (chunk_rid, column_name) DO NOTHING;

INSERT INTO chunk_vector_provenance (chunk_rid, column_name, model)
SELECT rid, 'embedding_1024', NULL FROM chunks WHERE embedding_1024 IS NOT NULL
ON CONFLICT (chunk_rid, column_name) DO NOTHING;

CREATE INDEX IF NOT EXISTS idx_chunk_vector_provenance_column
    ON chunk_vector_provenance (column_name, model);
