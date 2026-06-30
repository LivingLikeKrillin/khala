"""문서 제목 파생 — 결정론 파싱(LLM 미개입).

우선순위: frontmatter `title` → 본문 첫 ATX 헤딩 → 폴백(파일명).
notion deposit 등 frontmatter title·선두 H1 없이 적재된 문서의 제목이 파일명(UUID)으로
떨어지는 것을 막는다. pipeline 적재와 기존 문서 백필이 같은 규칙을 공유한다.
"""

from __future__ import annotations

import re

# ATX 헤딩: 선두 공백 0~3, '#' 1~6 + 공백 + 내용. 닫힘형 트레일링 '#'은 내용에서 제거.
_HEADING = re.compile(r"^\s{0,3}#{1,6}\s+(.*\S)\s*$")
_LINK = re.compile(r"\[([^\]]+)\]\([^)]*\)")  # [텍스트](url) → 텍스트


def _clean_inline(text: str) -> str:
    """제목용 인라인 마크다운 제거 — 링크는 텍스트만, 강조/코드 마커는 삭제."""
    text = _LINK.sub(r"\1", text)
    text = text.replace("*", "").replace("`", "")
    return text.strip()


def first_heading(content: str | None) -> str | None:
    """본문에서 첫 ATX 헤딩 텍스트를 반환(인라인 마크다운 정리). 없으면 None."""
    for line in (content or "").splitlines():
        m = _HEADING.match(line)
        if m:
            return _clean_inline(m.group(1).rstrip("# ").strip()) or None
    return None


def derive_title(frontmatter: dict | None, content: str | None, fallback: str) -> str:
    """frontmatter title → 본문 첫 헤딩 → fallback 순으로 사람이 읽는 제목을 고른다."""
    fm_title = (frontmatter or {}).get("title")
    if fm_title and str(fm_title).strip():
        return str(fm_title).strip()
    heading = first_heading(content)
    if heading:
        return heading
    return fallback
