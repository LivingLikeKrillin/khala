"""Notion 블록 → Markdown 변환.

텍스트(heading/paragraph/list/quote/callout/code/divider)는 충실히 살리고,
이미지는 카운트 + 플레이스홀더만 남긴다(의미 복원은 후속 비전 강화).
System decides: 결정론 파싱, LLM 미개입.
"""

from __future__ import annotations


def _rich_to_md(rich: list[dict]) -> str:
    out = []
    for r in rich or []:
        t = r.get("plain_text", r.get("text", {}).get("content", ""))
        ann = r.get("annotations", {})
        if ann.get("code"):
            t = f"`{t}`"
        if ann.get("bold"):
            t = f"**{t}**"
        if ann.get("italic"):
            t = f"*{t}*"
        href = r.get("href")
        if href:
            t = f"[{t}]({href})"
        out.append(t)
    return "".join(out)


def blocks_to_markdown(blocks: list[dict]) -> tuple[str, int]:
    """Notion 블록 리스트 → (markdown, image_count)."""
    lines: list[str] = []
    image_count = 0
    for b in blocks or []:
        bt = b.get("type")
        data = b.get(bt, {}) if bt else {}
        rich = data.get("rich_text", [])
        if bt == "heading_1":
            lines.append(f"# {_rich_to_md(rich)}")
        elif bt == "heading_2":
            lines.append(f"## {_rich_to_md(rich)}")
        elif bt == "heading_3":
            lines.append(f"### {_rich_to_md(rich)}")
        elif bt == "paragraph":
            lines.append(_rich_to_md(rich))
        elif bt == "bulleted_list_item":
            lines.append(f"- {_rich_to_md(rich)}")
        elif bt == "numbered_list_item":
            lines.append(f"1. {_rich_to_md(rich)}")
        elif bt == "to_do":
            mark = "x" if data.get("checked") else " "
            lines.append(f"- [{mark}] {_rich_to_md(rich)}")
        elif bt in ("quote", "callout"):
            lines.append(f"> {_rich_to_md(rich)}")
        elif bt == "code":
            lang = data.get("language", "")
            lines.append(f"```{lang}\n{_rich_to_md(rich)}\n```")
        elif bt == "divider":
            lines.append("---")
        elif bt == "image":
            image_count += 1
            src = data.get("external", {}).get("url") or data.get("file", {}).get("url", "")
            # **캡션은 본문이다.** 정책 문서의 그림 캡션은 "그림 3. 환불 승인 흐름" 처럼 그 문서가
            # 쓰는 어휘 그대로다. 예전엔 alt 를 `image` 로 고정해 캡션을 통째로 버렸고, 그러면
            # 표를 스크린샷으로 붙인 페이지가 **검색 텍스트 0** 인 얇은 문서가 된다.
            # 그림의 *내용* 은 여전히 못 잡는다(후속 비전 강화) — 잡는 것은 그 그림에 대해
            # 사람이 쓴 말이다.
            alt = _rich_to_md(data.get("caption", [])) or "image"
            lines.append(f"![{alt}]({src})")
        else:
            # 미지원 블록: 텍스트가 있으면 살리고, 없으면 무시 (무손실).
            # `file`/`video`/`pdf`/`embed`/`bookmark` 는 `rich_text` 가 없고 `caption` 에 글이
            # 담긴다 — 그래서 rich_text 만 보면 조용히 사라진다.
            salvaged = _rich_to_md(rich) or _rich_to_md(data.get("caption", []))
            if salvaged:
                lines.append(salvaged)
        lines.append("")
    return "\n".join(lines).strip() + "\n", image_count
