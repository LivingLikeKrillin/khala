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


#: origin → CRM `source_kind` enum(`init.sql:12`). 두 어휘가 따로 있는 이유는 origin 이
#: 업로드와 리포 파일을 가르기 때문이다 — enum 에는 그 구분이 없다.
_KIND_BY_ORIGIN = {"notion": "wiki", "upload": "file", "file": "git"}


def source_kind_for(source_uri: str) -> str:
    """저장할 `source_kind`. **여기 한 곳에서만 정한다.**

    이 컬럼은 2026-08-13 까지 모든 행에 `git` 이었다 — Notion 페이지 108건까지. 값이 없어서가
    아니라 **세 번 버려져서**다: 컨버터가 `source_kind: wiki` 를 frontmatter 에 넣고(`notion.py`),
    CSF 에는 그 칸이 없어 떨어지고, 파이프라인이 INSERT 에 `'git'` 을 **문자열 상수로** 박았다.
    제목과 그림 수가 앞서 똑같이 사라졌던 자리다(`_csf_to_markdown_file` 의 주석 둘).

    그래서 값을 세 홉에 걸쳐 나르는 대신 **URI 에서 유도한다** — 이 모듈이 이미 그렇게 하기로
    한 자리이고(§4.3 "source_uri 가 이미 답을 갖고 있다"), 유도가 한 곳이면 컬럼과
    `derive_origin` 이 서로 다른 답을 내는 일이 표현 불가능하다.
    """
    return _KIND_BY_ORIGIN[derive_origin(source_uri)[0]]
