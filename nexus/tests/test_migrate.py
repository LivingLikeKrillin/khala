"""경량 순차 마이그레이션 러너의 순수 로직 — 적용 대상 계산.

init.sql 은 빈 DB 베이스라인. 이후 스키마 델타는 migrations/NNN_*.sql 로 누적되고,
schema_migrations 에 기록된 버전은 건너뛴다(멱등). 파일명이 버전 키, 정렬 순 적용.
"""

from __future__ import annotations

from scripts.migrate import migration_version, pending_migrations


def test_version_is_filename(tmp_path):
    f = tmp_path / "001_add_x.sql"
    f.write_text("", encoding="utf-8")
    assert migration_version(f) == "001_add_x.sql"


def test_pending_excludes_applied_and_sorts(tmp_path):
    for n in ["003_c.sql", "001_a.sql", "002_b.sql"]:
        (tmp_path / n).write_text("", encoding="utf-8")
    pend = pending_migrations(list(tmp_path.glob("*.sql")), {"001_a.sql"})
    assert [p.name for p in pend] == ["002_b.sql", "003_c.sql"]


def test_pending_empty_when_all_applied(tmp_path):
    (tmp_path / "001_a.sql").write_text("", encoding="utf-8")
    assert pending_migrations(list(tmp_path.glob("*.sql")), {"001_a.sql"}) == []


def test_pending_all_when_none_applied(tmp_path):
    for n in ["002_b.sql", "001_a.sql"]:
        (tmp_path / n).write_text("", encoding="utf-8")
    pend = pending_migrations(list(tmp_path.glob("*.sql")), set())
    assert [p.name for p in pend] == ["001_a.sql", "002_b.sql"]
