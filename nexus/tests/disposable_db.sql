-- 이 DB 는 버려도 된다. 테스트 스위트가 테이블을 TRUNCATE 해도 좋다는 선언.
--
-- 개발 DB 나 운영 DB 에는 **절대** 실행하지 말 것. 이 테이블 하나가 스위트의 파괴 권한이다.
-- (tests/disposable.py, tests/conftest.py 의 세션 가드가 이 테이블만 본다 — URL 은 믿지 않는다.)
CREATE TABLE IF NOT EXISTS _disposable_test_db (
    declared_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
