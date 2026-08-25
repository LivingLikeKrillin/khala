"""A13 컷오버 백필 — 기존 청크에 **문서 제목 접두사**를 넣고, 그 텍스트에서 파생된 것을 무효화한다.

적재 경로는 이미 `utils.context_prefix_for` 를 쓴다(파이프라인). 이 스크립트는 **이미 앉아 있는
청크**를 같은 규칙으로 맞추는 일회성 도구다. 규칙을 여기 베끼지 않는다 — 사본이 생기는 순간
배포된 것과 백필된 것이 갈릴 수 있고, 그 차이는 화면에 안 보인다.

**왜 벡터를 지우나.** `search_text` 는 `COALESCE(context_prefix, '[' || section_path || ']')
|| ' ' || chunk_text` 다. 접두사가 바뀌면 그 텍스트로 만든 임베딩과 tsvector 는 **옛 텍스트의
것**이 된다. 안 지우면 재임베딩 큐(`WHERE <컬럼> IS NULL`)에 안 들어가고 조용히 옛 벡터로
검색된다 — ADR-0006 이 "stale-vector retrieval drift" 라 부른 그 상태다.

⛔ **고정된 평가 팩은 대상이 아니다.** `ko_eval_*` 는 과거 측정(KURE 비교·A13 1회차 등)이 그
코퍼스 위에서 재현돼야 하는 스냅샷이다. 접두사를 넣으면 그 숫자들이 재현 불가가 된다.
이 스크립트는 그 테넌트를 **기본으로 거부**하고, 넘기려면 이름을 정확히 대야 한다.

    docker exec nexus-app python -m scripts.backfill_context_prefix --tenant default          # 계획만
    docker exec nexus-app python -m scripts.backfill_context_prefix --tenant default --apply  # 적용
    docker exec nexus-app nexus reembed run --tenant default                                   # 그 다음 재임베딩
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from nexus import db  # noqa: E402
from nexus.utils import context_prefix_for  # noqa: E402

#: 과거 측정이 재현돼야 하는 코퍼스. 실수로 지나가는 일이 없게 **접두 일치**로 막는다.
PINNED_PREFIXES = ("ko_eval_",)


async def run(tenant: str, apply: bool) -> int:
    rows = await db.fetch_all(
        """
        SELECT c.rid, c.section_path, c.context_prefix, d.title
          FROM chunks c JOIN documents d ON d.rid = c.doc_rid
         WHERE c.tenant = $1 AND c.status = 'active'
        """,
        tenant,
    )
    if not rows:
        print(f"대상 청크 없음: {tenant}")
        return 1

    changes: list[tuple[str, str | None]] = []
    for r in rows:
        want = context_prefix_for(r["title"] or "", r["section_path"] or "root")
        if want != r["context_prefix"]:
            changes.append((r["rid"], want))

    print(f"테넌트 {tenant} · 활성 청크 {len(rows)} · 접두사가 바뀌는 청크 **{len(changes)}**")
    if not changes:
        return 0
    if not apply:
        for rid, want in changes[:5]:
            print(f"    {rid}  →  {want}")
        print("  (계획만 출력했다. 적용하려면 --apply)")
        return 0

    from nexus.index.vector_index import VECTOR_COLUMNS

    # 벡터 컬럼은 화이트리스트에서만 온다 — 설정값이 SQL 에 닿는 경로가 아니다.
    nulls = ", ".join(f"{c} = NULL" for c in sorted(VECTOR_COLUMNS))
    await db.execute_many(
        f"UPDATE chunks SET context_prefix = $2, {nulls}, tsvector_ko = NULL, "
        f"updated_at = now() WHERE rid = $1",
        [(rid, want) for rid, want in changes],
    )
    print(f"  적용 {len(changes)}건 — 벡터·tsvector 무효화됨.")
    print("  다음: `nexus reembed run` 으로 벡터를, 재적재 없이 BM25 는 "
          "`nexus reembed`/적재 경로가 채운다.")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--tenant", required=True)
    ap.add_argument("--apply", action="store_true", help="실제로 쓴다(기본은 계획만)")
    ap.add_argument("--i-know-this-is-a-pinned-eval-pack", action="store_true",
                    help="고정 평가 팩에도 강행한다. 과거 측정이 재현 불가가 된다.")
    args = ap.parse_args(argv)

    if (any(args.tenant.startswith(p) for p in PINNED_PREFIXES)
            and not args.i_know_this_is_a_pinned_eval_pack):
        print(f"⛔ {args.tenant} 는 고정된 평가 팩이다 — 접두사를 넣으면 그 위에서 잰 숫자들이 "
              "재현 불가가 된다. 정말이면 --i-know-this-is-a-pinned-eval-pack.")
        return 2

    async def _go() -> int:
        await db.get_pool()
        try:
            return await run(args.tenant, args.apply)
        finally:
            await db.close_pool()

    return asyncio.run(_go())


if __name__ == "__main__":
    sys.exit(main())
