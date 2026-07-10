"""Notion page id 표기 정규화.

Notion API 는 대시 포함 소문자 UUID 를 준다. 반면 사용자가 브라우저 URL 에서 복사하는 id 는
대시가 없다. `--roots` 에 URL 형식을 넣으면 루트 페이지만 다른 표기로 적재되어

  · 같은 페이지가 서로 다른 doc rid 로 **중복** 생기고,
  · walked_roots 와 prov_inputs 의 표기가 엇갈려 containment 술어가 조용히 빗나간다.

optional 의존(notion-client)이 없는 모듈로 둔다 — notion.py 와 notion_reconcile.py 가 함께 쓴다.
"""

from __future__ import annotations

import re

_HEX32 = re.compile(r"^[0-9a-f]{32}$")


def canonical_page_id(page_id: str) -> str:
    """32자리 hex(대시 유무·대소문자 무관)를 API 표기(대시 포함 소문자)로 맞춘다.

    UUID 가 아닌 문자열은 그대로 둔다(테스트 픽스처·비-UUID id 를 망가뜨리지 않는다).
    """
    s = page_id.strip()
    compact = s.replace("-", "").lower()
    if _HEX32.match(compact):
        return (
            f"{compact[0:8]}-{compact[8:12]}-{compact[12:16]}-"
            f"{compact[16:20]}-{compact[20:32]}"
        )
    return s
