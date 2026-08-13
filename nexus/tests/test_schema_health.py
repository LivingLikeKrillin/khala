"""밀린 마이그레이션이 **보이는가** (2026-08-13 파일럿 준비 중 발견).

이 배포는 018 이 빠진 채로 하루를 돌았다. 앱은 멀쩡히 떴고, `query_retention` 이 없는 컬럼을
SELECT 하고, 그 예외는 설계대로 삼켜지고(동의 기록이 답변을 막으면 안 되므로), 아무도 안 읽는
로그에 경고 한 줄이 남았다. **그동안 질문 보존은 죽어 있었다** — 파일럿의 가장 값진 산출물이다.

감지기는 이미 있었다(`scripts.migrate.pending_migrations`). 실패한 것은 **전달**이다.
"""

from __future__ import annotations

from nexus import schema_health as H


async def test_a_current_schema_is_quiet(monkeypatch, tmp_path):
    (tmp_path / "001_a.sql").write_text("-- x", encoding="utf-8")
    monkeypatch.setattr(H, "MIGRATIONS_DIR", tmp_path)

    async def applied(_q):
        return [{"version": "001_a.sql"}]
    monkeypatch.setattr(H.db, "fetch_all", applied)

    assert await H.pending() == []


async def test_a_stale_schema_names_what_is_missing(monkeypatch, tmp_path):
    for name in ("017_a.sql", "018_b.sql", "019_c.sql"):
        (tmp_path / name).write_text("-- x", encoding="utf-8")
    monkeypatch.setattr(H, "MIGRATIONS_DIR", tmp_path)

    async def applied(_q):
        return [{"version": "017_a.sql"}]
    monkeypatch.setattr(H.db, "fetch_all", applied)

    assert await H.pending() == ["018_b.sql", "019_c.sql"]


async def test_the_verdict_comes_from_the_runner_not_a_second_implementation(monkeypatch,
                                                                            tmp_path):
    """판정을 여기서 다시 구현하면 두 판정이 갈라지고, 갈라진 진단은 거짓말을 시작한다."""
    seen = {}
    import scripts.migrate as M

    real = M.pending_migrations

    def spy(files, applied):
        seen["called"] = True
        return real(files, applied)
    monkeypatch.setattr(M, "pending_migrations", spy)

    (tmp_path / "001_a.sql").write_text("-- x", encoding="utf-8")
    monkeypatch.setattr(H, "MIGRATIONS_DIR", tmp_path)

    async def applied(_q):
        return []
    monkeypatch.setattr(H.db, "fetch_all", applied)

    await H.pending()
    assert seen.get("called"), "러너의 판정을 안 쓰고 자체 구현을 돌렸다"


async def test_a_database_without_the_ledger_does_not_crash(monkeypatch, tmp_path):
    """마이그레이션을 한 번도 안 돌린 배포도 여기로 온다 — 진단이 부팅을 죽일 수 없다."""
    monkeypatch.setattr(H, "MIGRATIONS_DIR", tmp_path)

    async def boom(_q):
        raise RuntimeError('relation "schema_migrations" does not exist')
    monkeypatch.setattr(H.db, "fetch_all", boom)

    assert await H.pending() == []


async def test_pending_migrations_are_logged_at_error_not_warning(monkeypatch, tmp_path):
    """warning 은 묻힌다. 이 배포의 739줄짜리 상시 경고가 그 증거다.

    `caplog` 는 이 로그를 못 잡는다 — structlog 는 표준 logging 핸들러를 안 거친다.
    리포의 다른 테스트가 쓰는 `capture_logs` 를 쓴다(같은 함정을 두 번 밟지 않도록).
    """
    from structlog.testing import capture_logs

    (tmp_path / "018_b.sql").write_text("-- x", encoding="utf-8")
    monkeypatch.setattr(H, "MIGRATIONS_DIR", tmp_path)

    async def applied(_q):
        return []
    monkeypatch.setattr(H.db, "fetch_all", applied)

    with capture_logs() as logs:
        await H.log_pending()
    hits = [e for e in logs if e.get("event") == "pending_migrations"]
    assert hits, f"밀린 마이그레이션인데 아무 말도 안 했다: {logs}"
    assert hits[0]["log_level"] == "error", "warning 으로는 묻힌다"
    assert hits[0]["versions"] == ["018_b.sql"], "무엇이 빠졌는지 이름을 대야 고칠 수 있다"


async def test_a_current_schema_says_nothing_at_all(monkeypatch, tmp_path):
    """정상 배포에서 상시 경고를 내면, 진짜 경고가 그 안에 묻힌다."""
    from structlog.testing import capture_logs

    monkeypatch.setattr(H, "MIGRATIONS_DIR", tmp_path)

    async def applied(_q):
        return []
    monkeypatch.setattr(H.db, "fetch_all", applied)

    with capture_logs() as logs:
        await H.log_pending()
    assert [e for e in logs if e.get("event") == "pending_migrations"] == []
