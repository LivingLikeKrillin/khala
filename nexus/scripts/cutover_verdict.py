"""컷오버 판정 — 사전 등록된 규칙을 **코드 한 곳**에서 적용한다.

⛔ **왜 비율인가 (사전 등록 2026-09-01).** 컷오버가 세 번 같은 자리에서 막혔다. 매번
*1판은 매번 통과하고 2판만 갈리는* 라벨 하나 때문이었다. 산수를 해 보니 설계가 그렇게 되어
있었다 — 통과율 `p` 인 라벨이 10회 균일할 확률 × 다음 비교에서 갈릴 확률은 `p=0.9` 에서
**라벨 18개 기대 오경보 2.57** 이다. **"n회 균일" 은 "결정론적" 이 아니고**, 집합 동일성은
`p≈0.5` 만 걸러낸다. 회차를 늘려도 `p=0.9` 는 계속 통과한다 — 앞선 5→10 개정은 틀린 축이었다.

**지금 규칙**

  · 기준선·비교 **둘 다 10회**.
  · **게이트는 1판**(부분일치) — 안정 라벨에서 집합 동일성. 1판은 지금까지 한 번도 안 흔들렸다.
  · **2판은 개선 게이지이지 배포 게이트가 아니다.** 답변 형식이 비결정적인 한 2판으로 막으면
    배포가 영원히 안 된다. 비율로 보고만 하고, `10/10 → ≤5/10` 일 때만 표시한다.
  · **탐지 가능한 최소 변화량**: 이 하니스는 `1.0 → ≤0.5` 만 잡는다. 그보다 작은 변화는
    **못 잡는다** — 한계이지 통과 기준이 아니다.
  · 안정 하한 12. 양방향(올라도 원인 규명 전에는 채택하지 않는다).

    python scripts/cutover_verdict.py --classify BASE --compare CUT
"""

from __future__ import annotations

import argparse
import collections
import glob
import io
import json

MIN_STABLE = 12
#: 2판이 "떨어졌다" 고 부르는 선. 이 아래로만 잡히고, 그보다 작은 변화는 못 잡는다.
GAUGE_DROP_TO = 0.5
ROOT = "tests/eval/local"


def load(tag: str) -> dict[str, dict[str, tuple[bool, bool]]]:
    runs: dict[str, dict[str, tuple[bool, bool]]] = collections.defaultdict(dict)
    for f in sorted(glob.glob(f"{ROOT}/cutover-{tag}-*.json")):
        run = f.rsplit("-", 1)[-1].split(".")[0]
        for r in json.load(io.open(f, encoding="utf-8"))["rows"]:
            runs[r["id"]][run] = (bool(r["pass"]), bool(r["asserted"]))
    return runs


def classify(runs) -> tuple[dict[str, bool], list[str]]:
    """**1판으로만** 분류한다 — `라벨 → 고정된 1판 값`, 그리고 흔들린 라벨.

    2판을 분류에 넣으면 `p=0.9` 짜리가 세 번에 한 번 통과했다가 다음 비교에서 갈린다.
    그것이 컷오버를 세 번 막았다.
    """
    stable, wobbly = {}, []
    for lid, v in sorted(runs.items()):
        p = {x[0] for x in v.values()}
        if len(p) == 1:
            stable[lid] = next(iter(p))
        else:
            wobbly.append(lid)
    return stable, wobbly


def rate(runs, lid: str, idx: int) -> tuple[int, int]:
    v = runs.get(lid, {})
    return sum(1 for x in v.values() if x[idx]), len(v)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--classify", required=True, help="기준선 태그 (10회)")
    ap.add_argument("--compare", help="비교 시점 태그 (10회)")
    args = ap.parse_args()

    base = load(args.classify)
    n = max((len(v) for v in base.values()), default=0)
    stable, wobbly = classify(base)

    print(f"기준선 {args.classify} · 회차 {n} · 라벨 {len(base)}")
    print(f"  1판 안정 {len(stable)} · 흔들림 {len(wobbly)} {wobbly}")
    if n < 10:
        print(f"  ⚠ 회차가 {n} 이다 — 사전 등록은 10회다. 이 판정은 등록된 것이 아니다.")
    if len(stable) < MIN_STABLE:
        print(f"⛔ 안정 {len(stable)} < {MIN_STABLE} — **보류**")
        return
    if not args.compare:
        print(f"✓ 안정 {len(stable)} ≥ {MIN_STABLE} — 진행 가능")
        return

    cmp_runs = load(args.compare)
    gate_diff, gauge = [], []
    for lid, fixed in stable.items():
        got = {x[0] for x in cmp_runs.get(lid, {}).values()}
        if got != {fixed}:
            gate_diff.append((lid, fixed, sorted(got)))
        b_hit, b_n = rate(base, lid, 1)
        c_hit, c_n = rate(cmp_runs, lid, 1)
        if b_n and c_n and b_hit == b_n and c_hit / c_n <= GAUGE_DROP_TO:
            gauge.append((lid, f"{b_hit}/{b_n}", f"{c_hit}/{c_n}"))

    print(f"\n비교 {args.compare} vs 기준선 {args.classify}")
    print(f"  ⚠ 탐지 가능한 최소 변화량: 1.0 → ≤{GAUGE_DROP_TO:.1f}. "
          "그보다 작은 변화는 이 하니스가 못 잡는다.")
    for lid, fixed, got in gate_diff:
        print(f"  ⛔ 게이트 {lid}: 1판 기준 {fixed} → {got}")
    for lid, b, c in gauge:
        print(f"  · 게이지 {lid}: 2판 {b} → {c} (**게이트 아님** — 보고만 한다)")
    if gate_diff:
        print(f"⛔ 1판이 달라진 라벨 {len(gate_diff)} — **되돌린다**")
    else:
        print(f"✓ 안정 {len(stable)} 라벨의 1판 전건 일치 — 통과"
              + (f" (게이지 표시 {len(gauge)}건은 게이트가 아니다)" if gauge else ""))


if __name__ == "__main__":
    main()
