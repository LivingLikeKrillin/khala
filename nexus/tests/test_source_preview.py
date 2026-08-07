"""등록 전 루트 미리보기 — "이걸 넣으면 무엇이 들어오나".

`POST /sync {dry_run: true}` 는 **등록된** 루트만 걷는다. 루트를 고르는 순간에는 쓸 수 없다:
넣어봐야 알 수 있고, 알려면 넣어야 한다. 코퍼스를 키우려는 사람의 첫 질문이 거기서 끊긴다.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from nexus.sources.preview import IMAGE_ONLY_MAX_CHARS, preview_root, preview_roots


@dataclass
class _Conv:
    markdown: str
    image_count: int = 0
    frontmatter: dict | None = None


@dataclass
class _Ref:
    id: str
    title: str


class _FakeSource:
    """`NotionSource` 의 걷기/변환 표면만 흉내낸다."""

    def __init__(self, pages: dict[str, _Conv], broken: set[str] | None = None,
                 walk_error: Exception | None = None):
        self.pages = pages
        self.broken = broken or set()
        self.walk_error = walk_error

    def live_ids(self):
        if self.walk_error:
            raise self.walk_error
        return set(self.pages)

    def page_ref(self, pid):
        return _Ref(id=pid, title=f"제목 {pid}")

    def fetch_markdown(self, ref):
        if ref.id in self.broken:
            raise RuntimeError("block fetch failed")
        return self.pages[ref.id]


def test_it_separates_real_documents_from_empty_shells():
    """한 루트가 31페이지 중 19건이 목차·껍데기라 12건에서 고갈된 적이 있다. 그 구분이 안 보이면
    루트가 얕은 건지 순회가 얕은 건지 알 수 없다."""
    src = _FakeSource({
        "a": _Conv("실제 정책 본문이 충분히 길게 들어 있다" * 5),
        "b": _Conv("   \n  "),          # 목차/껍데기
        "c": _Conv(""),
        "d": _Conv("또 다른 정책 문서" * 20),
    })
    got = preview_root(src, "root-1")
    assert (got.pages, got.with_body, got.empty) == (4, 2, 2)


def test_an_image_only_page_is_counted_separately_from_a_thin_one():
    """정책 표를 스크린샷으로 붙인 페이지는 검색에 안 걸리는데 경고도 없다. 얇은 문서와 섞으면
    사람이 판단할 수 없으므로 따로 센다."""
    src = _FakeSource({
        "shot": _Conv("![](u)", image_count=3),                     # 그림뿐
        "thin": _Conv("짧지만 그림은 없는 문서"),                     # 그냥 얇음
        "rich": _Conv("본문이 충분한 문서 " * 30, image_count=2),     # 그림 있으나 본문도 있음
    })
    got = preview_root(src, "root-1")
    assert got.with_body == 3
    assert got.image_only == 1, "그림뿐인 것만 센다"
    assert got.images == 5, "이미지 총수는 따로 보고한다"


def test_a_captioned_image_page_stops_counting_as_image_only():
    """캡션을 살린 뒤에는 같은 페이지가 본문을 갖는다 — 그래서 이 지표가 캡션 수정의 효과를 잰다."""
    caption = "그림 3. 환불 승인 흐름 — 신청 후 3영업일 내 승인, 초과 시 자동 반려" * 3
    assert len(caption) > IMAGE_ONLY_MAX_CHARS
    src = _FakeSource({"shot": _Conv(f"![{caption}](u)", image_count=1)})
    assert preview_root(src, "root-1").image_only == 0


def test_a_walk_failure_is_reported_not_swallowed():
    """토큰·권한·오타는 여기서 드러나야 한다 — 0건을 '빈 루트' 로 읽으면 안 된다."""
    got = preview_root(_FakeSource({}, walk_error=PermissionError("unauthorized")), "root-1")
    assert got.pages == 0 and "PermissionError" in got.error


def test_one_unreadable_page_does_not_hide_the_rest():
    src = _FakeSource({"ok": _Conv("본문 " * 40), "bad": _Conv("")}, broken={"bad"})
    got = preview_root(src, "root-1")
    assert got.with_body == 1
    assert got.error, "일부 실패는 보고한다"


def test_each_root_is_walked_separately_so_the_choice_is_informed():
    """합쳐 걸으면 어느 루트가 무엇을 줬는지 알 수 없어 고르는 데 못 쓴다."""
    by_root = {
        "r1": _FakeSource({"a": _Conv("본문 " * 40)}),
        "r2": _FakeSource({"b": _Conv(""), "c": _Conv("본문 " * 40), "d": _Conv("본문 " * 40)}),
    }
    got = preview_roots(lambda rs: by_root[rs[0]], ["r1", "r2"])
    assert [r["root_id"] for r in got["roots"]] == ["r1", "r2"]
    assert [r["with_body"] for r in got["roots"]] == [1, 2]
    assert got["total"] == {"pages": 4, "with_body": 3, "empty": 1, "image_only": 0, "images": 0}


def test_titles_are_sampled_only_from_real_documents():
    src = _FakeSource({"a": _Conv("본문 " * 40), "b": _Conv("")})
    got = preview_root(src, "root-1")
    assert got.titles == ["제목 a"]


def test_the_preview_shows_the_title_that_will_actually_be_stored():
    """제목 속성이 빈 DB 행은 적재 시 다른 이름을 얻는다(select 값 등). 미리보기가 Notion 원본
    제목을 보여주면 실제 저장과 어긋나고, 그러면 미리보기가 미리보기가 아니다."""
    src = _FakeSource({"row": _Conv("본문 " * 40, frontmatter={"title": "파티룸 Entity / 입장"})})
    assert preview_root(src, "root-1").titles == ["파티룸 Entity / 입장"]


# ── 코퍼스 현황 ──────────────────────────────────────────────────────────────


class _Con:
    """문서 수와 **실질 문서 수**를 따로 돌려주는 가짜.

    둘을 같은 값으로 돌려주는 가짜는 2026-08-07 에 실제로 일어난 상황(문서 116 · 실질 19)을
    **표현할 수 없다**. 가짜가 실물보다 쉬우면 테스트는 통과하고 프로덕션은 죽는다.
    """

    def __init__(self, docs, substantive=None):
        self.docs = docs
        self.substantive = docs if substantive is None else substantive

    async def fetchval(self, sql, *a):
        if "HAVING coalesce(sum(length(c.chunk_text)), 0) >=" in sql:
            return self.substantive
        return self.docs if "FROM documents" in sql else 0

    async def fetch(self, sql, *a):
        return []


def test_the_pack_b_distance_is_computed_not_remembered():
    """트리거가 두 조건인데 그 거리를 보려면 psql 을 쳐야 했다."""
    import asyncio

    from nexus.sources.corpus import (PACK_B_MIN_DOCUMENTS, PACK_B_MIN_SUBSTANTIVE,
                                      corpus_status)

    assert PACK_B_MIN_DOCUMENTS == 100
    assert PACK_B_MIN_SUBSTANTIVE == 60

    got = asyncio.run(corpus_status(_Con(20)))["pack_b"]
    assert (got["documents"], got["short_by"], got["ready"]) == (20, 80, False)

    ready = asyncio.run(corpus_status(_Con(140)))["pack_b"]
    assert ready["ready"] and ready["short_by"] == 0 and ready["substantive_short_by"] == 0


def test_a_corpus_of_stubs_is_not_ready_however_many_stubs():
    """**두 조건은 다른 것을 잰다.** 짧은 문서도 창 경쟁에는 참가하므로 바닥값은 통과시키지만,
    본문이 없는 문서는 gold 가 못 된다.

    실물: 문서 116(바닥값 0.086, 통과)에 본문 800자 이상은 19건이었다. 답변가능 40건을 19개
    문서에 걸면 층별 8건을 서로 다른 문서에서 뽑을 수 없고, 무승부가 쌓여 '검정력 부족' 이
    나온다 — ADR-0008 §5(b) 를 갚지 못하는 유일한 결과다 (KOREAN_SEARCH_QUALITY.md §6.2).
    """
    import asyncio

    from nexus.sources.corpus import corpus_status

    got = asyncio.run(corpus_status(_Con(116, substantive=19)))["pack_b"]
    assert got["short_by"] == 0, "문서 수 조건은 이미 찼다 — 그래서 이것만 세면 통과한다"
    assert got["substantive_documents"] == 19
    assert got["substantive_short_by"] == 41
    assert got["ready"] is False, "실질 문서가 모자란데 준비됐다고 하면 라벨 노동만 태운다"


# ── 루트별 토큰: 워크스페이스가 하나라는 가정을 푼다 ─────────────────────────


def test_roots_are_grouped_by_the_token_that_can_read_them():
    from nexus.sources.roots_store import group_by_token

    got = group_by_token([
        {"root_id": "a", "token_env": "NOTION_TOKEN"},
        {"root_id": "b", "token_env": "NOTION_TOKEN_PFPLAY"},
        {"root_id": "c"},                                  # 옛 행 — 기본값으로 읽는다
    ])
    assert got == {"NOTION_TOKEN": ["a", "c"], "NOTION_TOKEN_PFPLAY": ["b"]}


def test_a_missing_token_stops_loudly_instead_of_falling_back(monkeypatch):
    """조용히 기본 토큰으로 떨어지면 다른 워크스페이스를 읽거나 **빈 걸음**이 된다.
    그리고 빈 걸음은 reconcile 에서 '사라진 문서' 와 구분되지 않는다 — 오독이 삭제가 된다."""
    from nexus.sources.preview import MissingToken, require_token

    monkeypatch.setenv("NOTION_TOKEN", "real-token")
    monkeypatch.delenv("NOTION_TOKEN_PFPLAY", raising=False)

    assert require_token("NOTION_TOKEN") == "real-token"
    with pytest.raises(MissingToken) as e:
        require_token("NOTION_TOKEN_PFPLAY")
    assert "NOTION_TOKEN_PFPLAY" in str(e.value)


def test_a_sync_spanning_two_workspaces_is_refused_not_merged():
    """한 걸음에 두 토큰을 섞으면 못 보는 쪽이 통째로 지워질 수 있다."""
    from fastapi import HTTPException

    from nexus.sources.api import _one_workspace

    two = {"NOTION_TOKEN": ["a"], "NOTION_TOKEN_PFPLAY": ["b"]}
    with pytest.raises(HTTPException) as e:
        _one_workspace(two, None)
    assert e.value.status_code == 400
    assert "multiple workspaces" in e.value.detail

    assert _one_workspace(two, "NOTION_TOKEN_PFPLAY") == "NOTION_TOKEN_PFPLAY"
    assert _one_workspace({"NOTION_TOKEN": ["a"]}, None) == "NOTION_TOKEN", "하나뿐이면 생략 가능"

    with pytest.raises(HTTPException) as e:
        _one_workspace(two, "NOTION_TOKEN_TYPO")
    assert "no roots registered under" in e.value.detail


def test_confirming_a_plan_recovers_the_workspace_it_belonged_to():
    from fastapi import HTTPException

    from nexus.sources.api import _token_for

    by_token = {"NOTION_TOKEN": ["a", "c"], "NOTION_TOKEN_PFPLAY": ["b"]}
    assert _token_for(["b"], by_token, None) == "NOTION_TOKEN_PFPLAY"
    assert _token_for(["a", "c"], by_token, None) == "NOTION_TOKEN"
    with pytest.raises(HTTPException):
        _token_for(["a", "b"], by_token, None)      # 두 워크스페이스에 걸친 계획은 확정 불가


# ── 임베딩 안 된 청크: 안 보이던 것을 판정보다 위에 (§3.2) ───────────────────


class _FakeCon:
    def __init__(self, docs=0, unembedded=0, rows=None):
        self.docs, self.unembedded, self.rows = docs, unembedded, rows or []
        self.sql: list[str] = []

    async def fetchval(self, sql, *a):
        self.sql.append(sql)
        if "IS NULL" in sql:
            return self.unembedded
        return self.docs if "documents" in sql else 0

    async def fetch(self, sql, *a):
        self.sql.append(sql)
        return self.rows if "IS NULL" in sql else []

    async def fetchrow(self, sql, *a):
        return None


def test_unembedded_chunks_are_reported_because_nothing_else_counts_them():
    """`index/embed.py` 는 실패를 삼키고, `embed_health` 는 IS NOT NULL 만 센다. 거부된 청크는
    벡터 다리에서 영구히 안 보이는데 두 곳 어디에도 안 잡힌다 (§3.2).

    2026-08-07 실물: 18,751자 청크를 사이드카가 413 으로 거부했다.
    """
    import asyncio

    from nexus.sources.corpus import corpus_status

    con = _FakeCon(docs=116, unembedded=1,
                   rows=[{"rid": "chunk_x", "title": "[파티룸] 디제잉 정책", "chars": 18751}])
    got = asyncio.run(corpus_status(con))
    u = got["unembedded_chunks"]
    assert u["count"] == 1
    assert u["sample"][0]["chars"] == 18751
    assert "벡터 다리" in u["note"]


def test_it_counts_the_column_the_search_leg_actually_reads(monkeypatch):
    """세대가 바뀐 뒤 다른 컬럼을 세면 '다 임베딩됐다' 는 거짓을 보고하게 된다."""
    import asyncio

    from nexus.sources.corpus import corpus_status

    monkeypatch.setenv("NEXUS_EMBEDDING_COLUMN", "embedding_1024")
    con = _FakeCon(docs=1, unembedded=0)
    got = asyncio.run(corpus_status(con))
    assert got["unembedded_chunks"]["column"] == "embedding_1024"
    assert any("embedding_1024 IS NULL" in s for s in con.sql), \
        "검색 다리가 읽는 컬럼으로 세야 한다"

    monkeypatch.setenv("NEXUS_EMBEDDING_COLUMN", "embedding")
    con2 = _FakeCon(docs=1, unembedded=0)
    got2 = asyncio.run(corpus_status(con2))
    assert got2["unembedded_chunks"]["column"] == "embedding"


def test_the_biggest_chunks_come_first_because_length_is_the_usual_cause():
    import asyncio

    from nexus.sources.corpus import corpus_status

    con = _FakeCon(docs=1, unembedded=2, rows=[
        {"rid": "a", "title": "긴 정책", "chars": 18751},
        {"rid": "b", "title": "짧은 것", "chars": 900},
    ])
    got = asyncio.run(corpus_status(con))
    assert [s["chars"] for s in got["unembedded_chunks"]["sample"]] == [18751, 900]
