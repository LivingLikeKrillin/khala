"""질의 텍스트 보존 (SPEC-nexus-query-text-retention U1).

**이 기능의 실패는 조용하다.** 안 켜졌는데 남는 것도, 켜졌는데 안 남는 것도 아무 증상이 없다.
그래서 여기 검사는 양쪽에서 건다 — 켜졌을 때 남고, **꺼졌을 때 아무것도 건드리지 않는다**.

키 검사가 특히 load-bearing 이다. 초안은 `search_log` 과 같은 해시를 키로 쓰면서 "principal
컬럼이 없으니 사람 로그가 아니다" 라고 적었고, `a2a_audit` 이 `principal` 과 `query_sha256` 을
같은 행에 갖는다는 사실 하나로 그 주장이 무너졌다. 그 실패는 **다른 테이블에** 있었으므로,
이 테이블만 보는 검사로는 원리적으로 못 잡는다.
"""

from __future__ import annotations

import asyncio
import os

import pytest

from nexus.search.query_retention import counters, retain, retention_key

pytestmark = pytest.mark.integration

TENANT = "t_retention"
OTHER = "t_retention_off"


# ── 키: 조인 불가능성 (DB 불필요) ────────────────────────────────────────────

def test_the_key_is_not_the_hash_other_tables_store():
    """`search_log.query_sha256` 과 같아지는 순간 텍스트가 principal 과 이어붙는다."""
    from nexus.search.signals import query_sha256

    q = "낙관적 락은 왜 필요한가"
    assert retention_key(TENANT, q) != query_sha256(q)


def test_the_same_question_in_two_tenants_gets_two_keys():
    q = "락은 언제 잡나"
    assert retention_key("a", q) != retention_key("b", q)


def test_the_separator_keeps_the_tenant_boundary():
    """구분자가 없으면 ('ab','c') 와 ('a','bc') 가 같은 키가 된다 — 격리가 우연에 달린다."""
    assert retention_key("ab", "c") != retention_key("a", "bc")


# ── DB 픽스처 ────────────────────────────────────────────────────────────────
#
# `nexus.db` 의 **전역 풀**을 연다. `db_pool` 픽스처의 별도 asyncpg 풀을 쓰면 `retain()` 이
# 보는 풀과 검사가 보는 풀이 달라져, 앞 테스트가 닫은 루프에 걸려 'Event loop is closed' 로
# 죽는다(실제로 그렇게 4건이 죽었다).

async def _clear(db):
    for t in (TENANT, OTHER):
        await db.execute("DELETE FROM search_query_text WHERE tenant = $1", t)
        await db.execute("DELETE FROM query_retention WHERE tenant = $1", t)


@pytest.fixture
async def db(db_url):
    from nexus import db as dbmod

    os.environ["DATABASE_URL"] = db_url
    await dbmod.get_pool()
    try:
        await _clear(dbmod)
        yield dbmod
        await _clear(dbmod)
    finally:
        await dbmod.close_pool()


async def _enable(db, tenant=TENANT, notice="https://example.invalid/notice", days=90):
    await db.execute(
        "INSERT INTO query_retention (tenant, enabled_by, notice_shown, retain_days) "
        "VALUES ($1,$2,$3,$4)", tenant, "tester", notice, days)


async def _count(db, tenant=TENANT):
    return await db.fetch_val(
        "SELECT count(*) FROM search_query_text WHERE tenant=$1", tenant)


# ── 쓰기: 켜짐/꺼짐 ───────────────────────────────────────────────────────────

async def test_a_tenant_that_never_opted_in_stores_nothing(db):
    assert await retain(TENANT, "저장되면 안 되는 질문") == "off"
    assert await _count(db) == 0


async def test_an_opted_in_tenant_stores_the_question(db):
    await _enable(db)
    assert await retain(TENANT, "파티룸 입장은 어떻게 하나") == "stored"
    row = await db.fetch_one(
        "SELECT query_text, seen_count FROM search_query_text WHERE tenant=$1", TENANT)
    assert row["query_text"] == "파티룸 입장은 어떻게 하나"
    assert row["seen_count"] == 1


async def test_an_opt_in_without_a_notice_retains_nothing_and_is_counted(db):
    """가리킬 수 없는 동의는 동의가 아니다. 그 거부는 세어져야 한다 — 로그는 안 읽힌다."""
    await _enable(db, notice="   ")
    before = counters["refused_no_notice"]
    assert await retain(TENANT, "고지 없이 들어온 질문") == "no_notice"
    assert await _count(db) == 0
    assert counters["refused_no_notice"] == before + 1


async def test_asking_again_counts_but_does_not_restart_the_window(db):
    """`first_seen` 이 밀리면 만료가 영원히 안 온다 — 만료는 그 컬럼을 본다(§3.3)."""
    await _enable(db)
    await retain(TENANT, "같은 질문")
    first = await db.fetch_val(
        "SELECT first_seen FROM search_query_text WHERE tenant=$1", TENANT)
    await retain(TENANT, "같은 질문")
    row = await db.fetch_one(
        "SELECT first_seen, last_seen, seen_count FROM search_query_text WHERE tenant=$1", TENANT)
    assert row["seen_count"] == 2
    assert row["first_seen"] == first
    assert row["last_seen"] >= first
    assert await _count(db) == 1, "같은 질문이 두 행이 되면 seen_count 가 뜻을 잃는다"


async def test_an_opted_out_tenant_does_not_touch_another_tenants_row(db):
    """옵트아웃한 테넌트의 검색이 남의 행을 밀면, 그 배포는 '아무것도 안 남긴다' 가 아니다."""
    await _enable(db)
    await retain(TENANT, "공유되는 질문")
    assert await retain(OTHER, "공유되는 질문") == "off"
    assert await db.fetch_val(
        "SELECT seen_count FROM search_query_text WHERE tenant=$1", TENANT) == 1
    assert await _count(db, OTHER) == 0


# ── 교차 테이블 불변식 ────────────────────────────────────────────────────────

async def test_no_table_carries_the_retention_key_next_to_a_principal(db):
    """이 테이블만 보는 검사로는 못 잡는 실패였다 — 살아 있는 스키마 전체를 훑는다."""
    rows = await db.fetch_all(
        "SELECT table_name, string_agg(column_name, ',') AS cols "
        "FROM information_schema.columns WHERE table_schema='public' GROUP BY table_name")
    identity = {"principal", "principal_id", "user_id", "actor", "subject"}
    seen_key = False
    for r in rows:
        cols = set(r["cols"].split(","))
        if "retention_key" in cols:
            seen_key = True
            assert not (cols & identity), (
                f"{r['table_name']} 이 retention_key 와 신원 컬럼을 함께 갖는다 — "
                "텍스트와 사람이 조인된다")
    assert seen_key, "retention_key 를 가진 테이블이 없다 — 마이그레이션이 안 돌았다"


# ── 검색을 죽이지 않는다 ──────────────────────────────────────────────────────

async def test_a_broken_retention_write_does_not_raise(db, monkeypatch):
    """동의 범위의 곁가지 기록이 답변을 못 내리게 하면 안 된다(§3.5)."""
    await _enable(db)

    async def boom(*a, **k):
        raise RuntimeError("디스크가 꽉 찼다")

    before = counters["failed"]
    # 컨텍스트로 가둔다 — 픽스처 teardown 도 `db.execute` 로 정리하므로, 패치가 테스트 밖까지
    # 살아 있으면 정리가 같이 죽는다(실제로 그렇게 깨졌다).
    with monkeypatch.context() as m:
        m.setattr(db, "execute", boom)
        assert await retain(TENANT, "실패해도 되는 질문") == "failed"
    assert counters["failed"] == before + 1


# ── U2: 만료·철회·노출 ────────────────────────────────────────────────────────

async def _age(db, tenant, days):
    """행을 과거로 민다 — 시간을 기다리지 않고 만료를 재기 위해."""
    await db.execute(
        "UPDATE search_query_text SET first_seen = now() - make_interval(days => $2) "
        "WHERE tenant = $1", tenant, days)


async def test_purge_deletes_by_first_seen_and_keeps_the_rest(db):
    from nexus.search.query_retention import purge

    await _enable(db, days=30)
    await retain(TENANT, "오래된 질문")
    await _age(db, TENANT, 31)
    await retain(TENANT, "새 질문")
    assert await _count(db) == 2

    deleted = await purge(TENANT)
    assert deleted == {TENANT: 1}
    left = await db.fetch_val(
        "SELECT query_text FROM search_query_text WHERE tenant=$1", TENANT)
    assert left == "새 질문"


async def test_purge_reads_first_seen_not_last_seen(db):
    """`last_seen` 기준이면 반복되는 질문이 영원히 안 지워진다 — 정확히 그 질문이 위험하다."""
    from nexus.search.query_retention import purge

    await _enable(db, days=30)
    await retain(TENANT, "계속 물어보는 질문")
    await _age(db, TENANT, 31)
    await retain(TENANT, "계속 물어보는 질문")      # last_seen 은 방금으로 갱신된다
    assert await db.fetch_val(
        "SELECT seen_count FROM search_query_text WHERE tenant=$1", TENANT) == 2
    assert await purge(TENANT) == {TENANT: 1}, "재관측이 만료를 미루면 안 된다"


async def test_purge_treats_orphaned_text_as_expired(db):
    """옵트인 행만 손으로 지우면 텍스트는 적용할 retain_days 가 없어 영원히 남는다."""
    from nexus.search.query_retention import purge

    await _enable(db)
    await retain(TENANT, "철회 뒤 남은 질문")
    await db.execute("DELETE FROM query_retention WHERE tenant=$1", TENANT)
    assert await _count(db) == 1, "여기서 이미 사라지면 이 검사는 아무것도 안 잰다"
    assert await purge() == {TENANT: 1}
    assert await _count(db) == 0


async def test_purge_keeps_text_that_is_still_inside_the_window(db):
    from nexus.search.query_retention import purge

    await _enable(db, days=90)
    await retain(TENANT, "아직 유효한 질문")
    await _age(db, TENANT, 10)
    assert await purge(TENANT) == {}
    assert await _count(db) == 1


async def test_disable_removes_text_and_opt_in_together(db):
    """둘이 갈라지면 철회가 보존이 된다 — 행만 지우면 고아, 텍스트만 지우면 다시 쌓인다."""
    from nexus.search.query_retention import disable

    await _enable(db)
    await retain(TENANT, "지워질 질문")
    assert await disable(TENANT) == 1
    assert await _count(db) == 0
    assert await db.fetch_val(
        "SELECT count(*) FROM query_retention WHERE tenant=$1", TENANT) == 0
    # 그리고 다시 쌓이지 않는다 — 옵트인이 함께 사라졌으므로.
    assert await retain(TENANT, "그 뒤에 들어온 질문") == "off"
    assert await _count(db) == 0


async def test_status_shows_the_oldest_row_and_the_overdue_count(db):
    """안 도는 purge 는 증상이 없다. 이 줄이 그 침묵을 깬다."""
    from nexus.search.query_retention import status

    await _enable(db, days=30)
    await retain(TENANT, "오래된 질문")
    await _age(db, TENANT, 31)
    row = next(r for r in await status() if r["tenant"] == TENANT)
    assert row["stored"] == 1
    assert row["overdue"] == 1
    assert row["oldest"] is not None
    assert row["has_notice"] is True


async def test_status_names_a_tenant_whose_notice_is_missing(db):
    from nexus.search.query_retention import status

    await _enable(db, notice="")
    row = next(r for r in await status() if r["tenant"] == TENANT)
    assert row["has_notice"] is False


async def test_status_names_orphaned_text(db):
    from nexus.search.query_retention import status

    await _enable(db)
    await retain(TENANT, "고아가 될 질문")
    await db.execute("DELETE FROM query_retention WHERE tenant=$1", TENANT)
    row = next(r for r in await status() if r["tenant"] == TENANT)
    assert row.get("orphan") is True and row["stored"] == 1


# ── U3: 내보내기 + provenance 어휘 ───────────────────────────────────────────

async def test_export_writes_the_questions_a_labeller_needs(db, tmp_path):
    import json
    from typer.testing import CliRunner

    from nexus.cli import app

    await _enable(db)
    await retain(TENANT, "자주 묻는 질문")
    await retain(TENANT, "자주 묻는 질문")
    await retain(TENANT, "한 번 물은 질문")

    out = tmp_path / "questions.json"
    # CLI 는 `asyncio.run` 을 쓴다 — 실행 중인 루프 안에서는 못 돈다. 스레드로 돌려서
    # **CLI 경로 그대로** 잰다(우회해서 내부 함수를 직접 부르면 U2 의 배선 사고를 못 잡는다).
    # 전역 풀을 먼저 닫는다: 안 닫으면 CLI 가 이 루프에 묶인 풀을 다른 스레드에서 집어
    # `another operation is in progress` 로 죽는다. CLI 는 자기 풀을 연다.
    await db.close_pool()
    res = await asyncio.to_thread(
        CliRunner().invoke, app,
        ["query-text", "export", "--tenant", TENANT, "--out", str(out)])
    assert res.exit_code == 0, res.output
    rows = json.loads(out.read_text(encoding="utf-8"))
    assert [r["query"] for r in rows] == ["자주 묻는 질문", "한 번 물은 질문"], "빈도 순이어야 한다"
    assert rows[0]["seen_count"] == 2
    assert {"first_seen", "last_seen"} <= set(rows[0])


async def test_export_can_skip_one_off_questions(db, tmp_path):
    import json
    from typer.testing import CliRunner

    from nexus.cli import app

    await _enable(db)
    await retain(TENANT, "두 번 물은 질문")
    await retain(TENANT, "두 번 물은 질문")
    await retain(TENANT, "한 번만 물은 질문")
    out = tmp_path / "q.json"
    await db.close_pool()
    await asyncio.to_thread(
        CliRunner().invoke, app,
        ["query-text", "export", "--tenant", TENANT, "--out", str(out), "--min-count", "2"])
    rows = json.loads(out.read_text(encoding="utf-8"))
    assert [r["query"] for r in rows] == ["두 번 물은 질문"]


def test_the_label_gate_knows_where_a_query_came_from():
    """자유 문자열이면 `from_user_query` 와 `from_user_queries` 가 나란히 살 수 있고,
    그러면 "저술된 질의와 실사용 질의를 영원히 구별한다" 가 오타에 달린 약속이 된다."""
    import copy

    from scripts.ko_eval_labels import DEFAULT_LABELS, DiskPack, check, load
    from scripts.ko_eval_pack import DEFAULT_PACK_DIR

    labels = load(DEFAULT_LABELS)
    pack = DiskPack(DEFAULT_PACK_DIR)
    assert check(labels, pack) == [], "바닥값이 이미 깨져 있으면 이 검사는 아무것도 안 잰다"

    real = copy.deepcopy(labels)
    real["queries"][0]["provenance"] = "from_user_query"
    assert check(real, pack) == [], "실사용 질문에서 온 라벨은 게이트를 통과해야 한다"

    typo = copy.deepcopy(labels)
    typo["queries"][0]["provenance"] = "from_user_queries"
    problems = check(typo, pack)
    assert any("provenance" in p for p in problems), "오타가 조용히 통과하면 구별이 무너진다"
