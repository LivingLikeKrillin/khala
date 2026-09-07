"""저장된 `tsvector_ko` 가 **지금 텍스트의 색인인가** — 다시 토큰화해서 비교한다.

⛔ **왜 있나 (`OPEN.md` A92).** 이 리포는 파생물이 낡았는데 복구 큐가 못 보는 결함을 두 번
겪었다. 2026-09-06 감사에서 파생물 여섯을 훑었더니 넷은 해시 도장으로 닫혀 있었고, 벡터에는
`written_at` 감지기가 붙었다. **남은 하나가 `tsvector_ko`** 였다 — 무효화는 `_invalidate_derived`
가 같이 걸어 주지만, *있는데 틀린* 상태를 볼 방법이 **하나도 없었다.**

⭐ **여기는 벡터보다 훨씬 싸다.** 벡터는 재계산이 임베딩 호출이라 수십 분이 들고, 그래서 먼저
범위를 좁히는 감지기가 필요했다. tsvector 는 mecab-ko 토큰화라 모델도 네트워크도 없다 —
**감지기가 곧 측정**이고, 전수로 돌 수 있다.

⭐ **그리고 이 재계산은 두 가지를 동시에 잡는다.**

1. 텍스트가 바뀌었는데 색인이 안 따라간 것 (`WHERE tsvector_ko IS NULL` 큐가 구조적으로 못 보는 것)
2. **mecab-ko 사전·토크나이저가 바뀌어 전량이 낡은 것** — 저장분은 옛 사전으로, 재계산은 지금
   사전으로 만들어지므로 갈린다. 행은 하나도 안 바뀌므로 다른 어떤 신호로도 안 보인다.

⚠ **대조군이 없으면 이 하니스도 A93 이 된다.** 어제 낡음 하니스의 대조군이 날짜에 박혀 빈
집합이 됐고, 그래서 `0/466` 이 *"낡은 게 없다"* 인지 *"아무것도 못 가른다"* 인지 구별되지
않았다. 그래서 여기도 **뒤섞기 대조군**을 같이 돌린다: 한 청크의 토큰을 **다른 청크의** 저장
tsvector 와 대면 달라야 한다. 안 다르면 이 비교는 아무 말도 못 하는 것이다.

⚠ **전부 어긋나면 그것도 의심한다.** 100% 불일치는 코퍼스가 전부 낡은 것보다 **이 스크립트의
토큰화가 색인기와 다르다**는 뜻일 가능성이 높다. 그 경우 개수를 결함으로 보고하지 않는다.

읽기 전용. 코퍼스를 건드리지 않는다.

    docker exec nexus-app python -u scripts/check_stale_bm25.py [--tenant default]
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

if sys.platform == "win32":          # cp949 콘솔이 ⚠ 에서 죽는다
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:                # noqa: BLE001
        pass

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from nexus import db  # noqa: E402
from nexus.index.bm25 import active_tokenizer  # noqa: E402
from nexus.utils import get_search_text  # noqa: E402


class _Chunk:
    """`get_search_text()` 가 기대하는 모양. 검색 텍스트 규칙을 여기서 다시 쓰지 않는다."""

    def __init__(self, section_path: str, chunk_text: str, context_prefix: str | None):
        self.section_path = section_path
        self.chunk_text = chunk_text
        self.context_prefix = context_prefix


def verdict(*, checked: int, mismatched: int, shuffled_matched: int, shuffled_n: int) -> dict:
    """**판정을 내도 되는가, 그리고 무엇을 말하는가.** 순수·결정론.

    규칙 셋이고, 전부 *수를 못 믿는 경우*를 먼저 거른다:

    * `checked == 0` — 볼 것이 없다. 0 을 결과로 내지 않는다.
    * `shuffled_n > 0` 인데 뒤섞은 짝이 **하나라도 일치** — 비교가 서로 다른 텍스트를 같다고
      부른다. 이 비교는 아무 말도 못 한다.
    * `mismatched == checked` (전수 불일치) — 코퍼스가 전부 낡았다기보다 **토큰화가 색인기와
      다르다**는 쪽이 훨씬 그럴듯하다. 개수를 결함으로 보고하지 않는다.
    """
    if checked == 0:
        return {"usable": False, "stale": None,
                "why": "볼 행이 없다 — 0 을 결과로 내지 않는다"}
    if shuffled_n and shuffled_matched:
        return {"usable": False, "stale": None,
                "why": f"뒤섞은 짝 {shuffled_matched}/{shuffled_n} 이 일치한다 — "
                       "이 비교는 서로 다른 텍스트를 같다고 부른다"}
    if shuffled_n == 0:
        return {"usable": False, "stale": None,
                "why": "뒤섞기 대조군이 비었다 — 비교가 무언가를 가르는지 확인하지 못했다"}
    if mismatched == checked:
        return {"usable": False, "stale": None,
                "why": f"{checked}건이 **전부** 어긋난다 — 코퍼스가 전부 낡은 것보다 이 "
                       "스크립트의 토큰화가 색인기와 다를 가능성이 높다. 개수를 결함으로 "
                       "보고하지 않는다"}
    return {"usable": True, "stale": mismatched, "why": ""}


async def _mismatched(rids: list[str], toks: list[str]) -> set[str]:
    """저장된 tsvector 와 **다시 만든 것**이 다른 행. 비교는 DB 가 한다 —
    `to_tsvector` 의 정본은 postgres 이고, 파이썬에서 흉내 내면 셋째 진실이 생긴다."""
    rows = await db.fetch_all(
        """
        SELECT c.rid
          FROM chunks c
          JOIN unnest($1::text[], $2::text[]) AS t(rid, toks) ON t.rid = c.rid
         WHERE c.tsvector_ko IS DISTINCT FROM to_tsvector('simple', t.toks)
        """, rids, toks)
    return {r["rid"] for r in rows}


async def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--tenant", default=None, help="생략하면 모든 테넌트")
    args = ap.parse_args()

    await db.get_pool()
    try:
        rows = [dict(r) for r in await db.fetch_all(
            """
            SELECT c.rid, c.section_path, c.chunk_text, c.context_prefix, c.tenant
              FROM chunks c JOIN documents d ON d.rid = c.doc_rid
             WHERE c.status = 'active' AND d.status = 'active'
               AND c.is_quarantined = false AND c.tsvector_ko IS NOT NULL
               AND ($1::text IS NULL OR c.tenant = $1)
             ORDER BY c.rid
            """, args.tenant)]
        print(f"  대상 {len(rows)}청크 · 토크나이저 {type(active_tokenizer()).__name__}", flush=True)
        if not rows:
            print("⛔ 볼 행이 없다.")
            return 76

        tok = active_tokenizer()
        rids = [r["rid"] for r in rows]
        toks = [" ".join(tok.tokenize(get_search_text(
            _Chunk(r["section_path"], r["chunk_text"], r["context_prefix"])))) for r in rows]

        bad = await _mismatched(rids, toks)

        # **뒤섞기 대조군** — 한 청크의 토큰을 다음 청크의 저장 tsvector 와 댄다. 여기서
        # 일치가 나오면 비교 자체가 아무것도 안 가르는 것이다. 값이 이미 손에 있어 공짜다.
        shifted = toks[1:] + toks[:1] if len(rows) > 1 else []
        shuffled_bad = await _mismatched(rids, shifted) if shifted else set()
        shuffled_matched = len(shifted) - len(shuffled_bad) if shifted else 0

        v = verdict(checked=len(rows), mismatched=len(bad),
                    shuffled_matched=shuffled_matched, shuffled_n=len(shifted))

        print(f"\n  뒤섞기 대조군 {len(shifted)}개 · 일치 {shuffled_matched}개 (0 이어야 한다)")
        if not v["usable"]:
            print(f"\n⛔ 판정을 내지 않는다 — {v['why']}")
            return 76

        print(f"\n  낡은 색인 {v['stale']}/{len(rows)}")
        if bad:
            by_tenant: dict[str, int] = {}
            for r in rows:
                if r["rid"] in bad:
                    by_tenant[r["tenant"]] = by_tenant.get(r["tenant"], 0) + 1
            print("\n  테넌트별")
            for t, n in sorted(by_tenant.items()):
                print(f"    {t:18s} {n:5d}")
            print("\n  앞쪽 몇 개")
            for rid in sorted(bad)[:8]:
                print(f"    {rid}")
            print("\n⚠ 이 수는 **두 원인을 안 가른다** — 텍스트가 바뀌었는데 색인이 안 따라간 "
                  "것과, mecab-ko 사전이 바뀌어 전량이 낡은 것. 가르려면 분포를 봐라: "
                  "일부면 앞쪽, 거의 전부면 뒤쪽이다.")
        return 0
    finally:
        await db.close_pool()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
