"""충분성 기록의 **쓰기 프로토콜** — 실 Postgres 상대.

두 문장을 따로 커밋하는 설계는 DB 없이는 검증되지 않는다. 여기서 재는 것:

    행이 절대 사라지지 않는가 · 좌초가 종결인가 · NULL 의 뜻이 하나인가 · CHECK 가 실재하는가

특히 **행이 사라지지 않는 것**이 이 파일의 이유다. 판정을 먼저 하고 INSERT 하면 멈춘 판정 하나가
search_log 행을 통째로 날리고, v_search_health 와 v_image_gap_signal 이 같이 망가진다. 판정을
잃는 것은 싸고 행을 잃는 것은 싸지 않다.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

pytestmark = pytest.mark.integration

_DB = os.getenv("NEXUS_TEST_DB_URL")


@pytest.fixture
async def pool():
    """nexus.db 모듈 풀. 이 코드가 실제로 쓰는 경로이므로 asyncpg 풀 fixture 가 아니라 이것이다."""
    from nexus import db
    os.environ["DATABASE_URL"] = _DB or ""
    await db.get_pool()
    try:
        yield db
    finally:
        # fire-and-forget 태스크가 아직 풀을 쥐고 있으면, 풀을 닫는 순간 그 태스크가 다음
        # 테스트의 출력 안에서 'pool is closed' 로 터진다. 먼저 비우고 닫는다.
        import asyncio as _a

        from nexus.search import signals as _S
        if _S._background_tasks:
            await _a.gather(*list(_S._background_tasks), return_exceptions=True)
        _S._inflight = 0
        await db.execute("DELETE FROM search_log WHERE tenant LIKE 'suff%'")
        await db.close_pool()


def _sig(tenant="suff_t", path="search_answer"):
    from nexus.search.signals import SearchSignals
    return SearchSignals(
        path=path, tenant=tenant, clearance="INTERNAL", route="hybrid_only",
        query_sha256="x", query_len=1, n_snippets=3, top_score=0.5, n_entities=0,
        graph_requested=False, n_graph_edges=0, no_answer=False, llm_failed=False,
        latency_ms=10,
    )


class _Judge:
    model = "test-model"

    def __init__(self, reply="VERDICT: insufficient\nREASON: r", boom=None):
        self.reply, self.boom, self.calls = reply, boom, 0

    async def generate(self, system, user, max_tokens=4096):
        self.calls += 1
        if self.boom:
            raise self.boom
        return self.reply


async def _row(db, tenant):
    return await db.fetch_one(
        "SELECT sufficiency, sufficiency_at, sufficiency_judge, evidence_fingerprint, "
        "       path, n_snippets FROM search_log WHERE tenant=$1 ORDER BY id DESC LIMIT 1",
        tenant)


async def test_the_check_constraint_exists_and_rejects_an_unknown_value(pool):
    """값 집합이 스키마에 실재해야 한다. 코드에만 있으면 다음 사람이 열한 번째를 넣는다."""
    db = pool
    with pytest.raises(Exception, match="(?i)check|constraint"):
        await db.execute(
            "INSERT INTO search_log (path, sufficiency) VALUES ($1,$2)", "t", "definitely_not_a_value")


async def test_all_ten_values_round_trip(pool):
    db = pool
    values = ["sufficient", "insufficient", "unparseable", "error", "timeout",
              "disabled", "not_applicable", "shed", "pending", "uninstrumented"]
    for v in values:
        await db.execute("INSERT INTO search_log (path, tenant, sufficiency) VALUES ($1,$2,$3)",
                         "rt", "suff_rt", v)
    got = [r["sufficiency"] for r in await db.fetch_all(
        "SELECT sufficiency FROM search_log WHERE tenant='suff_rt' ORDER BY id")]
    assert got == values, "열 값이 서로 구별되어 저장되지 않는다"
    # judged 는 둘뿐이다 — 실패값을 분모에 넣으면 공급자 장애가 근거 부족으로 읽힌다.
    judged = await db.fetch_val(
        "SELECT count(*) FROM search_log WHERE tenant='suff_rt' "
        "AND sufficiency IN ('sufficient','insufficient')")
    assert judged == 2


async def test_off_by_default_writes_the_row_as_disabled(pool, monkeypatch):
    """기본값이 켜져 있으면 업그레이드한 배포가 조용히 공급자를 부르기 시작한다."""
    from nexus.search.signals import JudgeInput, record_search
    monkeypatch.delenv("NEXUS_SUFFICIENCY", raising=False)
    j = _Judge()
    await record_search(_sig(tenant="suff_off"), await_persist=True,
                        judge_input=JudgeInput("q", "e", {}, j))
    r = await _row(pool, "suff_off")
    assert r["sufficiency"] == "disabled" and r["sufficiency_judge"] == "off"
    assert r["evidence_fingerprint"] is None
    assert j.calls == 0, "꺼져 있는데 판정자를 불렀다"


async def test_search_only_rows_are_not_applicable(pool):
    from nexus.search.signals import record_search
    await record_search(_sig(tenant="suff_na", path="search"), await_persist=True)
    r = await _row(pool, "suff_na")
    assert r["sufficiency"] == "not_applicable" and r["sufficiency_judge"] == "off"


async def test_an_enabled_tenant_gets_a_stored_verdict(pool, monkeypatch):
    from nexus.search.signals import JudgeInput, record_search
    monkeypatch.setenv("NEXUS_SUFFICIENCY", "on")
    monkeypatch.setenv("NEXUS_SUFFICIENCY_TENANTS", "suff_on")
    j = _Judge("VERDICT: insufficient\nREASON: 표에 그 값이 없다")
    await record_search(_sig(tenant="suff_on"), await_persist=True,
                        judge_input=JudgeInput("q", "e", {}, j))
    r = await _row(pool, "suff_on")
    assert r["sufficiency"] == "insufficient" and j.calls == 1
    assert r["sufficiency_judge"].count("/") == 2
    assert len(r["evidence_fingerprint"].strip()) == 8
    assert r["sufficiency_at"] is not None


async def test_a_raising_judge_still_leaves_the_row_and_records_error(pool, monkeypatch):
    """판정 실패가 행을 pending 에 영원히 남기면 좌초와 구별되지 않는다."""
    from nexus.search.signals import JudgeInput, record_search
    monkeypatch.setenv("NEXUS_SUFFICIENCY", "on")
    monkeypatch.setenv("NEXUS_SUFFICIENCY_TENANTS", "suff_err")
    await record_search(_sig(tenant="suff_err"), await_persist=True,
                        judge_input=JudgeInput("q", "e", {}, _Judge(boom=RuntimeError("down"))))
    r = await _row(pool, "suff_err")
    assert r["sufficiency"] == "error" and r["n_snippets"] == 3


async def test_a_broken_prologue_keeps_the_row_as_uninstrumented(pool, monkeypatch):
    """**이 파일의 핵심.** 계측기가 고장 나도 search_log 행은 남아야 한다 — 안 그러면 낡은
    NEXUS_EMBEDDING_COLUMN 하나가 v_search_health 를 조용히 갉아먹는다.

    그리고 그 행은 NULL 이 아니라 `uninstrumented` 다: NULL 은 '이 마이그레이션 이전 행' 만
    뜻해야 하고, 장애가 거기 숨으면 뷰가 건너뛰라고 배운 값 안에 숨는 것이다.
    """
    from nexus.search import signals as S
    monkeypatch.setenv("NEXUS_SUFFICIENCY", "on")
    monkeypatch.setenv("NEXUS_SUFFICIENCY_TENANTS", "suff_broken")

    def _boom(cfg):
        raise RuntimeError("stale NEXUS_EMBEDDING_COLUMN")

    monkeypatch.setattr(S, "evidence_fingerprint", _boom)
    await S.record_search(_sig(tenant="suff_broken"), await_persist=True,
                          judge_input=S.JudgeInput("q", "e", {}, _Judge()))
    r = await _row(pool, "suff_broken")
    assert r is not None, "계측기 고장이 search_log 행을 통째로 날렸다"
    assert r["sufficiency"] == "uninstrumented" and r["sufficiency_judge"] == "off"
    assert r["n_snippets"] == 3, "나머지 신호는 그대로 들어가야 한다"
    assert S._inflight == 0, "프롤로그 실패 경로에서 슬롯이 샜다"


async def test_a_stranded_row_cannot_be_resurrected_by_a_late_verdict(pool):
    """'재시도 없음, 회수 없음' 이 문장이 아니라 불변식이어야 한다."""
    db = pool
    from nexus.search.signals import STRANDED_SECONDS
    rid = await db.fetch_val(
        "INSERT INTO search_log (path, tenant, sufficiency, sufficiency_at) "
        "VALUES ($1,$2,'pending', now() - make_interval(secs => $3)) RETURNING id",
        "late", "suff_late", float(STRANDED_SECONDS + 60))
    await db.execute(
        "UPDATE search_log SET sufficiency=$1 WHERE id=$2 AND sufficiency='pending' "
        "AND sufficiency_at > now() - make_interval(secs => $3)",
        "sufficient", rid, float(STRANDED_SECONDS))
    still = await db.fetch_val("SELECT sufficiency FROM search_log WHERE id=$1", rid)
    assert still == "pending", "좌초로 선언된 행을 뒤늦은 판정이 되살렸다"


async def test_the_insert_lands_before_the_judge_runs(pool, monkeypatch):
    """판정을 먼저 하고 INSERT 하면 멈춘 판정이 행을 통째로 날린다. 순서를 단언한다."""
    db = pool
    from nexus.search.signals import JudgeInput, record_search
    monkeypatch.setenv("NEXUS_SUFFICIENCY", "on")
    monkeypatch.setenv("NEXUS_SUFFICIENCY_TENANTS", "suff_order")
    seen = {}

    class _Peek(_Judge):
        async def generate(self, system, user, max_tokens=4096):
            seen["row"] = await db.fetch_one(
                "SELECT sufficiency FROM search_log WHERE tenant='suff_order' ORDER BY id DESC LIMIT 1")
            return await super().generate(system, user, max_tokens)

    await record_search(_sig(tenant="suff_order"), await_persist=True,
                        judge_input=JudgeInput("q", "e", {}, _Peek()))
    assert seen["row"] is not None, "판정이 도는 동안 행이 아직 없었다"
    assert seen["row"]["sufficiency"] == "pending"
