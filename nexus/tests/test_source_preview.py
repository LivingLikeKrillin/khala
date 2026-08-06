"""등록 전 루트 미리보기 — "이걸 넣으면 무엇이 들어오나".

`POST /sync {dry_run: true}` 는 **등록된** 루트만 걷는다. 루트를 고르는 순간에는 쓸 수 없다:
넣어봐야 알 수 있고, 알려면 넣어야 한다. 코퍼스를 키우려는 사람의 첫 질문이 거기서 끊긴다.
"""

from __future__ import annotations

from dataclasses import dataclass

from nexus.sources.preview import IMAGE_ONLY_MAX_CHARS, preview_root, preview_roots


@dataclass
class _Conv:
    markdown: str
    image_count: int = 0


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


# ── 코퍼스 현황 ──────────────────────────────────────────────────────────────


def test_the_pack_b_distance_is_computed_not_remembered():
    """트리거가 '활성 문서 100건' 인데 그 거리를 보려면 psql 을 쳐야 했다."""
    from nexus.sources.corpus import PACK_B_MIN_DOCUMENTS

    assert PACK_B_MIN_DOCUMENTS == 100

    class _Con:
        def __init__(self, docs):
            self.docs = docs

        async def fetchval(self, sql, *a):
            return self.docs if "documents" in sql else 0

        async def fetch(self, sql, *a):
            return []

    import asyncio

    from nexus.sources.corpus import corpus_status

    got = asyncio.run(corpus_status(_Con(20)))
    assert got["pack_b"] == {
        "min_documents": 100, "documents": 20, "short_by": 80, "ready": False,
        "why": got["pack_b"]["why"]}

    ready = asyncio.run(corpus_status(_Con(140)))
    assert ready["pack_b"]["ready"] and ready["pack_b"]["short_by"] == 0
