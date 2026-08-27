"""8장 충실도 표본을 **뽑아서 꺼내 놓는다** — SPEC-nexus-screenshot-text-extraction §7.1.

이 평가 하니스는 채점하지 않는다. 디렉터가 그림을 읽고 기대 내용을 적을 수 있도록 **그림 파일만** 꺼낸다.
기계 판독은 이미 DB 에 있고, 이 스크립트는 **그것을 출력하지 않는다** — §7.1 이 요구하는 순서가
"사람이 먼저 적고, 그다음 기계 판독을 본다" 이기 때문이다.

## 사전등록된 추첨 규칙 (revision 2)

**왜 revision 2 인가 — 재등록 기록.** revision 1 은 "문서 제목순 라운드로빈으로 각 문서의 미선택
최소 index" 였고, 그것이 뽑은 8장이 **전부 각 문서의 #1·#2** 였다. 규칙대로였고 임의 선택은
없었지만, 첫 그림들이 계통적으로 같은 종류(문서 머리의 화면 스펙 등)라면 표본이 좁은 한 종류만
재게 된다. 2026-08-11 에 디렉터가 (B) 재등록을 택했다.

**재등록이 정당한 조건은 하나뿐이고 그것을 만족했다: 아직 아무도 그림도 기계 판독도 보지
않았다.** 판독을 본 뒤에 규칙을 고치면 그건 결과를 보고 문턱을 옮기는 것이고, 사전등록이
아무 의미가 없어진다. 여기서 바뀐 근거는 *내용* 이 아니라 *인덱스 분포* 다.

1. 문서는 **제목 오름차순**, 그림은 **walk 순서 index** 로 고정 정렬한다.
2. 구현 에이전트가 이미 연 5장을 제외한다 (§7.1c — 아바타 정책 문서의 6·8·9·10·11번).
   그 5장은 기계-대-자기자신 비교가 되므로 참조 판독이 될 수 없다.
3. **배분**: 다섯 문서가 각 1장을 먼저 받는다(§7.1 의 "across all five documents"). 남은 3장은
   **적격 그림이 많은 문서 순** 으로 하나씩 준다(동수면 제목 오름차순).
4. **문서 안에서는 인덱스 범위에 고르게 편다.** k 장을 받은 문서는 적격 목록의
   `(i + 0.5) / k` 위치(i = 0..k-1)를 취한다 — k=1 이면 한가운데, k=2 면 1/4·3/4 지점.
   앞에서부터 세지 않는다. 그것이 revision 1 의 결함이었다.
5. **무작위 없음.** 다시 돌리면 같은 8장이 나온다.

## 왜 다시 걸어야 하나

그림 바이트는 어디에도 저장돼 있지 않고(`vision_extractions` 는 해시와 텍스트만), 청크 마커에도
블록 id 가 없다 — `vision.source_ref()` 는 정의돼 있으나 **부르는 곳이 없다.** 그래서 원본은
Notion 을 다시 걸어서만 얻는다. Step 0b(§7.1b)가 증명한 "블록 id 만으로 재수집" 은 그 실행이
메모리에 들고 있던 id 로 한 것이다.

    docker exec nexus-app python -u scripts/vision_fidelity_sample.py --roots "<id>,<id>"
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from nexus.ingest.sources.notion import NotionSource  # noqa: E402

OUT = Path("/app/tests/eval/local/fidelity-sample")

#: §7.1c — 구현 에이전트가 이미 연 그림. 문서 제목의 일부와 1-기반 번호로 적는다.
#: 번호는 그 문서 안에서의 walk 순서다.
ALREADY_OPENED: dict[str, set[int]] = {"아바타": {6, 8, 9, 10, 11}}

SAMPLE_SIZE = 8


def _excluded(title: str, index_1based: int) -> bool:
    return any(key in title and index_1based in nums for key, nums in ALREADY_OPENED.items())


def allocate(sizes: dict[str, int], total: int) -> dict[str, int]:
    """문서별 배분 (규칙 3). 각 1장 먼저, 남은 것은 적격 수 많은 순 — 동수면 제목 오름차순."""
    docs = sorted(sizes)
    quota = {t: 1 for t in docs if sizes[t] > 0}
    remaining = total - sum(quota.values())
    # 큰 문서부터 하나씩. 자기 적격 수를 넘겨 주지 않는다.
    order = sorted(quota, key=lambda t: (-sizes[t], t))
    i = 0
    while remaining > 0 and any(quota[t] < sizes[t] for t in order):
        t = order[i % len(order)]
        if quota[t] < sizes[t]:
            quota[t] += 1
            remaining -= 1
        i += 1
    return quota


def draw(catalogue: list[dict]) -> list[dict]:
    """사전등록 규칙 revision 2 그대로. 순수 함수 — 입력이 같으면 결과가 같다."""
    by_doc: dict[str, list[dict]] = {}
    for im in catalogue:
        if not _excluded(im["doc_title"], im["index"]):
            by_doc.setdefault(im["doc_title"], []).append(im)
    for ims in by_doc.values():
        ims.sort(key=lambda x: x["index"])

    quota = allocate({t: len(v) for t, v in by_doc.items()}, SAMPLE_SIZE)

    drawn: list[dict] = []
    for title in sorted(by_doc):
        ims, k = by_doc[title], quota.get(title, 0)
        # 규칙 4 — 인덱스 범위의 (i+0.5)/k 지점. 앞에서부터 세지 않는다.
        picked = {min(len(ims) - 1, int((i + 0.5) / k * len(ims))) for i in range(k)}
        drawn += [ims[p] for p in sorted(picked)]
    return sorted(drawn, key=lambda x: (x["doc_title"], x["index"]))


async def _image_pages_from_db(tenant: str) -> list[tuple[str, str]]:
    """그림을 가진 문서의 (page_id, title). **트리를 다시 걷지 않는다.**

    root 에서 걷는 길은 root 하나가 접근 불가가 되면 통째로 멈춘다. 우리가 원하는 것은 트리가
    아니라 **그림을 가진 문서 5개**이고, 그건 `documents.n_images` 가 이미 안다
    (migration 011 이 그 수를 질의 가능하게 만든 이유가 이런 것이다).

    page id 는 손으로 넘기지 않는다 — 조직 지문이라 명령줄·로그에 남기지 않는 편이 낫다.
    """
    from nexus import db

    await db.get_pool()
    try:
        rows = await db.fetch_all(
            "SELECT source_uri, title FROM documents "
            "WHERE tenant = $1 AND status = 'active' AND n_images > 0 ORDER BY title", tenant)
        out = []
        for r in rows:
            # default:ext-notion-<page-id>.md
            stem = r["source_uri"].rsplit(":", 1)[-1]
            if stem.startswith("ext-notion-") and stem.endswith(".md"):
                out.append((stem[len("ext-notion-"):-len(".md")], r["title"]))
        return out
    finally:
        await db.close_pool()


async def _tokens_by_root(tenant: str) -> list[str]:
    """등록된 root 들이 쓰는 **토큰 env 이름**. root 마다 다르다 (migration 009).

    한 워크스페이스만 있다고 가정하고 `NOTION_TOKEN` 하나로 물으면, 다른 통합에 연결된 트리는
    통째로 `ObjectNotFound` 로 돌아온다 — 그리고 그 코드는 *공유 안 됨* 과 *없음* 을 구분하지
    않으므로 "원본이 사라졌다" 로 오독된다. 2026-08-11 에 내가 그렇게 읽었다.
    """
    from nexus import db

    await db.get_pool()
    try:
        rows = await db.fetch_all(
            "SELECT DISTINCT token_env FROM notion_sources WHERE tenant = $1 ORDER BY token_env",
            tenant)
        return [r["token_env"] for r in rows]
    finally:
        await db.close_pool()


def main() -> int:
    import asyncio

    ap = argparse.ArgumentParser()
    ap.add_argument("--tenant", default="default")
    args = ap.parse_args()

    pages = asyncio.run(_image_pages_from_db(args.tenant))
    if not pages:
        print("  그림을 가진 문서가 없다 — documents.n_images 를 확인하라")
        return 2
    print(f"  그림을 가진 문서 {len(pages)}개를 연다", flush=True)

    # **등록된 모든 토큰을 시도한다.** 페이지가 어느 통합에 걸려 있는지는 문서 행이 모르고,
    # `notion_sources.token_env` 만 안다. 하나로 물으면 다른 트리는 전부 "없음" 으로 보인다.
    tokens = asyncio.run(_tokens_by_root(args.tenant))
    sources = []
    for env in tokens:
        try:
            sources.append((env, NotionSource(token_env=env, roots=[])))
        except KeyError:
            print(f"  ⚠ {env} 가 환경에 없다 — 그 트리는 못 읽는다", flush=True)
    if not sources:
        print("  쓸 수 있는 Notion 토큰이 없다")
        return 2
    print(f"  토큰 {len(sources)}종으로 시도한다: {', '.join(e for e, _ in sources)}", flush=True)

    catalogue: list[dict] = []
    unreachable: list[str] = []
    for page_id, title in pages:
        conv = None
        for env, src in sources:
            try:
                conv = src.fetch_markdown(src.page_ref(page_id))
                break
            except Exception:      # noqa: BLE001 — 다음 토큰을 시도한다
                continue
        if conv is None:
            unreachable.append(title[:26])
            print(f"  ✗ 어느 토큰으로도 닿지 않음: {title[:26]}", flush=True)
            continue
        for i, im in enumerate(conv.images, start=1):
            catalogue.append({
                "doc_title": conv.frontmatter.get("title") or title,
                "page_id": page_id, "index": i,
                "block_id": im["block_id"], "url": im["url"],
                "caption": im.get("caption", ""),
            })

    print(f"\n  닿은 문서 {len(pages) - len(unreachable)}/{len(pages)} · "
          f"그림 {len(catalogue)}장 (코퍼스에 기록된 수는 44)", flush=True)
    if unreachable:
        print("  ⚠ 원본에 닿지 못한 문서 — ADR-0010 §2 의 recourse 가 이만큼 비어 있다:")
        for u in unreachable:
            print(f"      {u}")
    if not catalogue:
        print("\n  그림을 하나도 못 얻었다. 표본을 뽑을 수 없다 — 이것이 결과다.")
        return 2

    drawn = draw(catalogue)
    OUT.mkdir(parents=True, exist_ok=True)

    import httpx

    sheet = []
    for n, im in enumerate(drawn, start=1):
        name = f"{n:02d}_{im['doc_title'][:20].replace('/', '_')}_{im['index']}.png"
        try:
            r = httpx.get(im["url"], timeout=60, follow_redirects=False)
            r.raise_for_status()
            (OUT / name).write_bytes(r.content)
            saved = name
        except Exception as e:      # noqa: BLE001 — 한 장 실패가 나머지를 막지 않는다
            saved = f"(받지 못함: {e})"
        sheet.append({"n": n, "file": saved, "doc": im["doc_title"], "image_index": im["index"],
                      "block_id": im["block_id"]})
        print(f"  {n:2d}. {im['doc_title'][:26]:26s} #{im['index']:<3d} → {saved}", flush=True)

    (OUT / "sample.json").write_text(
        json.dumps({"rule": "SPEC-nexus-screenshot-text-extraction §7.1 · revision 2 "
                            "(문서별 배분 + 인덱스 범위 균등 분산) · 에이전트가 연 5장 제외 · "
                            "무작위 없음 · revision 1(라운드로빈)은 #1·#2 로 뭉쳐 재등록됨, "
                            "재등록 시점에 그림·기계판독 모두 미열람",
                    "total_images": len(catalogue), "drawn": sheet},
                   ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

    print(f"\n  그림 {len(drawn)}장을 {OUT} 에 꺼냈다.")
    print("  기계 판독은 **출력하지 않는다** — 디렉터가 먼저 적어야 한다 (§7.1).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
