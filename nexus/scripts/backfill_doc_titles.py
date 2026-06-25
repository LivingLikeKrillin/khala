"""기존 문서 제목 백필 — 파일명(UUID)으로 떨어진 title 을 본문 첫 헤딩으로 복구.

적재 시점 fix(ingest/title.derive_title)는 향후 문서에만 적용된다. 이미 적재되어
title 이 파일명 폴백(source_uri basename)인 문서는 이 스크립트로 본문 첫 헤딩에서
사람이 읽는 제목을 복구한다. title 은 표시 전용(rid·검색 인덱스 불변)이라 안전.

멱등: title 이 파일명 폴백과 정확히 같은 문서만 손댄다(이미 실제 제목이면 skip).
기본 dry-run. 적용하려면 --apply.

    docker exec nexus-app python -m scripts.backfill_doc_titles          # dry-run
    docker exec nexus-app python -m scripts.backfill_doc_titles --apply  # 적용
"""

from __future__ import annotations

import asyncio
import sys

from nexus import db
from nexus.ingest.title import first_heading


async def backfill(apply: bool) -> int:
    pool = await db.get_pool()
    updated = 0
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT d.rid, d.source_uri, d.title,
                   (SELECT string_agg(c.chunk_text, E'\n' ORDER BY c.chunk_index)
                      FROM chunks c WHERE c.doc_rid = d.rid) AS body
            FROM documents d
            WHERE d.status = 'active'
            """
        )
        for r in rows:
            # title 이 파일명 폴백(source_uri 의 tenant: 뒤 basename)과 같을 때만 대상.
            fallback = r["source_uri"].split(":", 1)[-1]
            if r["title"] != fallback:
                continue  # 이미 실제 제목 — 멱등 skip
            heading = first_heading(r["body"])
            if not heading or heading == r["title"]:
                continue
            print(f"  {r['rid']}: {r['title']!r} -> {heading!r}")
            if apply:
                await conn.execute(
                    "UPDATE documents SET title = $1, updated_at = now() WHERE rid = $2",
                    heading, r["rid"],
                )
            updated += 1
    print(f"{'applied' if apply else 'dry-run'}: {updated} document(s)")
    return updated


if __name__ == "__main__":
    asyncio.run(backfill(apply="--apply" in sys.argv))
