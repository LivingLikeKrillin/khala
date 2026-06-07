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
            lines.append(f"![image]({src})")  # 의미 미캡처 (후속 비전 강화)
        else:
            # 미지원 블록: 텍스트가 있으면 살리고, 없으면 무시 (무손실)
            if rich:
                lines.append(_rich_to_md(rich))
        lines.append("")
    return "\n".join(lines).strip() + "\n", image_count
