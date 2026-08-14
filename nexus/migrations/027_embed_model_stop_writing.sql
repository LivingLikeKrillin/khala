-- 027_embed_model_stop_writing: 행 라벨 `chunks.embed_model` 에 더 쓰지 않는다.
-- (SPEC-nexus-embedding-provenance-grain §8 의 두 갈래 중 "COMMENT 를 단다" 쪽)
--
-- **왜.** 벡터는 컬럼 둘(`embedding` 768 · `embedding_1024`)에 사는데 이 라벨은 **행당 한
-- 칸**이다. 쓰기 경로가 `{col}` 은 바꾸면서 라벨은 같은 칸에 덮었으므로, 값은 **마지막에 쓴
-- 컬럼의 것**이고 다른 컬럼에 대해서는 거짓이다. 2026-08-14 실측: `default` 309행 중 111행이
-- 768 모델 라벨을 단 채 1024 벡터를 갖고 있었다 — nomic 은 1024 를 만들 수 없다.
--
-- 025 가 `chunk_vector_provenance` 로 **컬럼별** 출처를 세웠고, 읽는 곳은 전부 그리로 옮겼다.
-- 남은 것은 쓰기뿐이었다 — 아무도 안 읽는 값을, 거짓인 채로, 계속 쓰고 있었다.
--
-- **DEFAULT 를 먼저 지우는 이유.** `'multilingual-e5-base'` 는 INSERT 되는 **모든** 청크에
-- 붙는다. 벡터가 아직 없는 청크도 이 라벨을 달고 들어왔다는 뜻이다. 쓰기 경로만 고치고
-- DEFAULT 를 두면 새 행이 계속 거짓 라벨을 갖는다.
--
-- **이 마이그레이션이 컬럼을 DROP 하지 않는 이유.** 코드와 스키마가 같은 배포에서 함께
-- 움직이는데(`task update` 한 줄), 마이그레이션에는 되돌리기가 없다. 컬럼을 지운 뒤 이미지만
-- 예전 커밋으로 되돌리면 옛 쓰기 경로가 없는 컬럼을 UPDATE 한다 — `index/embed.py` 는 그
-- 예외를 삼켜 거부로 적고 `False` 를 돌려주므로 **임베딩이 조용히 안 되는 배포**가 되고,
-- `index/reembed.py` 는 루프 한가운데서 죽는다. 값이 아니라 그 실패 모양이 비싼 것이다.
-- DROP 은 이 마이그레이션이 배포되고 옛 이미지로 돌아갈 일이 없어진 뒤 별도 회차에서 한다
-- (OPEN.md A4 가 그 방아쇠를 든다).
--
-- **기존 값을 지우지 않는 이유.** 이 회차는 되돌릴 수 있어야 한다. 값은 거짓이지만
-- 아무도 읽지 않고, COMMENT 가 그 사실을 컬럼에 붙여 둔다.

ALTER TABLE chunks ALTER COLUMN embed_model DROP DEFAULT;
ALTER TABLE chunks ALTER COLUMN embed_model DROP NOT NULL;

COMMENT ON COLUMN chunks.embed_model IS
    '역사적 컬럼. 2026-08-15 이후 쓰기 없음(NULL) — 행당 한 칸이라 벡터 컬럼 둘을 설명하지 '
    '못했고 기존 값은 마지막에 쓴 컬럼의 것이다(SPEC-nexus-embedding-provenance-grain). '
    '컬럼별 출처의 정본은 chunk_vector_provenance. 새로 쓰지도, 읽지도 말 것.';
