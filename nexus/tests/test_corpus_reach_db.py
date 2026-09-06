"""코퍼스 도달 판정을 **실제 청크**에 걸어 본다 — postgres. NEXUS_TEST_DB_URL 이 필요하다.

판정 규칙 자체는 `test_corpus_reach.py`(순수)가 지킨다. 여기서 보는 것은 SQL 이 실제로
무엇을 세는가다 — 어느 테넌트를 보는가, `ILIKE` 와일드카드가 막혔는가, 검색이 안 보는
상태의 행을 '있다' 로 세지 않는가.

⛔ **왜 파일을 갈랐나.** 처음엔 순수 검사와 한 파일에 두고 DB 픽스처를 `autouse` 로 걸었더니
풀을 여닫는 비용이 순수 검사 다섯에도 붙어 8건이 141초 걸렸다. `*_db.py` 로 가르는 것이
이 리포의 관례이기도 하다.
"""

from __future__ import annotations

import os

import pytest

from nexus import db
from scripts.ko_eval_corpus_reach import needles_in_corpus

pytestmark = pytest.mark.asyncio

_DB = os.getenv("NEXUS_TEST_DB_URL")


@pytest.fixture(autouse=True)
async def _db_pool():
    """`nexus.db` 의 전역 풀을 **이 모듈이 열고 닫는다** (`test_spans_purge_db.py` 와 같은 관례).

    ⛔ **`autouse` 가 관례의 핵심이다.** 첫 판은 요청형 픽스처로 세 검사에만 걸었더니 스위트
    전체에서 뒤따르는 모듈 30건이 죽었다 — 이 파일만 돌리면 초록이라 안 보인다. 그 다음 판은
    반대로 닫기를 지웠더니 풀이 다른 이벤트 루프에 묶인 채 남아 이 파일 안에서 둘이 죽었다.
    **여는 것과 닫는 것은 같은 범위에 있어야 한다.**
    """
    os.environ["DATABASE_URL"] = _DB or ""
    await db.get_pool()
    yield
    await db.close_pool()


async def _seed(tenant: str, text: str) -> None:
    doc = f"doc_{abs(hash((tenant, text))) % 10**9}"
    await db.execute(
        "INSERT INTO documents (rid, tenant, source_uri, hash, content_hash, title, status) "
        "VALUES ($1,$2,'u','h','h','t','active')", doc, tenant)
    await db.execute(
        "INSERT INTO chunks (rid, tenant, source_uri, doc_rid, chunk_text, section_path, "
        "chunk_index, status, hash) VALUES ($1,$2,'u',$3,$4,'root',0,'active','h')",
        f"c_{doc}", tenant, doc, text)


@pytest.mark.skipif(not _DB, reason="NEXUS_TEST_DB_URL 필요")
@pytest.mark.integration
async def test_a_needle_is_found_only_in_the_tenant_that_holds_it(clean_db):
    """⭐ **이것이 A86 의 실물이다** — 사실은 있었고, 묻지 않은 테넌트에 있었다."""
    await _seed("design_docs", "인덱스 이름은 idx_ual_partyroom_event_time 이다")
    pool = await db.get_pool()
    needle = "idx_ual_partyroom_event_time"

    assert await needles_in_corpus([needle], ["default"], pool) == set()
    assert await needles_in_corpus([needle], ["design_docs"], pool) == {needle}
    assert await needles_in_corpus([needle], ["default", "design_docs"], pool) == {needle}


@pytest.mark.skipif(not _DB, reason="NEXUS_TEST_DB_URL 필요")
@pytest.mark.integration
async def test_the_underscore_escape_holds_against_a_real_query(clean_db):
    """⛔ 안 막으면 `a_b` 가 `axb` 를 찾아내고, 없는 사실이 **있다고** 보고된다."""
    await _seed("default", "여기에는 axb 만 있다")
    pool = await db.get_pool()
    assert await needles_in_corpus(["a_b"], ["default"], pool) == set()


@pytest.mark.skipif(not _DB, reason="NEXUS_TEST_DB_URL 필요")
@pytest.mark.integration
async def test_superseded_and_soft_deleted_chunks_do_not_count_as_reach(clean_db):
    """검색이 절대 안 보는 행을 '있다' 로 세면 이 검사가 거짓말을 한다.

    `active` 밖의 상태를 둘 다 확인한다 — `soft_deleted` 만 막고 `superseded` 를 놓치면,
    정정당한 옛 문서가 여전히 '코퍼스에 있다' 로 세어져 이 검사가 정반대를 말한다.
    """
    pool = await db.get_pool()
    # ⛔ 상태마다 **다른 바늘**을 쓴다. 사이에 `TRUNCATE` 를 넣었던 판은 이 파일 밖의 픽스처가
    # 깔아 둔 행까지 지워 스위트 전체를 흔들었다 — 검사는 자기 자리만 건드린다.
    for state, needle in (("soft_deleted", "needlecanary1"), ("superseded", "needlecanary2")):
        await _seed("default", f"{state} 문장에 {needle} 가 있다")
        assert await needles_in_corpus([needle], ["default"], pool) == {needle}
        await db.execute(
            "UPDATE chunks SET status = $1::resource_status WHERE chunk_text LIKE $2",
            state, f"%{needle}%")
        assert await needles_in_corpus([needle], ["default"], pool) == set(), state
