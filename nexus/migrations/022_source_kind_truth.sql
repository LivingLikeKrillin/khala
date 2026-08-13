-- 022: source_kind 가 실제 출처를 말하게 한다 (그 전엔 모든 행이 'git' 이었다).
--
-- Notion 페이지 108건이 `source_kind='git'` 으로 앉아 있었다. 값이 없어서가 아니라 컨버터가
-- 넣은 `wiki` 가 CSF→임시파일→INSERT 세 홉에서 버려지고, 파이프라인이 `'git'` 을 문자열
-- 상수로 박았기 때문이다. 쓰는 쪽은 `nexus/documents/origin.py::source_kind_for` 로 고쳤다.
--
-- 여기서는 **이미 들어앉은 행**을 고친다. 재적재로는 안 고쳐졌다 — ON CONFLICT 갱신 목록에
-- source_kind 가 없었기 때문이고, 그것도 같은 커밋에서 고쳤다.
--
-- 판정 규칙은 `nexus/documents/filters.py::ORIGIN_FILTERS` 와 **같은 술어**다. 두 곳이 다른
-- 답을 내면 콘솔의 출처 필터와 저장된 값이 어긋난다.

UPDATE documents
   SET source_kind = 'wiki'
 WHERE source_uri LIKE '%:ext-notion-%'
   AND source_kind <> 'wiki';

UPDATE documents
   SET source_kind = 'file'
 WHERE source_uri LIKE '%:uploads/%'
   AND source_kind <> 'file';

UPDATE chunks
   SET source_kind = 'wiki'
 WHERE source_uri LIKE '%:ext-notion-%'
   AND source_kind <> 'wiki';

UPDATE chunks
   SET source_kind = 'file'
 WHERE source_uri LIKE '%:uploads/%'
   AND source_kind <> 'file';

-- 리포 파일은 'git' 이 맞으므로 건드리지 않는다. 나머지 rtype(entities/edges/observed_edges)
-- 도 그대로 둔다 — 그쪽은 각자 자기 기본값('manual'·'otel')을 이미 쓰고 있고, 이 결함은
-- 문서/청크 적재 경로의 것이다.
