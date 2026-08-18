-- 033: 스캔이 세던 한 칸을 **두 사실로** 가른다 (`code_scans`).
--
-- **왜.** `unparsed_files` 는 두 가지를 같이 세고 있었다:
--   ① 읽지 못한 파일 — 그 파일의 심볼이 통째로 없으므로, 문서가 그 이름을 부르면
--      `orphaned`("코드에 없는 이름")로 판정된다. **거짓 드리프트의 원인**이고 조치가 필요하다.
--   ② 선언이 하나도 없는 파일 — `__init__.py`, 스크립트. 완전히 평범한 사실이다.
--
-- 뭉쳐 있는 동안 이 수에는 **경보를 걸 수 없었다**: 걸면 정상 상태에서 영원히 울리고,
-- 안 꺼지는 경보가 진짜 경보를 죽인다는 것이 이 리포가 이미 지불한 값이다
-- (SPEC-nexus-index-completeness §2). 그래서 가른다 — ①에만 ⚠ 를 건다.
--
-- **백필하지 않는다.** 기존 행의 `unparsed_files` 는 두 값의 합이고, 어느 쪽이 얼마인지
-- 아는 방법이 없다. 추정해서 넣으면 그 숫자는 근거가 없다 — 다음 스캔이 채운다.
-- 그때까지 두 컬럼은 NULL 이고, NULL 의 뜻은 "이 스캔은 가르기 전이다" 이지 0 이 아니다.

ALTER TABLE code_scans ADD COLUMN IF NOT EXISTS unreadable_files INTEGER;
ALTER TABLE code_scans ADD COLUMN IF NOT EXISTS no_symbol_files  INTEGER;
