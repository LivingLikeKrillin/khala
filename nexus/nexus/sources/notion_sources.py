"""사람이 붙여넣는 Notion 참조 → canonical page id.

SPEC-nexus-notion-source-console §4.1.

브라우저 주소창에서 복사한 URL 은 슬러그 뒤에 대시 없는 32자리 hex 가 붙는다:

    https://www.notion.so/My-Team-Page-2740c71bb9dc80efb43aea3676e632c8?pvs=4

반면 API 는 대시 포함 소문자 UUID 를 준다. 둘을 같은 페이지로 취급하지 않으면 같은 문서가
서로 다른 doc_rid 로 중복 적재되고, 재조정의 containment 술어가 조용히 빗나간다.
"""

from __future__ import annotations

import re
from urllib.parse import urlparse

from nexus.ingest.sources.notion_ids import canonical_page_id

#: 32자리 hex — URL 슬러그 꼬리든, 대시 없는 id 든.
_HEX32 = re.compile(r"(?<![0-9a-fA-F])[0-9a-fA-F]{32}(?![0-9a-fA-F])")
#: 대시 포함 UUID.
_UUID = re.compile(
    r"(?<![0-9a-fA-F-])[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}(?![0-9a-fA-F-])"
)


def parse_notion_ref(ref: str) -> str:
    """URL · 대시 있는 id · 대시 없는 id 중 무엇이 와도 canonical id 를 돌려준다.

    page id 를 찾지 못하면 ValueError. 조용히 빈 문자열을 돌려주면 root 목록에 쓰레기가 쌓인다.
    """
    s = (ref or "").strip()
    if not s:
        raise ValueError("빈 참조입니다 — Notion 페이지 URL 또는 page id 를 주세요")

    # URL 이면 쿼리스트링을 떼어낸다: ?pvs=4, ?v=... 안에도 32자리 hex 가 있을 수 있다.
    if "://" in s:
        parsed = urlparse(s)
        s = parsed.path

    m = _UUID.search(s) or _HEX32.search(s)
    if m is None:
        raise ValueError(f"Notion page id 를 찾을 수 없습니다: {ref!r}")
    return canonical_page_id(m.group(0))
