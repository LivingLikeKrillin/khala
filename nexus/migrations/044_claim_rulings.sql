-- 044 — claim 에 **소유자의 판정**을 붙인다
--
-- ⛔ **왜 필요한가 (2026-09-23).** 문서 값과 코드 값이 갈린 것을 답변이 나란히 냈고, 소유자가
-- 어느 쪽이 맞는지 판정했다. 그 판정은 운영자 메모에만 있었다 — 기계가 읽는 자리에 없어서
-- 같은 질문이 오면 답변은 여전히 문서의 낡은 값을 내거나 판정을 사람에게 되물었다(OPEN A27).
-- 판정이 필요한 것이 아픈 것이 아니라 **같은 판정을 매번 다시 하는 것**이 아프다.
--
-- 다섯 칸. `ruled_value` 는 없을 수 있다 — "코드 값 기각, 대체 값 미정" 도 판정이고 그때는
-- `ruling_note` 가 말한다. `ruled_by`·`ruled_on` 은 시드가 강제한다(소유자·날짜 없는 판정은
-- 메모다). 어긋남(코드 현재 값 ≠ 판정)은 저장하지 않고 답변 시점에 코드가 계산한다.
--
-- 멱등: 빈 DB(init.sql 이 이미 칸을 가짐)와 기존 DB 양쪽에서 안전하다.

ALTER TABLE claims ADD COLUMN IF NOT EXISTS ruled_value  TEXT;
ALTER TABLE claims ADD COLUMN IF NOT EXISTS ruled_source TEXT;
ALTER TABLE claims ADD COLUMN IF NOT EXISTS ruled_by     TEXT;
ALTER TABLE claims ADD COLUMN IF NOT EXISTS ruled_on     TEXT;
ALTER TABLE claims ADD COLUMN IF NOT EXISTS ruling_note  TEXT;
