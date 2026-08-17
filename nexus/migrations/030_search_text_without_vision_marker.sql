-- 030: 그림 추출 마커를 **색인 텍스트에서** 걷어낸다 (`search_text` 생성 컬럼).
--
-- **왜.** 마커 한 줄은 기계용 손잡이다 — 인용에서 원본 그림으로 되돌아가는 경로가
-- `chunk_text` 에서 그것을 파싱한다(`ingest/vision_source.py`). 그래서 본문에는 남아야 한다.
-- 그런데 그 줄이 **검색 색인에도 들어가고 있었다**: 라이브 정책 코퍼스 309청크 중 41개(13.3%)가
-- `derived` · `gemini` · `flash` · `img` · 16자 해시를 토큰으로 싣는다. 설계문서·평가팩은 0이다
-- (그림이 없다) — 즉 오염은 **팀이 실제로 묻는 코퍼스에만** 있었다.
--
-- **무엇이 실제로 망가졌나.** 2026-08-18 에 1홉 근거의 어휘로 질의를 넓히는 실험을 했더니 근거에서
-- 가장 흔한 토큰이 그 마커 조각들이라 확장어가 `['flash', '내용', 'derived']` 로 뽑혔다. 실험이
-- 통째로 막혔고, 그 전까지는 아무도 이 오염을 못 봤다.
--
-- **파이썬과 같은 정의를 유지한다.** `utils.get_search_text()` 가 색인·임베딩 경유점이고 이 컬럼은
-- 그 DB 대응물이다. 한쪽만 고치면 두 정의가 갈라지고, 갈라졌다는 사실은 조용하다.
-- `btrim(x)` 가 **공백만** 지운다는 것도 그래서 중요하다: 마커를 지우면 개행이 앞에 남으므로
-- 개행·탭을 명시해야 파이썬의 `.strip()` 과 바이트가 같아진다.
--
-- 사람이 읽는 `> (그림에서 읽은 내용)` 줄은 **남긴다.** 그건 뜻이 있는 문장이다.
--
-- ⚠ 기존 BM25 tsvector 는 파이썬이 써 둔 값이라 이 컬럼을 바꿔도 자동으로 안 바뀐다 —
--    영향받은 청크의 재색인이 필요하다(`index/bm25.py:_run_bm25_indexing`).

ALTER TABLE chunks DROP COLUMN IF EXISTS search_text;

ALTER TABLE chunks ADD COLUMN search_text TEXT GENERATED ALWAYS AS (
    COALESCE(context_prefix, '[' || section_path || ']') || ' ' ||
    btrim(
        regexp_replace(chunk_text, '(?m)^!\[\]\(\)\{:[^}\n]*derived=vision[^}\n]*\}$', '', 'g'),
        E' \t\n\r'
    )
) STORED;

-- pg_trgm fallback 인덱스는 컬럼과 함께 사라졌으므로 다시 만든다.
CREATE INDEX IF NOT EXISTS idx_chunk_trgm ON chunks USING gin (search_text gin_trgm_ops);
