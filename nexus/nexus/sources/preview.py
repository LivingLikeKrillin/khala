"""등록하지 않은 Notion 루트를 재본다 — "이걸 넣으면 무엇이 들어오나".

`POST /sources/notion/sync {dry_run: true}` 는 **등록된** 루트만 걷는다. 그래서 루트를 고르는
순간에는 쓸 수 없다: 넣어봐야 알 수 있고, 알려면 넣어야 한다. 코퍼스를 키우려는 사람이 처음
묻는 질문이 정확히 그것이라, 여기서 끊긴다.

세는 것은 셋이고, 셋 다 이유가 있다.

* **본문 있는 페이지** — 실제로 색인될 문서 수. 코퍼스 목표(Pack B 트리거는 활성 문서 100건)에
  얼마나 가까워지는지가 이 숫자다.
* **빈 페이지** — 자식 링크만 있는 목차이거나 제목만 만들어 둔 껍데기. 적재하면 같은 내용을 두 번
  세는 인덱스 오염이라 건너뛰는 게 맞지만, **몇 건인지 안 보이면 루트가 얕은 건지 순회가 얕은
  건지 구분되지 않는다.** 실제로 한 루트가 31페이지 중 19건이 그래서 12건에서 고갈됐다.
* **그림뿐인 페이지** — 이미지가 있는데 본문이 거의 없는 문서. 정책 문서에서 표를 스크린샷으로
  붙이면 이렇게 되고, 그러면 검색에 안 걸리는데 경고도 없다. 얇은 문서와 구분해서 센다.

읽기 전용이다. DB 도 run 행도 건드리지 않는다.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

# 본문이 이보다 짧으면서 이미지가 있으면 '그림뿐' 으로 센다. 캡션까지 살린 뒤의 길이라,
# 캡션이 제대로 붙은 문서는 여기 걸리지 않는다.
IMAGE_ONLY_MAX_CHARS = 120


@dataclass
class RootPreview:
    root_id: str
    pages: int = 0
    with_body: int = 0
    empty: int = 0
    image_only: int = 0
    images: int = 0
    titles: list[str] = field(default_factory=list)     # with_body 인 것만, 최대 10개
    error: str = ""

    def as_dict(self) -> dict:
        return asdict(self)


def preview_root(source, root_id: str, sample_titles: int = 10) -> RootPreview:
    """한 루트를 걸어 무엇이 들어올지 센다. `source` 는 `NotionSource` 호환 객체."""
    out = RootPreview(root_id=root_id)
    try:
        page_ids = sorted(source.live_ids())
    except Exception as e:  # noqa: BLE001 — 토큰/권한/오타는 여기서 드러난다
        out.error = f"{type(e).__name__}: {e}"
        return out

    out.pages = len(page_ids)
    for pid in page_ids:
        try:
            ref = source.page_ref(pid)
            conv = source.fetch_markdown(ref)
        except Exception as e:  # noqa: BLE001 — 한 페이지가 막혀도 나머지는 센다
            out.error = out.error or f"{type(e).__name__}: {e}"
            continue
        body = conv.markdown.strip()
        out.images += getattr(conv, "image_count", 0)
        if not body:
            out.empty += 1
            continue
        out.with_body += 1
        if getattr(conv, "image_count", 0) and len(body) <= IMAGE_ONLY_MAX_CHARS:
            out.image_only += 1
        if len(out.titles) < sample_titles:
            out.titles.append(getattr(ref, "title", "") or pid)
    return out


def preview_roots(source_factory, root_ids: list[str]) -> dict:
    """여러 루트를 각각 재고 합계를 낸다.

    루트마다 새 source 를 만든다 — `live_ids()` 가 자기 roots 를 걷기 때문이고, 합쳐 걸으면
    어느 루트가 무엇을 줬는지 알 수 없어 고르는 데 못 쓴다.
    """
    previews = [preview_root(source_factory([r]), r) for r in root_ids]
    return {
        "roots": [p.as_dict() for p in previews],
        "total": {
            "pages": sum(p.pages for p in previews),
            "with_body": sum(p.with_body for p in previews),
            "empty": sum(p.empty for p in previews),
            "image_only": sum(p.image_only for p in previews),
            "images": sum(p.images for p in previews),
        },
    }
