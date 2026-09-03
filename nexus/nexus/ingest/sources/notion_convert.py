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


#: 읽지 못한 하위 블록 자리에 남기는 표식. **본문에 남긴다** — 조용히 지우면 잘린 정책이
#: 완전한 정책처럼 보이고, 그 위에서 답하는 쪽은 무엇이 빠졌는지 알 방법이 없다.
#: 블록 id 는 여기 안 넣는다(코퍼스에 남는 텍스트다). 진단용 id 는 `hole_sink` 와 로그에 있다.
HOLE_NOTE = "> (읽지 못한 블록: {kind} — 원본이 이 integration 에 공유되지 않았습니다)"

#: 데이터베이스가 있던 자리. **구멍 표식이 아니다** — 못 읽은 게 아니라 **다른 문서로 읽은 것**이고,
#: 그 차이를 문장이 말해야 읽는 쪽이 "표가 잘렸다" 로 오해하지 않는다.
DATABASE_NOTE = "> (데이터베이스 {name} — 각 행은 별도 문서로 적재되어 있습니다)"


def _children(children_of, block: dict, hole_sink: list | None) -> list[dict] | None:
    """자식 블록을 가져온다. 못 가져오면 `None` 을 돌려주고 구멍으로 기록한다.

    **왜 삼키지 않고 가르나.** `synced_block` 의 원본이 이 integration 에 공유돼 있지 않으면
    Notion 이 404 를 낸다. 예전에는 그 예외가 변환기를 뚫고 올라가 `import_notion` 의
    per-page `except` 에 잡혔고, **블록 하나 때문에 페이지가 통째로 버려진 뒤 `skipped` 숫자
    뒤에 묻혔다**(2026-08-25 실측: 조직 정책 문서 4건이 전부 이 이유로 코퍼스에 없었다).

    빈 리스트로 갈음하지 않는 이유도 같다 — 그러면 "자식이 없다" 와 "못 읽었다" 가 같은 값이
    되고, 그 둘을 가르지 못하는 순간 손실이 다시 조용해진다.
    """
    try:
        return children_of(block["id"])
    except Exception as exc:  # noqa: BLE001 — 원인 무관하게 나머지 본문을 살린다
        if hole_sink is not None:
            hole_sink.append({"block_id": block.get("id", ""),
                              "type": block.get("type", ""), "error": str(exc)})
        return None


def blocks_to_markdown(blocks: list[dict], children_of=None,
                       image_sink: list | None = None,
                       hole_sink: list | None = None) -> tuple[str, int]:
    """Notion 블록 리스트 → (markdown, image_count).

    `children_of(block_id) -> list[dict]` 를 주면 자식이 있는 블록(표·토글·동기화 블록)을
    한 겹 더 펼친다. 안 주면 예전처럼 얕게 훑는다 — 호출자가 API 를 안 들고 있을 수 있어서다.

    `image_sink` 를 주면 그림 블록마다 `{block_id, url, caption}` 을 담고 본문엔 `image_slot()`
    표식을 남긴다. **URL 을 여기서만 잡을 수 있다** — Notion 이 주는 서명 링크는 한 시간이면
    죽으므로, 순회 중에 안 챙기면 나중에 다시 물어야 한다. sink 를 안 주면 예전 그대로
    `![]()` 를 쓴다(추출이 꺼진 배포·기존 테스트).

    `hole_sink` 를 주면 **읽지 못한 하위 블록**을 `{block_id, type, error}` 로 담는다. 그 자리
    본문에는 `HOLE_NOTE` 가 남고 **나머지 페이지는 살아남는다**. 안 주면 구멍은 표식만 남긴다.
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
            kids = _children(children_of, b, hole_sink)
            lines.extend(_table_rows_to_md(kids) if kids is not None
                         else [HOLE_NOTE.format(kind="표")])
        elif bt == "child_database":
            # **데이터베이스는 여기서 펼치지 않는다 — 자리만 남긴다.**
            #
            # 행은 각각 페이지이고 이미 별도 문서로 적재된다(`notion.py` 의 「속성도 본문이다」:
            # 블록이 0개인 행이 통째로 빠지던 것을 고친 자리). 그러니 여기서 표로 펼치면 같은
            # 내용이 두 벌이 되고, 행마다 API 를 한 번 더 쳐야 한다.
            #
            # ⛔ **그런데 아무것도 안 남기면 가리키는 문장이 갈 곳을 잃는다.** 실측 2026-09-03:
            # 「프로필/아바타 정책」의 정정 문구가 *"정본은 아래 「…」 데이터베이스"* 라고 적는데
            # 본문의 그 자리가 **비어 있었다** — `child_database` 는 미지원 블록으로 떨어지고
            # `rich_text` 도 `caption` 도 없어 흔적조차 안 남았기 때문이다. `_collect` 은 이
            # 블록을 알고 행을 재귀하는데 변환기만 몰랐다.
            title = (data.get("title") or "").strip()
            lines.append(DATABASE_NOTE.format(name=f"「{title}」" if title else "(이름 없음)"))
        elif bt in ("toggle", "synced_block", "column_list", "column") and children_of is not None:
            # 접힌 것도 본문이다. 토글 안에 규칙을 넣어 두는 문서가 흔하다.
            if rich:
                lines.append(_rich_to_md(rich))
            kids = _children(children_of, b, hole_sink)
            if kids is None:
                lines.append(HOLE_NOTE.format(kind=bt))
            else:
                sub, sub_images = blocks_to_markdown(kids, children_of, image_sink, hole_sink)
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
