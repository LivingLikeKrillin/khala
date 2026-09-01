"""컷오버 판정 — 사전 등록된 규칙을 **코드 한 곳**에서 적용한다.

⛔ **왜 스크립트인가 (2026-08-31).** 1차 시도에서 판정을 매번 손으로 짜서 돌렸고, 그때마다
파일 형식·안정 라벨 정의·비교 방식을 다시 썼다. 판정 규칙이 **읽는 사람 머릿속에만** 있으면
그것은 사전 등록이 아니다. 규칙은 이렇다 (`tests/eval/answer-facts/README.md`):

  · 안정성 **분류는 10회 한 번** — 통과율 0.5 인 라벨이 n회에 균일하게 보일 확률은 `2×0.5ⁿ`
    이고, n=5 면 라벨 18개 중 기대 오분류가 **1.12** 다. 실제로 하나 났고 그것이 컷오버를
    오경보로 되돌렸다.
  · 비교는 시점별 **5회**, **분류가 안정이라 한 라벨만**.
  · 잔존 라벨이 **12개 미만이면 부착 보류**.
  · 판정은 **양방향** — T2 가 기준선보다 **올라도** 원인 규명 전에는 채택하지 않는다.

    python scripts/cutover_verdict.py --classify CLS --compare T2
"""

from __future__ import annotations

import argparse
import collections
import glob
import io
import json

MIN_STABLE = 12
ROOT = "tests/eval/local"


def load(tag: str) -> dict[str, dict[str, tuple[bool, bool]]]:
    runs: dict[str, dict[str, tuple[bool, bool]]] = collections.defaultdict(dict)
    for f in sorted(glob.glob(f"{ROOT}/cutover-{tag}-*.json")):
        run = f.rsplit("-", 1)[-1].split(".")[0]
        for r in json.load(io.open(f, encoding="utf-8"))["rows"]:
            runs[r["id"]][run] = (bool(r["pass"]), bool(r["asserted"]))
    return runs


def classify(runs) -> tuple[dict[str, tuple[bool, bool]], list[str]]:
    """`(안정 라벨 → 고정값, 흔들린 라벨)`. 회차 수도 함께 본다 — 적으면 분류가 아니다."""
    stable, wobbly = {}, []
    for lid, v in sorted(runs.items()):
        p = {x[0] for x in v.values()}
        a = {x[1] for x in v.values()}
        if len(p) == 1 and len(a) == 1:
            stable[lid] = (next(iter(p)), next(iter(a)))
        else:
            wobbly.append(lid)
    return stable, wobbly


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--classify", required=True, help="분류에 쓸 태그 (10회)")
    ap.add_argument("--compare", help="비교할 시점 태그 (5회)")
    args = ap.parse_args()

    cls_runs = load(args.classify)
    n_runs = max((len(v) for v in cls_runs.values()), default=0)
    stable, wobbly = classify(cls_runs)
    false_rate = 2 * 0.5 ** n_runs if n_runs else 1.0

    print(f"분류 태그 {args.classify} · 회차 {n_runs} · 라벨 {len(cls_runs)}")
    print(f"  안정 {len(stable)} · 흔들림 {len(wobbly)} {wobbly}")
    print(f"  ⚠ 이 회차 수에서 경계 라벨이 균일하게 보일 확률 {false_rate*100:.2f}% "
          f"· 라벨 {len(cls_runs)}개 중 기대 오분류 {false_rate*len(cls_runs):.2f}")
    if len(stable) < MIN_STABLE:
        print(f"⛔ 잔존 {len(stable)} < {MIN_STABLE} — 사전 등록 규칙에 따라 **부착 보류**")
        return
    if not args.compare:
        print(f"✓ 잔존 {len(stable)} ≥ {MIN_STABLE} — 진행 가능")
        return

    cmp_runs = load(args.compare)
    diff = []
    for lid, fixed in stable.items():
        got = set(cmp_runs.get(lid, {}).values())
        if got != {fixed}:
            diff.append((lid, fixed, sorted(got)))

    # 기준선은 **분류 회차 그 자체**다 — 분류는 기준선 조건에서 돌렸다.
    print(f"\n비교 {args.compare} vs 기준선(분류 회차) {args.classify}")
    for lid, fixed, got in diff:
        print(f"  {lid}: 기준 {fixed} → {got}")
    if diff:
        print(f"⛔ 다른 라벨 {len(diff)} — **되돌린다** "
              "(양방향: 올라도 원인 규명 전에는 채택하지 않는다)")
    else:
        print(f"✓ 잔존 {len(stable)} 라벨 전건 일치 — 통과")


if __name__ == "__main__":
    main()
