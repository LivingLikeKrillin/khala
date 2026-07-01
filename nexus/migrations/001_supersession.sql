-- 001_supersession: 문서 supersession 필드 + 재수집 이벤트 로그 + 엔트로피 신호 뷰
ALTER TABLE documents ADD COLUMN IF NOT EXISTS superseded_by TEXT NOT NULL DEFAULT '';

CREATE TABLE IF NOT EXISTS doc_reingest_events (
  id                BIGSERIAL PRIMARY KEY,
  rid               TEXT NOT NULL,
  tenant            TEXT NOT NULL,
  old_content_hash  TEXT NOT NULL,
  new_content_hash  TEXT NOT NULL,
  at                TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_reingest_tenant_at ON doc_reingest_events(tenant, at);

-- 정규화 title-stem: 확장자/버전토큰/공백 제거 (IMMUTABLE; 버전토큰은 \y 워드바운더리 앵커)
CREATE OR REPLACE FUNCTION norm_title_stem(t TEXT) RETURNS TEXT AS $$
  SELECT btrim(regexp_replace(
           regexp_replace(
             regexp_replace(lower(coalesce(t,'')), '\.(md|txt|pdf|docx?)$', ''),
             '\y(v[0-9]+|final|draft|copy|사본|최종)\y', ' ', 'g'),
           '[[:space:]_-]+', ' ', 'g'))
$$ LANGUAGE sql IMMUTABLE;

CREATE OR REPLACE VIEW v_entropy_signals AS
  SELECT
    (SELECT count(*) FROM doc_reingest_events) AS reingest_overwrite_events,
    (SELECT count(*) FROM documents d1 JOIN documents d2
       ON d1.content_hash = d2.content_hash AND d1.rid < d2.rid
      WHERE d1.status='active' AND d2.status='active' AND d1.content_hash <> '') AS exact_dup_pairs,
    (SELECT count(*) FROM (
        SELECT norm_title_stem(title) AS stem
        FROM documents WHERE status='active'
        GROUP BY norm_title_stem(title) HAVING count(*) > 1
     ) g) AS title_stem_collisions,
    (SELECT count(*) FROM documents WHERE superseded_by <> '') AS supersessions;
