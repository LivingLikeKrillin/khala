-- 023_audit_query_hash_stop_writing: 감사 행에 질의 지문을 더 쓰지 않는다.
-- (SPEC-nexus-audit-query-hash §3.3, approved 2026-08-14, 결정 A)
--
-- **왜.** `search_query_text` 는 질문을 평문으로 담고 `a2a_audit.query_sha256` 은 소금 없는
-- `sha256(query)` 였다. 평문에서 해시를 다시 계산하면 `principal` 로 이어지는 **결정적 경로**가
-- 성립한다 — 마지막 홉은 통계가 아니라 정확 일치다.
--
-- **소금은 이것을 못 고친다.** `sha256(tenant‖\0‖q)` 는 테넌트를 아는 사람이면 누구나 다시
-- 계산하고, 테넌트는 같은 표의 컬럼이다. 소금이 막는 것은 *다른 표 해시와의 우연한 값 일치*
-- 이지 **자기가 저장한 평문에서의 재계산**이 아니다. 이 리포는 "소금 쳤으니 안전하다" 를
-- 두 번 적었고 두 번 다 같은 자리에서 틀렸다 (SPEC §1.4).
--
-- **컬럼을 DROP 하지 않는 이유.** 기존 행의 값은 이미 쓰인 감사 기록이고, 감사 기록의 소급
-- 변경은 감사의 성질을 해친다 (SPEC §2). 새 행은 NULL 이다.
--
-- **`''` 가 아니라 NULL 인 이유.** 빈 문자열은 "기록하지 않음" 과 "빈 질의" 를 구별하지
-- 못하는 센티널이고, 그 구별이 사라지면 나중에 이 칸을 읽는 사람이 둘을 합친다.

ALTER TABLE a2a_audit ALTER COLUMN query_sha256 DROP NOT NULL;
ALTER TABLE a2a_audit ALTER COLUMN query_sha256 DROP DEFAULT;

COMMENT ON COLUMN a2a_audit.query_sha256 IS
    '역사적 컬럼. 2026-08-14 이후 행은 NULL — 평문 보존 표에서 재계산해 principal 로 이어지는 '
    '경로였다(SPEC-nexus-audit-query-hash). 새로 쓰지 말 것.';
