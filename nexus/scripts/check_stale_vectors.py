"""저장된 벡터가 **지금 텍스트의 벡터인가** — 재계산해서 비교한다.

**알려진 원인은 고쳐졌다** (SPEC-nexus-generation-of-record §3.4): `_save_chunks` 의 ON CONFLICT 가
텍스트 변경 시 `embedding`(768)과 `tsvector_ko` 만 NULL 로 되돌리고 `embedding_1024` 는 그대로
뒀었다. 재임베딩 큐가 `WHERE <컬럼> IS NULL` 이라 그런 청크는 큐에 영영 안 들어갔고, **옛 텍스트의
벡터**로 검색됐다 — 실측 8건, 최저 코사인 0.593. 이제 레지스트리의 모든 벡터 컬럼을 무효화한다.

⭐ **먼저 범위를 좁혀라 (2026-09-06).** `nexus.index.provenance.fetch_freshness` 가 같은 출처 표의
`written_at` 을 읽어 **낡을 수 없는 행**(`written_at >= updated_at`)을 갈라낸다. 실측: 서빙 두
테넌트 2,045건 중 **1,736건이 확인 불필요**, 후보는 309건이다. 이 스크립트는 아직 전수로 도므로,
비싸면 그 감지기로 범위를 먼저 보라(`nexus status` 에 줄로 나온다).

⛔ **대조군이 비면 판정을 안 낸다** (`OPEN.md` A93, 2026-09-07 수정). 예전 대조군은 *`updated_at`
이 `2026-08-10` 인 행* 이었다. 그 날짜의 행이 사라지자 대조군이 **빈 집합**이 됐고, 코드는
대조군 줄을 **아예 안 찍은 채** 판정을 그대로 냈다 — 부재가 **침묵으로** 표현됐다. 그때 나온
`0/466` 은 *낡은 게 없다* 와 *이 계측기는 아무것도 못 가른다* 에 똑같이 들어맞았고, 실제 검증은
사람이 임시 테넌트에 낡은 벡터를 손으로 만들어서야 됐다(2 중 1, 코사인 0.6506).

지금은 대조군이 **둘이고, 둘 다 썩지 않는다**:

* **양성** — `written_at >= updated_at` 이고 모델이 같은 행. 그 벡터는 지금 본문에서 나왔으므로
  재계산하면 같아야 한다. 코퍼스가 굴러가는 한 계속 채워진다.
* **음성** — 저장된 벡터를 **다른 청크의** 새 벡터와 댄다. 양성만으로는 *늘 1.0 을 내도록
  망가진 하니스*를 못 가른다. 새 벡터가 이미 손에 있으므로 임베딩 호출이 안 는다.

둘 중 하나라도 비거나 못 넘기면 **판정을 안 찍고 exit 76** 이다.

이 평가 하니스가 남아 있는 이유는 **모르는 원인** 때문이다. 벡터가 NULL 이 아니면 커버리지는 "채워짐" 으로
세므로, *있는데 틀린* 상태를 볼 수 있는 것은 재계산뿐이다. 값싸지 않다(334청크 ≈ 35분) — 그래서
상시 검사가 아니라 손으로 부르는 도구다.

읽기 전용. 코퍼스를 건드리지 않는다.

    docker exec nexus-app python -u scripts/check_stale_vectors.py [--tenant default]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from nexus import db  # noqa: E402
from nexus.index.vector_index import configured_column  # noqa: E402
from nexus.providers.embedding import embedding_service_from_config  # noqa: E402
from nexus.utils import get_search_text  # noqa: E402

LOCAL = Path(__file__).resolve().parents[1] / "tests" / "eval" / "local"
CACHE_FILE = LOCAL / "stale-vectors-cache.json"
#: 뒤섞기 대조군. 자기 텍스트와의 코사인만으로는 "늘 1.0 을 내는 하니스" 를 못 가른다.
SHUFFLED_FILE = LOCAL / "stale-vectors-shuffled.json"

#: 같은 입력이면 같은 벡터가 나와야 한다. 부동소수 잡음만 허용한다 — 문턱을 관대하게 잡으면
#: "조금 다른 텍스트" 를 신선하다고 세게 된다. 대조군이 이 문턱을 검증한다.
FRESH_COSINE = 0.9999

BATCH = 16


class _Chunk:
    """`get_search_text()` 가 기대하는 모양. 검색 텍스트 규칙을 여기서 다시 쓰지 않는다."""

    def __init__(self, section_path: str, chunk_text: str, context_prefix: str | None):
        self.section_path = section_path
        self.chunk_text = chunk_text
        self.context_prefix = context_prefix


def _cos(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    return dot / (na * nb) if na and nb else 0.0


def _load_cache() -> dict:
    return json.loads(CACHE_FILE.read_text(encoding="utf-8")) if CACHE_FILE.exists() else {}


def _load_shuffled() -> dict:
    return json.loads(SHUFFLED_FILE.read_text(encoding="utf-8")) if SHUFFLED_FILE.exists() else {}


# ── 대조군 — **비어 있을 수 없어야 한다** ────────────────────────────────────


def positive_control(rows: list[dict], model: str) -> list[str]:
    """낡을 수 **없는** 행. 이것들이 문턱을 못 넘으면 하니스가 고장난 것이다.

    ⛔ **왜 이 정의인가 (`OPEN.md` A93).** 예전 정의는 *`updated_at` 이 특정 날짜인 행* 이었다.
    그 날짜의 행이 사라지자 대조군이 **빈 집합**이 됐고, 그래서 대조군 줄이 아예 안 찍혔다 —
    **부재가 침묵으로 표현됐다.** 그때 이 하니스는 `0/466` 을 냈는데, 만점은 *낡은 게 없다* 와
    *이 계측기는 아무것도 못 가른다* 에 똑같이 들어맞는다.

    새 정의는 날짜를 안 쓴다: **벡터가 그 행의 마지막 갱신 이후에 쓰였으면** 그 벡터는 지금
    본문에서 나온 것이므로 재계산하면 같은 값이 나와야 한다. 이 조건은 코퍼스가 굴러가는 한
    계속 채워지고, **날짜처럼 썩지 않는다.**

    ⚠ **모델도 같아야 한다.** 시각이 맞아도 다른 모델이 쓴 벡터면 지금 모델로 재계산한 값과
    다르고, 그러면 멀쩡한 하니스를 고장났다고 부르게 된다.
    """
    out = []
    for r in rows:
        w, u = r.get("written_at"), r.get("updated_at")
        if w is not None and u is not None and w >= u and r.get("model") == model:
            out.append(r["rid"])
    return out


def negative_control(shuffled: list[float], threshold: float) -> dict:
    """**뒤섞은 짝**이 문턱 아래로 떨어지는가 — 이 문턱이 무언가를 가르기는 하는가.

    ⭐ 양성 대조군만으로는 부족하다. 저장된 벡터를 자기 텍스트와 대 보면 **하니스가 늘 1.0 을
    내도록 망가져 있어도** 통과한다. 그래서 저장된 벡터를 **다른 청크의** 새 벡터와 대 본다 —
    이 리포의 한국어 평가 하니스가 이미 쓰는 대조군 설계다(*"진짜 대조군은 벡터를 청크 사이에서
    뒤섞는 것"*).

    ⚠ **중앙값으로 판정한다.** 본문이 같은 청크가 있으면 그 짝은 정당하게 1.0 이 나오므로,
    최댓값으로 판정하면 중복 하나가 대조군을 떨어뜨린다. 최댓값과 문턱 이상 개수는 **보고만**
    한다 — 그 수가 곧 중복의 크기다.
    """
    if not shuffled:
        return {"n": 0, "median": None, "max": None, "at_or_above": 0, "discriminates": False}
    s = sorted(shuffled)
    mid = len(s) // 2
    median = s[mid] if len(s) % 2 else (s[mid - 1] + s[mid]) / 2
    return {
        "n": len(s),
        "median": median,
        "max": s[-1],
        "at_or_above": sum(1 for x in s if x >= threshold),
        "discriminates": median < threshold,
    }


def controls_allow_a_verdict(pos_worst: float | None, neg: dict, threshold: float) -> tuple[bool, str]:
    """**판정을 내도 되는가.** 낼 수 없으면 그 이유를 말한다 — 조용히 넘어가지 않는다.

    ⛔ 이 함수의 존재 이유가 A93 이다. 대조군이 비면 예전 코드는 **아무 말도 안 하고** 판정을
    그대로 찍었다. 이제 비는 것 자체가 실패다.
    """
    if pos_worst is None:
        return False, "양성 대조군이 비었다 — 낡을 수 없는 행이 하나도 없어서 하니스를 검증하지 못했다"
    if pos_worst < threshold:
        return False, f"양성 대조군이 문턱을 못 넘었다({pos_worst:.6f}) — 하니스가 고장난 것이다"
    if neg["n"] == 0:
        return False, ("음성 대조군이 비었다 — 이번 실행에서 새로 계산한 행이 없어 뒤섞기 대조를 "
                       "못 했다. `--fresh` 로 캐시를 비우고 다시 돌려라")
    if not neg["discriminates"]:
        return False, (f"음성 대조군이 문턱을 안 넘겼다(중앙값 {neg['median']:.6f}) — "
                       "이 문턱은 아무것도 가르지 못한다")
    return True, ""


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tenant", default="default")
    ap.add_argument("--max-batches", type=int, default=0, help="0 이면 끝까지")
    ap.add_argument("--fresh", action="store_true",
                    help="캐시를 비우고 다시 계산한다 — 음성 대조군이 비었을 때 필요하다")
    args = ap.parse_args()

    await db.get_pool()
    try:
        col = configured_column()
        # 라벨은 **이 컬럼의 출처**에서 온다 (`chunk_vector_provenance`). 옛 `chunks.embed_model`
        # 은 행당 한 칸이라 지금 보고 있는 컬럼의 것이라는 보장이 없었다 — 여기서 그 값으로
        # 대조군을 골랐으므로, 라벨이 다른 컬럼의 것이면 대조군 자체가 틀린 표본이 된다.
        # 출처가 없는 행은 '미상' 이다(025 백필). 없는 것을 추측해 채우지 않는다.
        rows = [dict(r) for r in await db.fetch_all(
            f"SELECT c.rid, c.section_path, c.chunk_text, c.context_prefix, "
            f"       COALESCE(p.model, '(미상)') AS model, p.written_at, "
            f"       c.provenance_tier, c.updated_at, c.{col}::text AS vec "
            f"FROM chunks c JOIN documents d ON d.rid = c.doc_rid "
            f"LEFT JOIN chunk_vector_provenance p "
            f"       ON p.chunk_rid = c.rid AND p.column_name = $2 "
            f"WHERE c.tenant = $1 AND c.status = 'active' AND d.status = 'active' "
            f"  AND c.is_quarantined = false AND c.{col} IS NOT NULL "
            f"ORDER BY c.rid", args.tenant, col)]

        svc = embedding_service_from_config()
        print(f"  {args.tenant} · {col} · 청크 {len(rows)}개 · {svc.model}", flush=True)

        if args.fresh:
            CACHE_FILE.unlink(missing_ok=True)
            SHUFFLED_FILE.unlink(missing_ok=True)
        cache = _load_cache()
        shuffled = _load_shuffled()
        todo = [r for r in rows if r["rid"] not in cache]
        budget = args.max_batches or 10 ** 9
        for i in range(0, len(todo), BATCH):
            if budget <= 0:
                print(f"  예산 소진 — {len(cache)}/{len(rows)} 까지 계산됨. 다시 부르면 이어서 한다",
                      flush=True)
                break
            batch = todo[i:i + BATCH]
            texts = [get_search_text(_Chunk(r["section_path"], r["chunk_text"],
                                            r["context_prefix"])) for r in batch]
            fresh = await svc.embed_documents(texts)
            for j, (r, fresh_vec) in enumerate(zip(batch, fresh)):
                stored = [float(x) for x in r["vec"].strip("[]").split(",")]
                cache[r["rid"]] = round(_cos(stored, fresh_vec), 6)
                # **뒤섞기 대조군은 여기서 공짜다** — 새 벡터가 이미 손에 있으므로 임베딩
                # 호출이 늘지 않는다. 배치 안의 다음 청크와 짝지어 저장한다.
                if len(batch) > 1:
                    other = fresh[(j + 1) % len(batch)]
                    shuffled[r["rid"]] = round(_cos(stored, other), 6)
            CACHE_FILE.write_text(json.dumps(cache), encoding="utf-8")
            SHUFFLED_FILE.write_text(json.dumps(shuffled), encoding="utf-8")
            budget -= 1
            print(f"  {min(len(cache), len(rows))}/{len(rows)}", flush=True)
    finally:
        await db.close_pool()

    done = [r for r in rows if r["rid"] in cache]
    if len(done) < len(rows):
        print(f"\n  아직 {len(rows) - len(done)}개 남았다 — 다시 호출하라")
        return 75

    stale = [r for r in done if cache[r["rid"]] < FRESH_COSINE]

    # ── 대조군 먼저. **비어 있으면 그것이 곧 실패다** (`OPEN.md` A93) ──────────
    pos = [rid for rid in positive_control(done, svc.model) if rid in cache]
    pos_worst = min((cache[rid] for rid in pos), default=None)
    neg = negative_control([v for rid, v in shuffled.items() if rid in cache], FRESH_COSINE)

    print(f"\n  양성 대조군(낡을 수 없는 행) {len(pos)}개 · 최저 코사인 "
          f"{'—' if pos_worst is None else f'{pos_worst:.6f}'}")
    if neg["n"]:
        print(f"  음성 대조군(뒤섞은 짝) {neg['n']}개 · 중앙값 {neg['median']:.6f} · "
              f"최대 {neg['max']:.6f} · 문턱 이상 {neg['at_or_above']}개")
    else:
        print("  음성 대조군(뒤섞은 짝) 0개")

    ok, why = controls_allow_a_verdict(pos_worst, neg, FRESH_COSINE)
    if not ok:
        # ⛔ **판정을 안 찍는다.** 예전 코드는 대조군이 비어도 아래 수를 그대로 찍었고, 그
        # 침묵이 `0/466` 을 검증된 0 처럼 보이게 했다.
        print(f"\n⛔ 판정을 내지 않는다 — {why}")
        return 76

    print(f"\n  낡은 벡터 {len(stale)}/{len(done)}")
    by_label: dict[str, list[int]] = {}
    for r in done:
        k = r["model"]
        b = by_label.setdefault(k, [0, 0])
        b[0] += 1
        b[1] += 1 if cache[r["rid"]] < FRESH_COSINE else 0
    print("\n  출처별            전체   낡음")
    for k, (n, s) in sorted(by_label.items()):
        print(f"    {k:18s} {n:5d} {s:6d}")

    if stale:
        print("\n  가장 많이 어긋난 것들(코사인 낮은 순)")
        for r in sorted(stale, key=lambda x: cache[x["rid"]])[:8]:
            print(f"    {cache[r['rid']]:.4f}  {r['model']:16s} {r['rid']}")

    out = LOCAL / "stale-vectors.json"
    out.write_text(json.dumps(
        {"tenant": args.tenant, "column": col, "threshold": FRESH_COSINE,
         "total": len(done), "stale": len(stale),
         "by_label": {k: {"total": n, "stale": s} for k, (n, s) in by_label.items()}},
        ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"\n기록: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
