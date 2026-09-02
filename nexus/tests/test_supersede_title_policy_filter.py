"""대체한 문서의 **제목**이 등급·격리·상태 필터를 지나는가 — 진짜 Postgres 에.

⛔ **왜 생겼나 (외부 평가 F3, 2026-09-02).** `nexus/CLAUDE.md` 는 *"모든 SELECT 에 정책
필터를 건다. 예외 없음."* 이라고 적어 두었다. 그런데 대체 문서를 잇는 조인에는 `tenant` 만
있고 **등급·격리·상태가 없었다.** 그 제목은 `describe()` 를 지나 **프롬프트에 들어가고**
(`doc_debt.py` 가 스스로 *"프롬프트에 들어가는 한 줄"* 이라 적는다), 문서 목록 API 의
`superseded_by_title` 로도 나간다.

라이브 실측으로는 누출 조합이 **0건**이었다. 다만 재료는 다 있었다 — 대체 관계 121 ·
`RESTRICTED` 17 · 격리 4. **잠복이지 안전이 아니다.**

⚠ 기존 검사가 왜 못 잡았나: `test_documents_api.py` 는 제목이 **나오는 것**을 단언하고,
`test_doc_debt.py` 는 DB 를 안 쳐서 이 SQL 을 지나간다. 그래서 이 파일은 **행을 심어** 본다 —
누출은 SQL 에 있으므로 실제 DB 로만 잡힌다(`SPEC-nexus-graph-scope-filter` 가 같은 말을 한다).
"""

from __future__ import annotations

import os

import pytest

from nexus.rid import doc_rid
from nexus.search import doc_debt

pytestmark = pytest.mark.skipif(
    not os.getenv("NEXUS_TEST_DB_URL"), reason="NEXUS_TEST_DB_URL 필요")

_TENANT = "supersede_filter_test"
#: 답변에도 목록에도 **절대** 나오면 안 되는 문자열.
_SECRET = "읽을권한없는대체문서제목"


async def _seed(con, key: str, title: str, *, classification="INTERNAL",
                quarantined=False, status="active", superseded_by="") -> str:
    uri = f"{_TENANT}:{key}"
    rid = doc_rid(uri)
    await con.execute(
        "INSERT INTO documents (rid,tenant,source_uri,hash,content_hash,title,status,"
        "classification,is_quarantined,superseded_by) "
        "VALUES ($1,$2,$3,'h','h',$4,$5,$6::classification_level,$7,$8)",
        rid, _TENANT, uri, title, status, classification, quarantined, superseded_by)
    return rid


@pytest.fixture
async def corpus(db_pool):
    """은퇴한 문서 하나와, 그것을 대체한 **읽을 수 없는** 문서 셋."""
    from nexus import db

    previous = db._pool
    db._pool = db_pool
    async with db_pool.acquire() as con:
        await con.execute("DELETE FROM documents WHERE tenant=$1", _TENANT)
        hi = await _seed(con, "hi.md", _SECRET, classification="RESTRICTED")
        q = await _seed(con, "q.md", _SECRET, quarantined=True)
        gone = await _seed(con, "gone.md", _SECRET, status="soft_deleted")
        ok = await _seed(con, "ok.md", "볼 수 있는 대체 문서")
        rids = {
            "by_restricted": await _seed(con, "a.md", "정책 A", superseded_by=hi),
            "by_quarantined": await _seed(con, "b.md", "정책 B", superseded_by=q),
            "by_deleted": await _seed(con, "c.md", "정책 C", superseded_by=gone),
            "by_readable": await _seed(con, "d.md", "정책 D", superseded_by=ok),
        }
        yield rids
        await con.execute("DELETE FROM documents WHERE tenant=$1", _TENANT)
    db._pool = previous


@pytest.mark.asyncio
@pytest.mark.parametrize("case", ["by_restricted", "by_quarantined", "by_deleted"])
async def test_the_title_never_reaches_the_prompt(corpus, case):
    """⛔ 이 파일의 존재 이유. 셋 다 **같은 네 절** 중 하나에 걸려야 한다."""
    debts = await doc_debt.debts_for_docs(_TENANT, "INTERNAL", [corpus[case]])
    debt = debts[corpus[case]]
    assert debt.superseded_by_title == "", f"{case}: 제목이 새어 나왔다"
    assert _SECRET not in doc_debt.describe([debt]), f"{case}: 제목이 프롬프트 줄에 있다"


@pytest.mark.asyncio
@pytest.mark.parametrize("case", ["by_restricted", "by_quarantined", "by_deleted"])
async def test_the_fact_survives_even_when_the_name_cannot(corpus, case):
    """이름은 못 줘도 **은퇴했다는 사실**은 준다 — 그것은 읽는 사람이 보고 있는 문서의 사실이다.

    감추면 낡은 근거를 낡은 줄 모르고 읽는다. 그래서 여기서 갈라 둔다.
    """
    debts = await doc_debt.debts_for_docs(_TENANT, "INTERNAL", [corpus[case]])
    debt = debts[corpus[case]]
    assert debt.superseded is True
    assert "대체된 문서다" in doc_debt.describe([debt])


@pytest.mark.asyncio
async def test_a_readable_replacement_is_still_named(corpus):
    """⛔ **대조군.** 필터가 전부를 지우면 이 기능이 죽은 것이지 고쳐진 것이 아니다."""
    debts = await doc_debt.debts_for_docs(_TENANT, "INTERNAL", [corpus["by_readable"]])
    debt = debts[corpus["by_readable"]]
    assert debt.superseded_by_title == "볼 수 있는 대체 문서"
    assert "볼 수 있는 대체 문서" in doc_debt.describe([debt])


@pytest.mark.asyncio
async def test_raising_the_clearance_reveals_it(corpus):
    """대조군 둘 — 등급을 올리면 보인다. 그래야 위 검사가 '등급 때문' 임이 증명된다."""
    debts = await doc_debt.debts_for_docs(_TENANT, "RESTRICTED", [corpus["by_restricted"]])
    assert debts[corpus["by_restricted"]].superseded_by_title == _SECRET


@pytest.mark.asyncio
async def test_no_clearance_means_no_lookup_not_an_unfiltered_one(corpus):
    """⛔ 빈 등급을 '필터 없음' 으로 읽으면 이 함수가 곧 우회로가 된다."""
    assert await doc_debt.debts_for_docs(_TENANT, "", [corpus["by_restricted"]]) == {}
