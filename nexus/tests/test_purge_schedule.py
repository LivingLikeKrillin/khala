"""만료 정리가 **스스로 도는가** (SPEC-nexus-query-text-retention §3.3).

`purge` 는 있었지만 아무도 안 불렀다. 안 도는 purge 는 증상이 없다 — 공지에 "90일" 이라고
적는 순간 그것은 지켜야 하는 약속이 되는데, 그 약속이 사람의 기억에 걸려 있었다.
"""

from __future__ import annotations

import asyncio

import pytest

from nexus.search import purge_schedule as P


class _Con:
    def __init__(self, lock_granted=True, purge_raises=False):
        self.lock_granted = lock_granted
        self.purge_raises = purge_raises
        self.unlocked = False

    async def fetchval(self, _q, _k):
        return self.lock_granted

    async def execute(self, _q, _k):
        self.unlocked = True

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False


class _Pool:
    def __init__(self, con):
        self._con = con

    def acquire(self):
        return self._con


def _wire(monkeypatch, con, deleted=None, raises=False, span_deleted=0):
    """반환은 `(tenant_purge_calls, span_purge_calls)`.

    span 후보 만료도 같은 틱에서 돈다(purge_schedule.run_once). 실제 asyncpg 호출을 태우지
    않고 이 유닛에서는 "불렀는가·어떤 인자로·반환값이 접혔는가"만 보도록, `query_retention.purge`
    와 같은 방식으로 갈아 끼운다 — SQL 자체는 test_spans_purge_db.py(통합)가 검증한다.
    """
    async def get_pool():
        return _Pool(con)
    monkeypatch.setattr(P.db, "get_pool", get_pool)

    calls = []

    async def purge(tenant=None):
        calls.append(tenant)
        if raises:
            raise RuntimeError("DB 폭발")
        return deleted or {}

    import nexus.search.query_retention as QR
    monkeypatch.setattr(QR, "purge", purge)

    # 실제 config.yaml 값(배포마다 다를 수 있다)에 이 유닛이 묶이지 않도록 고정값으로 갈아
    # 끼운다 — config 읽기 자체는 별도 시험(test_span_candidate_retain_days_...)이 본다.
    monkeypatch.setattr(P, "span_candidate_retain_days", lambda: 3)

    span_calls = []

    async def purge_candidates(retain_days):
        span_calls.append(retain_days)
        return span_deleted

    import nexus.search.span_store as SS
    monkeypatch.setattr(SS, "purge_candidates", purge_candidates)
    return calls, span_calls


# ── 도는가 ────────────────────────────────────────────────────────────────────

async def test_it_actually_calls_purge(monkeypatch):
    con = _Con()
    calls, span_calls = _wire(monkeypatch, con, deleted={"default": 3})
    assert await P.run_once() == {"default": 3}
    assert calls == [None], "전 테넌트를 대상으로 한 번 돌아야 한다"
    assert span_calls == [3], "span 후보 만료도 같은 틱에서 돌아야 한다"


async def test_the_lock_is_released_even_after_a_failure(monkeypatch):
    """락을 쥔 채 죽으면 다음 주기가 영원히 건너뛴다 — 조용히 멈춘 자동화가 된다."""
    con = _Con()
    _wire(monkeypatch, con, raises=True)
    assert await P.run_once() == {}
    assert con.unlocked is True


async def test_a_second_instance_does_not_double_purge(monkeypatch):
    con = _Con(lock_granted=False)
    calls, span_calls = _wire(monkeypatch, con)
    assert await P.run_once() == {}
    assert calls == [], "락을 못 잡았는데 지웠다"
    assert span_calls == [], "락을 못 잡았는데 span 후보도 지웠다"


async def test_span_candidate_purge_folds_into_the_returned_dict(monkeypatch):
    """⛔ 0 이면 안 접는다 — 옛 배포(spans 미사용)의 반환 모양을 안 건드리려면
    `query_retention` 만 지운 결과와 구분이 안 돼야 한다."""
    con = _Con()
    calls, span_calls = _wire(monkeypatch, con, deleted={"default": 3}, span_deleted=5)
    assert await P.run_once() == {"default": 3, "span_candidates": 5}


async def test_span_candidate_purge_is_omitted_when_nothing_expired(monkeypatch):
    con = _Con()
    _wire(monkeypatch, con, deleted={}, span_deleted=0)
    assert await P.run_once() == {}


async def test_span_candidate_retain_days_reads_config_not_a_hardcoded_three(monkeypatch, tmp_path):
    """`candidate_retain_days` 를 config.yaml 밖에서 읽으면(예: 3 하드코딩) 소유자가 창을
    넓혀도 배포가 못 따라간다 — 그 회귀를 여기서 막는다."""
    cfg = tmp_path / "config.yaml"
    cfg.write_text("spans:\n  candidate_retain_days: 9\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    assert P.span_candidate_retain_days() == 9


async def test_a_failure_never_raises(monkeypatch):
    """정리 작업이 서버를 죽이면 그것은 정리가 아니다."""
    async def boom():
        raise RuntimeError("풀 없음")
    monkeypatch.setattr(P.db, "get_pool", boom)
    assert await P.run_once() == {}


# ── 켜고 끄기 ──────────────────────────────────────────────────────────────────

def test_the_interval_can_be_turned_off(monkeypatch):
    """끄는 방법이 없는 자동화는 사고다."""
    monkeypatch.setenv("NEXUS_RETENTION_PURGE_HOURS", "0")
    assert P.interval_hours() == 0.0
    assert P.start() is None


@pytest.mark.parametrize("raw,expected", [
    ("6", 6.0), ("0.5", 0.5), ("", P.DEFAULT_INTERVAL_HOURS),
    ("스물넷", P.DEFAULT_INTERVAL_HOURS),      # 오타가 자동화를 끄면 안 된다
    ("-3", 0.0),                               # 음수는 끈 것으로 읽는다
])
def test_the_interval_reads_its_env(monkeypatch, raw, expected):
    monkeypatch.setenv("NEXUS_RETENTION_PURGE_HOURS", raw)
    assert P.interval_hours() == expected


def test_the_default_is_daily(monkeypatch):
    monkeypatch.delenv("NEXUS_RETENTION_PURGE_HOURS", raising=False)
    assert P.interval_hours() == 24.0


async def test_the_loop_runs_on_boot_then_waits(monkeypatch):
    """PC 가 켜지면 정리된다 — 정해진 시각의 cron 은 그 시각에 꺼져 있으면 그냥 건너뛴다."""
    ran = []

    async def once():
        ran.append(1)
        return {}
    monkeypatch.setattr(P, "run_once", once)

    task = asyncio.create_task(P.loop(3600.0, startup_delay_s=0.0))
    await asyncio.sleep(0.05)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert ran == [1], "기동 직후 한 번 돌아야 한다"


# ── 배선: 앱이 실제로 켜는가 ────────────────────────────────────────────────────
#
# "함수는 맞는데 아무도 안 부른다" 가 이 리포의 반복 결함이고, `purge` 가 정확히 그 상태였다.
# 그래서 스케줄러가 도는지가 아니라 **앱이 그것을 켜는지**를 건다.

async def test_the_app_starts_the_scheduler_on_boot(monkeypatch):
    started = []

    def fake_start():
        started.append(1)
        return None
    monkeypatch.setattr(P, "start", fake_start)

    from nexus import api

    # lifespan 의 다른 준비 작업은 이 시험의 대상이 아니다 — DB·임베딩·가제티어를 세운다.
    async def noop(*a, **k):
        return None
    for name in ("_log_embedding_coverage", "_bootstrap_gazetteer", "_sweep_orphaned_syncs"):
        monkeypatch.setattr(api, name, noop)
    monkeypatch.setattr(api.db, "get_pool", noop)
    monkeypatch.setattr(api.db, "close_pool", noop)
    monkeypatch.setattr(api.db, "ensure_search_log", noop)
    monkeypatch.setattr(api, "embedding_service_from_config", lambda *a, **k: None)
    monkeypatch.setattr("nexus.schema_health.log_pending", noop)

    async with api.lifespan(api.app):
        pass
    assert started == [1], "앱이 만료 정리 스케줄러를 켜지 않았다"
