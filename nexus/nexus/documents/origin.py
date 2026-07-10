"""문서의 출처를 source_uri 에서 **유도**한다 (SPEC-nexus-document-lifecycle §4.3).

새 컬럼을 만들지 않는다. source_uri 가 이미 답을 갖고 있다.

세 갈래다. 업로드와 리포 파일은 "어디서 왔나" 에 대한 서로 다른 답이고, 둘을 뭉뚱그리면
이 컬럼의 존재 이유가 사라진다.
"""

from __future__ import annotations

import re

_NOTION_PREFIX = "ext-notion-"
_UPLOAD_PREFIX = "uploads/"
_CANONICAL_PAGE_ID = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
)


def _path(source_uri: str) -> str:
    """'{tenant}:{path}' → path. 콜론이 없으면 통째로 path."""
    _, _, rest = source_uri.partition(":")
    return rest or source_uri


def derive_origin(source_uri: str) -> tuple[str, str | None]:
    """(origin, origin_url) 을 돌려준다. origin ∈ {notion, upload, file}.

    Notion page id 가 canonical(대시 포함 소문자 UUID)이 아니면 URL 을 **추측하지 않고**
    None 을 돌려준다. 틀린 링크는 링크 없음보다 나쁘다.
    """
    path = _path(source_uri)

    if path.startswith(_NOTION_PREFIX):
        page_id = path[len(_NOTION_PREFIX):].removesuffix(".md")
        if _CANONICAL_PAGE_ID.match(page_id):
            return "notion", f"https://www.notion.so/{page_id.replace('-', '')}"
        return "notion", None

    if path.startswith(_UPLOAD_PREFIX):
        return "upload", None

    return "file", None
