-- 이 검색의 융합이 문서 합의를 셌는가 — 요청 칸 `fusion_doc_agreement`(사전 등록 F1)를 행에 남긴다
-- (nexus/search/signals.py · nexus/search/hybrid.py::_add_document_agreement).
--
-- 검색 코드의 변화는 어느 판 칸에도 안 잡힌다 — `search_fingerprint` 는 설정만 보고, 이 처치는 설정이
-- 아니라 요청 칸이다. 그래서 어느 요청이 처치를 받았는지는 이 칸이 아니면 기록에 없다. 대조 측정
-- (T0 / F1 두 판)도, 나중에 소비자가 켰을 때의 지표 비교도 이 칸으로 가른다.
--
-- NULL = 기록 안 함(이 칸이 생기기 전의 행) ≠ false(기록했고 꺼져 있었다).
ALTER TABLE search_log ADD COLUMN IF NOT EXISTS fusion_doc_agreement BOOLEAN;
