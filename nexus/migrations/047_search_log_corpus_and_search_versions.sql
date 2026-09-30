-- 이 답이 어떤 코퍼스에서, 어떤 검색 설정으로 나왔는가 (nexus/search/versions.py).
--
-- corpus_version     — 이번 답이 뒤진 테넌트들의 **읽을 수 있는** 문서의 (tenant, rid, content_hash)
--                      를 정렬해 해시한 12 hex. 재적재돼도 내용이 같으면 같은 값이다.
-- search_fingerprint — 임베딩 컬럼 · 모델 · 토크나이저 + `search` 설정 절 전체의 12 hex.
--
-- ⛔ `evidence_fingerprint`(판정자 전용)와 다른 칸이다. 그 칸은 충분성 판정자가 켜진 행에만 채워져서,
-- 판정자가 꺼진 배포에서 최근 12일 609행이 전부 비어 있었다(2026-09-27 실측). 이 두 칸은 **답변 행마다**
-- 채운다. 정의가 다른 값을 같은 칸에 이어 적지 않는다 — 옛 칸은 판정자의 것으로 그대로 둔다.
--
-- 빈 문자열 = 답변 경로가 아니다, 코퍼스를 셀 DB 가 없었다, 또는 이 칸이 생기기 전의 행.
ALTER TABLE search_log ADD COLUMN IF NOT EXISTS corpus_version     TEXT NOT NULL DEFAULT '';
ALTER TABLE search_log ADD COLUMN IF NOT EXISTS search_fingerprint TEXT NOT NULL DEFAULT '';
