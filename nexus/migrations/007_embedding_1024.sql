-- SPEC-nexus-kure-embedding-swap §4.2
--
-- KURE-v1 은 1024차원이다. `chunks.embedding` 은 `vector(768)` 이라 담을 수 없다.
--
-- **컬럼을 바꾸지 않고 하나 더 둔다.** ALTER 로 갈아치우면 그 순간 모든 벡터가 사라지고, 재임베딩이
-- 끝날 때까지(코퍼스에 따라 시간 단위) 벡터 다리가 캄캄해진다. 컬럼이 둘이면 옛 벡터가 계속
-- 서비스하는 동안 새 벡터가 채워지고, 컷오버와 롤백이 `search.embedding_column` 설정 한 줄이 된다.
--
-- **인덱스는 여기서 만들지 않는다.** ivfflat 의 `lists` 는 행 수에서 나오는데, 지금은 컬럼이 비어
-- 있다. 반쯤 찬 컬럼에 맞춰 사이징하면 존재한 적 없는 코퍼스에 맞춘 인덱스가 된다. 재임베딩이
-- 끝난 뒤 `nexus reembed --create-index` 가 세어서 만든다 (§4.2).
--
-- 멱등.

ALTER TABLE chunks ADD COLUMN IF NOT EXISTS embedding_1024 vector(1024);

-- 옛 컬럼과 인덱스는 **건드리지 않는다** — 그게 롤백이 진짜 복원인 이유다.
