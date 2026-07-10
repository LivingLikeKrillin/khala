"""소스 콘솔의 `force` 는 강제해야 한다 — 지금은 받아서 버린다.

`POST /sources/notion/sync {"force": true}` 는 `force` 를 재조정 planner 로만 보내고, 적재
경로에는 넘기지 않는다. `import_notion` 은 `force` 인자를 아예 갖고 있지 않다.

그래서 본문이 안 바뀐 페이지는 영원히 `idempotent` 로 건너뛴다. Notion 페이지 제목을 고치는
수정(문서 제목 = 페이지 이름)을 배포하고 `force` 로 재동기화해도 **제목이 그대로였다.**
관측 2026-07-10: `force: true` 실행이 `ingested: 0, idempotent: 12` 를 보고했다.
"""

from __future__ import annotations

import inspect

from nexus.ingest.sources.notion_importer import import_notion


def test_import_notion_accepts_force():
    assert "force" in inspect.signature(import_notion).parameters, (
        "import_notion 이 force 를 받지 않는다 — 콘솔의 force 체크박스는 아무것도 하지 않는다")


async def test_force_reaches_the_ingest_function():
    """force=True 면 적재 함수가 그 사실을 받는다. 여기서 끊기면 본문 해시 dedup 이 이긴다."""
    seen: list[bool] = []

    async def ingest_fn(doc, tenant, *, force=False):
        seen.append(force)
        return "ingested"

    class _Src:
        def live_index(self):
            return {"p1": {"root"}}

        def page_ref(self, pid):
            from nexus.ingest.sources.base import PageRef
            return PageRef(id=pid, url="", last_edited="2026-01-01", title="제목")

        def fetch_markdown(self, ref):
            from nexus.ingest.sources.base import ConvertedDoc
            return ConvertedDoc(page_id=ref.id, markdown="# 본문", frontmatter={"title": "제목"},
                                image_count=0)

    await import_notion(_Src(), "t", ingest_fn, force=True)
    assert seen == [True], "force 가 적재 함수까지 도달하지 않았다"


async def test_without_force_the_ingest_function_is_told_so():
    seen: list[bool] = []

    async def ingest_fn(doc, tenant, *, force=False):
        seen.append(force)
        return "idempotent"

    class _Src:
        def live_index(self):
            return {"p1": {"root"}}

        def page_ref(self, pid):
            from nexus.ingest.sources.base import PageRef
            return PageRef(id=pid, url="", last_edited="2026-01-01", title="제목")

        def fetch_markdown(self, ref):
            from nexus.ingest.sources.base import ConvertedDoc
            return ConvertedDoc(page_id=ref.id, markdown="# 본문", frontmatter={"title": "제목"},
                                image_count=0)

    await import_notion(_Src(), "t", ingest_fn)
    assert seen == [False]
