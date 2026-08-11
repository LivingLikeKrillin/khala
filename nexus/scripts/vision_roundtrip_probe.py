"""인용 하나를 들고 실제 그림까지 걸어가 본다 — SPEC-nexus-vision-source-ref §6.

CI 의 §5.5 는 스텁 fetcher 로 돈다(§5 가 그렇게 요구한다: 살아 있는 블록·맞는 토큰·안 만료된
서명 URL 은 셋 다 사라질 수 있어서 시험의 근거로 삼으면 무관한 이유로 빨개진다). 그래서 **한 번은
손으로** 진짜 코퍼스에 대고 확인한다. 시험이 아니라 관측이다.

    활성 machine_read 청크 → resolve_source() → Notion 블록 재조회 → 새 서명 URL →
    바이트 내려받기 → sha 가 저장된 image_sha256 과 같은가

서명 URL 이 만료됐다는 것이 요점이다: 참조가 유효하면 **다시 받아올 수 있다**.
"""

from __future__ import annotations

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _tokens() -> list[tuple[str, str]]:
    """(env 이름, 토큰). 루트마다 다른 integration 이므로 가진 것을 다 시도한다."""
    return [(k, v) for k, v in os.environ.items()
            if k.startswith("NOTION_TOKEN") and v.strip()]


async def _image_url(block_id: str) -> tuple[str, str]:
    """블록을 다시 조회해 **새** 서명 URL 을 얻는다. → (url, 어느 토큰이었나)"""
    from notion_client import AsyncClient

    last = ""
    for name, token in _tokens():
        try:
            block = await AsyncClient(auth=token).blocks.retrieve(block_id)
        except Exception as exc:  # noqa: BLE001 — 토큰마다 ObjectNotFound 가 정상이다
            last = f"{name}: {type(exc).__name__}"
            continue
        img = block.get("image") or {}
        url = (img.get("file") or {}).get("url") or (img.get("external") or {}).get("url") or ""
        if url:
            return url, name
        last = f"{name}: 블록에 이미지 url 이 없다 (type={block.get('type')})"
    raise RuntimeError(f"어느 토큰으로도 블록을 못 읽었다 — {last}")


async def main(limit: int = 3) -> int:
    from nexus import db
    from nexus.ingest import vision, vision_source

    tenant = os.getenv("DEFAULT_TENANT", "default")
    rows = await db.fetch_all(
        "SELECT rid, chunk_text FROM chunks "
        "WHERE tenant = $1 AND status = 'active' AND provenance_tier = 'machine_read' "
        "ORDER BY rid LIMIT $2", tenant, limit)
    if not rows:
        print("활성 machine_read 청크가 없다 — 잴 것이 없다")
        return 1

    ok = 0
    for row in rows:
        ref = await vision_source.resolve_source(tenant, row["chunk_text"])
        if not isinstance(ref, vision_source.SourceRef):
            print(f"✗ {row['rid']}: 해석 실패 — {ref}")
            continue

        url, which = await _image_url(ref.block_id)
        from nexus.ingest.vision_store import _fetch_bytes

        data, media = await _fetch_bytes(url)
        got = vision.image_sha256(data)
        same = got == ref.image_sha256
        ok += same
        print(f"{'✓' if same else '✗'} {row['rid']}\n"
              f"    참조   {ref.render()}\n"
              f"    토큰   {which}\n"
              f"    받음   {len(data)} bytes · {media} · sha={got[:16]}\n"
              f"    기대   sha={ref.image_sha256[:16]}")
    print(f"\n{ok}/{len(rows)} 왕복 성공")
    await db.close_pool()
    return 0 if ok == len(rows) else 2


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main(int(sys.argv[1]) if len(sys.argv) > 1 else 3)))
