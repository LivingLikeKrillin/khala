"""문서 생애주기 프리미티브 — REAL Postgres.

SPEC-nexus-document-lifecycle §4.1(hold) · §4.2(unsupersede, 체인 가드, 원장).

여기서 고정하는 불변식:
  1. 사람이 숨긴 문서(hold)는 다음 동기화가 되살리지 않는다.
  2. 재조정이 내린 문서(hold=false)는 페이지가 돌아오면 여전히 되살아난다.
  3. supersession 체인은 역순으로만 풀린다 — v1 을 되살려 v3 와 공존시키지 않는다.
  4. supersede/unsupersede 는 상태 변경과 **같은 트랜잭션**에서 원장 행 하나를 남긴다.
"""

from __future__ import annotations

import os

import pytest

from nexus.rid import chunk_rid

pytestmark = pytest.mark.skipif(not os.getenv("NEXUS_TEST_DB_URL"), reason="NEXUS_TEST_DB_URL 필요")

_TENANT = "acme"
_V1 = "doc_v1v1v1v1v1v1"
_V2 = "doc_v2v2v2v2v2v2"
_V3 = "doc_v3v3v3v3v3v3"
_NOTION = "doc_notionnotion"

_C_V1_CUR = chunk_rid(_V1, "", 0)
_C_V1_OLD = chunk_rid(_V1, "", 1)


async def _seed(conn) -> None:
    async def doc(rid, uri, status, chash, superseded_by="", hold=False):
        await conn.execute(
            "INSERT INTO documents (rid, tenant, source_uri, hash, content_hash, status, "
            "superseded_by, hold, title) VALUES ($1,$2,$3,$4,$4,$5::resource_status,$6,$7,$8)",
            rid, _TENANT, uri, chash, status, superseded_by, hold, uri,
        )

    await doc(_V1, f"{_TENANT}:v1.md", "active", "h1")
    await doc(_V2, f"{_TENANT}:v2.md", "active", "h2")
    await doc(_V3, f"{_TENANT}:v3.md", "active", "h3")
    await doc(_NOTION, f"{_TENANT}:ext-notion-pageA.md", "active", "hn")

    async def chunk(rid, doc_rid_, status, chash):
        await conn.execute(
            "INSERT INTO chunks (rid, tenant, source_uri, doc_rid, chunk_text, status, hash) "
            "VALUES ($1,$2,'u',$3,'본문',$4::resource_status,$5)",
            rid, _TENANT, doc_rid_, status, chash,
        )

    await chunk(_C_V1_CUR, _V1, "active", "h1")       # 현재 세대
    await chunk(_C_V1_OLD, _V1, "superseded", "h0")   # 낡은 세대 — 되살아나면 안 된다


@pytest.fixture
async def seeded(db_pool):
    from nexus import db
    from nexus.sources.schema import ensure_schema  # noqa: F401  (003 은 lifecycle 스키마)

    db._pool = db_pool
    async with db_pool.acquire() as con:
        from nexus.documents.schema import ensure_lifecycle_schema
        await ensure_lifecycle_schema(con)
        await con.execute("TRUNCATE documents, chunks, doc_supersession_events CASCADE")
        await _seed(con)
    yield
    db._pool = None


# ── §4.2 unsupersede ──────────────────────────────────────────────────────────

async def test_unsupersede_restores_only_the_current_chunk_generation(seeded):
    from nexus import db
    from nexus.lifecycle import unsupersede
    from nexus.supersede import supersede

    await supersede(_V1, _V2, _TENANT)
    assert await unsupersede(_V1, _TENANT, reason="잘못 대체했다") == "unsuperseded"

    row = await db.fetch_one("SELECT status, superseded_by FROM documents WHERE rid=$1", _V1)
    assert row["status"] == "active" and row["superseded_by"] == ""

    cur = await db.fetch_one("SELECT status FROM chunks WHERE rid=$1", _C_V1_CUR)
    old = await db.fetch_one("SELECT status FROM chunks WHERE rid=$1", _C_V1_OLD)
    assert cur["status"] == "active"
    assert old["status"] == "superseded"          # 죽은 텍스트는 죽은 채로


async def test_unsupersede_is_idempotent_and_refuses_non_superseded(seeded):
    from nexus.lifecycle import unsupersede
    from nexus.supersede import supersede

    assert await unsupersede(_V1, _TENANT, reason="r") == "noop"      # active 는 대상 아님
    await supersede(_V1, _V2, _TENANT)
    assert await unsupersede(_V1, _TENANT, reason="r") == "unsuperseded"
    assert await unsupersede(_V1, _TENANT, reason="r") == "noop"


async def test_unsupersede_refuses_a_broken_chain_and_names_the_blocker(seeded):
    """v2→v1, v3→v2 인 상태에서 v1 을 되살리면 v3 와 공존한다 — ADR-0006 엔트로피 1순위 (I-002)."""
    from nexus import db
    from nexus.lifecycle import ChainBroken, unsupersede
    from nexus.supersede import supersede

    await supersede(_V1, _V2, _TENANT)   # v1 → v2
    await supersede(_V2, _V3, _TENANT)   # v2 → v3  (이제 v2 도 superseded)

    with pytest.raises(ChainBroken) as e:
        await unsupersede(_V1, _TENANT, reason="되돌리고 싶다")
    assert _V2 in str(e.value)           # 에이전트가 쓸 rid
    # 사람이 읽는 표면(웹 토스트)에도 이 문장이 그대로 뜬다. rid 만 있으면 아무 말도 안 한 것과 같다.
    assert "v2.md" in str(e.value)       # 막고 있는 문서의 제목
    assert e.value.blocker_title == f"{_TENANT}:v2.md"

    assert (await db.fetch_one("SELECT status FROM documents WHERE rid=$1", _V1))["status"] == "superseded"

    # 역순으로는 풀린다
    assert await unsupersede(_V2, _TENANT, reason="먼저 v2") == "unsuperseded"
    assert await unsupersede(_V1, _TENANT, reason="이제 v1") == "unsuperseded"


async def test_unsupersede_rejects_an_empty_reason_before_any_write(seeded):
    from nexus import db
    from nexus.lifecycle import unsupersede
    from nexus.supersede import supersede

    await supersede(_V1, _V2, _TENANT)
    for bad in ("", "   ", "\n"):
        with pytest.raises(ValueError):
            await unsupersede(_V1, _TENANT, reason=bad)

    assert (await db.fetch_one("SELECT status FROM documents WHERE rid=$1", _V1))["status"] == "superseded"
    assert await db.fetch_val("SELECT count(*) FROM doc_supersession_events WHERE action='unsuperseded'") == 0


# ── §4.2 원장 ─────────────────────────────────────────────────────────────────

async def test_both_directions_append_exactly_one_event(seeded):
    from nexus import db
    from nexus.lifecycle import unsupersede
    from nexus.supersede import supersede

    await supersede(_V1, _V2, _TENANT)
    await unsupersede(_V1, _TENANT, reason="사유 있음")

    rows = await db.fetch_all(
        "SELECT action, superseded_by, reason FROM doc_supersession_events "
        "WHERE rid=$1 ORDER BY id", _V1)
    assert [r["action"] for r in rows] == ["superseded", "unsuperseded"]
    assert rows[0]["superseded_by"] == _V2          # 설정된 rid
    assert rows[1]["superseded_by"] == _V2          # 버려진 rid
    assert rows[1]["reason"] == "사유 있음"


async def test_a_refused_unsupersede_leaves_no_event(seeded):
    from nexus import db
    from nexus.lifecycle import ChainBroken, unsupersede
    from nexus.supersede import supersede

    await supersede(_V1, _V2, _TENANT)
    await supersede(_V2, _V3, _TENANT)
    with pytest.raises(ChainBroken):
        await unsupersede(_V1, _TENANT, reason="r")
    assert await db.fetch_val(
        "SELECT count(*) FROM doc_supersession_events WHERE action='unsuperseded'") == 0


# ── §4.1 hold ─────────────────────────────────────────────────────────────────

async def test_hide_sets_hold_and_restore_clears_it(seeded):
    from nexus import db
    from nexus.documents.lifecycle_ops import hide_document, restore_document

    assert await hide_document(_NOTION, _TENANT) == "hidden"
    row = await db.fetch_one("SELECT status, hold FROM documents WHERE rid=$1", _NOTION)
    assert row["status"] == "soft_deleted" and row["hold"] is True
    assert await hide_document(_NOTION, _TENANT) == "noop"

    assert await restore_document(_NOTION, _TENANT) == "restored"
    row = await db.fetch_one("SELECT status, hold FROM documents WHERE rid=$1", _NOTION)
    assert row["status"] == "active" and row["hold"] is False


async def test_hide_refuses_a_superseded_document(seeded):
    from nexus import db
    from nexus.documents.lifecycle_ops import AlreadySuperseded, hide_document
    from nexus.supersede import supersede

    await supersede(_V1, _V2, _TENANT)
    with pytest.raises(AlreadySuperseded):
        await hide_document(_V1, _TENANT)
    row = await db.fetch_one("SELECT status, hold FROM documents WHERE rid=$1", _V1)
    assert row["status"] == "superseded" and row["hold"] is False


async def test_restore_refuses_a_superseded_document(seeded):
    from nexus.documents.lifecycle_ops import UseUnsupersede, restore_document
    from nexus.supersede import supersede

    await supersede(_V1, _V2, _TENANT)
    with pytest.raises(UseUnsupersede):
        await restore_document(_V1, _TENANT)


async def test_a_held_document_survives_reconciliation(seeded):
    """사람이 숨긴 Notion 문서를, 페이지가 살아 있다는 이유로 동기화가 되살리면 안 된다 (§4.1)."""
    from nexus import db
    from nexus.documents.lifecycle_ops import hide_document
    from nexus.ingest.sources.notion_reconcile import make_reconcile_fn

    await hide_document(_NOTION, _TENANT)
    # 페이지는 여전히 live 다 — 평소라면 revive 대상.
    await make_reconcile_fn()(_TENANT, {"rootA"}, {_NOTION: ["rootA"]})

    row = await db.fetch_one("SELECT status, hold FROM documents WHERE rid=$1", _NOTION)
    assert row["status"] == "soft_deleted" and row["hold"] is True


async def test_a_pruned_document_is_still_revived_when_its_page_returns(seeded):
    """재조정이 내린 문서(hold=false)는 페이지가 돌아오면 되살아난다 — 기존 계약 불변."""
    from nexus import db
    from nexus.ingest.sources.notion_reconcile import make_reconcile_fn
    from nexus.lifecycle import soft_delete

    await soft_delete(_NOTION, _TENANT)          # prune 이 하는 일 (hold 를 세우지 않는다)
    await make_reconcile_fn()(_TENANT, {"rootA"}, {_NOTION: ["rootA"]})

    row = await db.fetch_one("SELECT status, hold FROM documents WHERE rid=$1", _NOTION)
    assert row["status"] == "active" and row["hold"] is False


# ── 컷오버가 기대는 불변식 (SPEC-nexus-design-corpus-cutover §3.2·§3.3) ──────────

async def test_reingesting_a_hidden_document_does_not_revive_it(seeded):
    """⛔ **컷오버 전체가 이 불변식에 걸려 있다.**

    사본 122문서를 `hide` 로 내린 뒤 누가 같은 경로를 다시 적재하면 되살아나는가? 되살아나면
    순서를 짜서 피하려던 **정본·사본 겹침이 배포 뒤에 조용히 재생성**되고, 어떤 완료 조건도
    그것을 안 본다(비평 I-004).

    코드를 읽어 보니 이미 막혀 있었다 — 문서 upsert 의 `SET` 목록에 `status` 가 없다. 하지만
    **읽어서 그렇다고 믿는 것과 검사로 박는 것은 다르다.** 이 리포가 반복해서 데인 자리다.
    """
    from nexus import db
    from nexus.documents.lifecycle_ops import hide_document

    await hide_document(_V1, _TENANT)

    async with db._pool.acquire() as con:
        # 적재 파이프라인과 **같은 upsert 형태**로 재적재한다.
        await con.execute(
            "INSERT INTO documents (rid, tenant, source_uri, hash, content_hash, status, "
            "superseded_by, hold, title) "
            "VALUES ($1,$2,$3,$4,$4,'active'::resource_status,'',false,$5) "
            "ON CONFLICT (rid) DO UPDATE SET hash = EXCLUDED.hash, "
            "content_hash = EXCLUDED.content_hash, title = EXCLUDED.title",
            _V1, _TENANT, f"{_TENANT}:v1.md", "h1-new", "재적재된 제목",
        )
        row = await con.fetchrow(
            "SELECT status::text AS status, hold, title FROM documents WHERE rid = $1", _V1)

    assert row["status"] == "soft_deleted", "재적재가 숨긴 문서를 되살렸다 — 컷오버가 무너진다"
    assert row["hold"] is True, "사람의 결정이 재적재에 지워졌다"
    # 대조군: 내용은 갱신된다. 상태만 안 건드리는 것이지 적재가 죽은 게 아니다.
    assert row["title"] == "재적재된 제목"


async def test_hiding_and_restoring_returns_the_document_exactly(seeded):
    """§3.2 R-3 — **역연산이 있다.** supersede 는 단방향이라 못 쓴다."""
    from nexus import db
    from nexus.documents.lifecycle_ops import hide_document, restore_document

    async with db._pool.acquire() as con:
        before = await con.fetchrow(
            "SELECT status::text AS s, hold FROM documents WHERE rid = $1", _V1)

    await hide_document(_V1, _TENANT)
    await restore_document(_V1, _TENANT)

    async with db._pool.acquire() as con:
        after = await con.fetchrow(
            "SELECT status::text AS s, hold FROM documents WHERE rid = $1", _V1)

    assert (after["s"], after["hold"]) == (before["s"], before["hold"])
