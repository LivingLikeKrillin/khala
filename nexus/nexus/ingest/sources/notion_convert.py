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


def properties_to_markdown(props: dict, skip_title: bool = True) -> str:
    """데이터베이스 행의 **속성**을 본문으로 만든다.

    DB 행은 블록이 0개인 경우가 흔하다 — 내용이 전부 속성(컬럼)에 있다. 개정 이력의 한 행은
    `개정 내용`·`날짜`·`Epic`·`바로가기` 가 전부이고 블록은 비어 있다. 블록만 읽으면 그런 행은
    **빈 문서**로 판정돼 적재에서 빠지고, 정책 코퍼스의 상당 부분이 그렇게 사라진다.

    제목 속성은 문서 제목으로 따로 쓰이므로 기본적으로 건너뛴다(본문에 또 넣으면 중복이다).
    """
    lines: list[str] = []
    for name, v in (props or {}).items():
        t = v.get("type")
        if t == "title" and skip_title:
            continue
        val = ""
        if t in ("title", "rich_text"):
            val = _rich_to_md(v.get(t, []))
        elif t == "select":
            val = ((v.get("select") or {}) or {}).get("name", "")
        elif t == "multi_select":
            val = ", ".join(o.get("name", "") for o in v.get("multi_select", []))
        elif t == "status":
            val = ((v.get("status") or {}) or {}).get("name", "")
        elif t == "date":
            d = v.get("date") or {}
            val = " ~ ".join(x for x in (d.get("start"), d.get("end")) if x)
        elif t in ("number", "url", "email", "phone_number"):
            val = "" if v.get(t) is None else str(v.get(t))
        elif t == "checkbox":
            val = "예" if v.get("checkbox") else "아니오"
        elif t == "people":
            val = ", ".join(p.get("name", "") for p in v.get("people", []) if p.get("name"))
        elif t == "files":
            val = ", ".join(f.get("name", "") for f in v.get("files", []))
        elif t == "formula":
            f = v.get("formula") or {}
            val = str(f.get(f.get("type"), "") or "")
        val = (val or "").strip()
        if val:
            lines.append(f"- **{name}**: {val}")
    return "\n".join(lines)


def _table_rows_to_md(rows: list[dict]) -> list[str]:
    """`table_row` 블록들 → 마크다운 표.

    **정책 문서는 표가 본문이다.** 표를 못 읽으면 "비로그인 사용자는 입장 불가" 같은 규칙이
    통째로 사라지는데, 문서는 얇아 보일 뿐이라 아무도 눈치채지 못한다.
    """
    out: list[str] = []
    for i, r in enumerate(rows):
        cells = r.get("table_row", {}).get("cells", [])
        texts = [_rich_to_md(c).replace("|", "\\|").strip() or " " for c in cells]
        if not texts:
            continue
        out.append("| " + " | ".join(texts) + " |")
        if i == 0:                                   # 첫 행을 머리로 본다
            out.append("|" + "|".join([" --- "] * len(texts)) + "|")
    return out


def image_slot(block_id: str) -> str:
    """그림 자리에 남기는 표식. 2패스의 이음매다.

    순회는 동기(Notion API 를 순서대로 훑는다)이고 추출은 비동기(HTTP + LLM)라, 한 함수 안에서
    둘을 섞으면 잘 검증된 컨버터를 비동기로 물들이고 44장을 직렬로 읽게 된다. 그래서 1패스는
    자리만 비워 두고, 2패스가 그 자리를 채운다 — 동시에.
    """
    return f"<!-- khala:vision:slot:{block_id} -->"


def blocks_to_markdown(blocks: list[dict], children_of=None,
                       image_sink: list | None = None) -> tuple[str, int]:
    """Notion 블록 리스트 → (markdown, image_count).

    `children_of(block_id) -> list[dict]` 를 주면 자식이 있는 블록(표·토글·동기화 블록)을
    한 겹 더 펼친다. 안 주면 예전처럼 얕게 훑는다 — 호출자가 API 를 안 들고 있을 수 있어서다.

    `image_sink` 를 주면 그림 블록마다 `{block_id, url, caption}` 을 담고 본문엔 `image_slot()`
    표식을 남긴다. **URL 을 여기서만 잡을 수 있다** — Notion 이 주는 서명 링크는 한 시간이면
    죽으므로, 순회 중에 안 챙기면 나중에 다시 물어야 한다. sink 를 안 주면 예전 그대로
    `![]()` 를 쓴다(추출이 꺼진 배포·기존 테스트).
    """
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
            # **캡션은 남기고 URL 은 버린다.**
            #
            # 캡션이 본문인 이유는 그대로다: 정책 문서의 그림 캡션은 "그림 3. 환불 승인 흐름" 처럼
            # 그 문서가 쓰는 어휘다. 예전엔 alt 를 `image` 로 고정해 캡션을 통째로 버렸고, 그러면
            # 표를 스크린샷으로 붙인 페이지가 검색 텍스트 0 인 얇은 문서가 됐다.
            #
            # URL 은 반대다. Notion 이 주는 것은 **1시간 뒤 만료되는 S3 서명 링크**
            # (`X-Amz-Expires=3600`) 라 저장해도 죽은 값이고, 그러면서 본문을 망가뜨린다.
            # 2026-08-08 실측: 가장 큰 청크 18,839자 중 **18,623자(99%)** 가 공백 없는 이미지
            # URL 11개였다. 공백이 없으니 토큰 추정기가 그 덩어리를 144토큰으로 세어 청킹 상한
            # (1100)이 걸리지 않았고, 그 결과 정책 표가 잘린 채 근거로 나가 세 질의가 계속
            # 실패했다. 임베딩 사이드카도 같은 청크를 `413` 로 거부했다.
            #
            # 원문 이미지는 Notion 에 있다 — 원칙 5(인덱스이지 저장소가 아님) 그대로다.
            alt = _rich_to_md(data.get("caption", [])).strip()
            if image_sink is not None:
                src = data.get("file") or data.get("external") or {}
                image_sink.append({"block_id": b["id"], "url": src.get("url", ""),
                                   "caption": alt})
                lines.append(image_slot(b["id"]))
            else:
                lines.append(f"![{alt}]()" if alt else "![]()")
        elif bt == "table" and children_of is not None:
            lines.extend(_table_rows_to_md(children_of(b["id"])))
        elif bt in ("toggle", "synced_block", "column_list", "column") and children_of is not None:
            # 접힌 것도 본문이다. 토글 안에 규칙을 넣어 두는 문서가 흔하다.
            if rich:
                lines.append(_rich_to_md(rich))
            sub, sub_images = blocks_to_markdown(children_of(b["id"]), children_of, image_sink)
            image_count += sub_images
            if sub.strip():
                lines.append(sub.strip())
        else:
            # 미지원 블록: 텍스트가 있으면 살리고, 없으면 무시 (무손실).
            # `file`/`video`/`pdf`/`embed`/`bookmark` 는 `rich_text` 가 없고 `caption` 에 글이
            # 담긴다 — 그래서 rich_text 만 보면 조용히 사라진다.
            salvaged = _rich_to_md(rich) or _rich_to_md(data.get("caption", []))
            if salvaged:
                lines.append(salvaged)
        lines.append("")
    return "\n".join(lines).strip() + "\n", image_count
