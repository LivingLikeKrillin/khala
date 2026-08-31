"""설계 문서 **사본**을 정책 코퍼스에서 내리고 되돌린다 (SPEC-nexus-design-corpus-cutover).

⛔ **되돌리기가 내리기만큼 쉬워야 한다.** SPEC §3.2 R-3 는 역연산을 요구하는데, 122건을
`nexus doc hide` 로 하나씩 내리고 되돌릴 때 손으로 붙여 넣게 두면 **역연산은 문서에만 있고
실무에는 없다.** 그래서 같은 술어로 양방향을 돈다.

**술어는 SPEC §1.1 이 정한 것 하나다** —

    tenant = 'default' AND source_uri ~ '^default:(docs|modules|repo)/'

그 술어가 잡는 것이 전부 `design_docs` 에 정본을 갖는다는 것을 경로·해시·제목 셋으로 확인했다
(§1.3). 이 스크립트는 **실행 전에 그 셋을 다시 확인하고**, 하나라도 어긋나면 멈춘다 — 코퍼스는
살아 있고, 어제의 측정이 오늘의 사실이라는 보장이 없다.

    python scripts/cutover_copy.py                 # 보기만 (기본값)
    python scripts/cutover_copy.py --hide --yes
    python scripts/cutover_copy.py --restore --yes
"""

from __future__ import annotations

import argparse
import asyncio

from nexus import db

#: SPEC §1.1. **여기 말고 다른 곳에 사본의 정의를 두지 않는다.**
COPY_PREDICATE = "tenant = 'default' AND source_uri ~ '^default:(docs|modules|repo)/'"


async def _candidates(status: str) -> list[dict]:
    rows = await db.fetch_all(
        f"""
        SELECT d.rid, d.title, d.source_uri, d.hash, d.hold,
               EXISTS (SELECT 1 FROM documents e WHERE e.tenant='design_docs'
                       AND e.hash = d.hash AND e.hash <> '')            AS by_hash,
               EXISTS (SELECT 1 FROM documents e WHERE e.tenant='design_docs'
                       AND e.title = d.title)                           AS by_title,
               EXISTS (SELECT 1 FROM documents e WHERE e.tenant='design_docs'
                       AND substring(e.source_uri FROM 13)
                           = regexp_replace(substring(d.source_uri FROM 9), '^docs/', ''))
                                                                        AS by_path
          FROM documents d
         WHERE {COPY_PREDICATE} AND d.status = $1::resource_status
         ORDER BY d.source_uri
        """, status)
    return [dict(r) for r in rows]


def _refuse_unless_every_copy_has_its_source(rows: list[dict]) -> None:
    """⛔ 정본 없는 문서를 내리면 **설계 문서가 영구 소실**된다 (비평 I-003).

    셋 중 하나라도 어긋나면 멈춘다. 셋을 다 보는 이유는 어느 하나도 신원이 아니기 때문이다 —
    제목은 우연히 같을 수 있고, 해시는 적재 경로가 다르면 갈리고, 경로는 이름이 바뀌면 끊긴다.
    """
    bad = [r for r in rows if not (r["by_hash"] and r["by_title"] and r["by_path"])]
    if bad:
        for r in bad[:5]:
            print(f"  ⛔ 정본 대응 실패 {r['source_uri']} "
                  f"(해시={r['by_hash']} 제목={r['by_title']} 경로={r['by_path']})")
        raise SystemExit(
            f"멈춘다 — {len(bad)}건이 정본 대응에 실패했다. 술어가 사본 아닌 것을 잡았거나 "
            "정본이 사라졌다. 어느 쪽이든 손으로 볼 일이지 일괄로 내릴 일이 아니다.")


async def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--hide", action="store_true", help="사본을 검색에서 내린다")
    g.add_argument("--restore", action="store_true", help="내린 사본을 되돌린다")
    ap.add_argument("--yes", action="store_true", help="실제로 실행한다 (없으면 보기만)")
    args = ap.parse_args()

    from nexus.documents.lifecycle_ops import hide_document, restore_document

    want = "soft_deleted" if args.restore else "active"
    rows = await _candidates(want)
    chunks = await db.fetch_one(
        f"""SELECT count(*) AS n FROM chunks c JOIN documents d ON d.rid = c.doc_rid
            WHERE {COPY_PREDICATE.replace('tenant', 'd.tenant').replace('source_uri', 'd.source_uri')}
              AND d.status = $1::resource_status""", want)

    print(f"술어: {COPY_PREDICATE}")
    print(f"대상: 문서 {len(rows)} · 청크 {chunks['n'] if chunks else '?'} (status={want})")
    if not rows:
        print("대상이 없다.")
        return

    _refuse_unless_every_copy_has_its_source(rows)
    print("✓ 전건이 정본 대응(해시·제목·경로) 통과")

    if not (args.hide or args.restore):
        print("\n보기만 했다. 실행하려면 --hide --yes 또는 --restore --yes")
        return
    if not args.yes:
        print("\n--yes 가 없다. 실행하지 않는다.")
        return

    op, name = (hide_document, "hide") if args.hide else (restore_document, "restore")
    done = 0
    for r in rows:
        result = await op(r["rid"], "default")
        done += 1 if result != "noop" else 0
    print(f"{name}: {done}건 처리 (noop {len(rows) - done})")
    print("되돌리려면: python scripts/cutover_copy.py "
          f"--{'restore' if args.hide else 'hide'} --yes")


async def _run() -> None:
    # ⛔ 루프를 **한 번만** 연다. `asyncio.run` 을 두 번 부르면 두 번째 루프가 첫 루프의
    # 커넥션을 닫으려다 `Event loop is closed` 로 터진다 — 실제로 그렇게 터졌다.
    try:
        await main()
    finally:
        await db.close_pool()


if __name__ == "__main__":
    asyncio.run(_run())
