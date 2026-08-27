"""풀 판정의 값을 **뽑기 전에** 계산한다 (SPEC-nexus-ko-eval-pool-sensitivity §4.5).

그 SPEC 은 자기 오류를 하나 적어 두었다:

    "표본 크기는 검정력 계산 없이 정해졌다. **그것은 오류였다**, 다음 표본이 뽑히기 전에
     크기가 정해지도록 기록해 둔다."

이 파일이 그 빚이다. 세 가지를 한다 — 지금 표본이 무엇을 말하는지, 결론을 사려면 얼마인지,
그리고 그 값이 어디서 나오는지.

**왜 모집단 개수가 답인가.** §3 의 최소 비용은 10 이고, 비용의 단위는 **쌍의 개수**다. 판정을
뒤집으려면 적수가 쌍 10개를 관련으로 승격시켜야 하므로, 풀에 관련 쌍이 10개 미만이면 판정은
뒤집힐 수 없다. 한쪽 방향으로만 성립한다 — 10개 이상이라고 해서 뒤집히는 것은 아니다(그 10개가
'맞는 자리'에 있어야 한다). 우리가 원하는 방향이 그쪽이라 이걸로 충분하다.

**초기하로 센다, 이항이 아니라.** §4.5.1 이 Clopper–Pearson(이항)을 쓰면서 그것이 근사임을
명시했다. 표본은 746 에서 **비복원**으로 뽑히므로 정확 분포는 초기하다. n/N 이 커질수록 이항은
보수적(넓은) 쪽으로 틀리고, 여기서는 n 이 커야 하므로 그 차이가 값을 바꾼다.
"""

from __future__ import annotations

import argparse
import sys
from math import comb

#: 비교 가능 부분집합의 풀 크기 (§4.5 의 모집단).
POPULATION = 746

#: 이보다 적으면 판정은 뒤집힐 수 없다 (§3 의 최소 비용).
THRESHOLD = 10

#: 상한의 신뢰수준.
ALPHA = 0.05


def p_at_most(k: int, relevant: int, n: int, population: int = POPULATION) -> float:
    """`P(K ≤ k | 모집단에 relevant 개, n 개 추출)` — 초기하."""
    if relevant > population or n > population:
        raise ValueError("모집단보다 클 수 없다")
    total = comb(population, n)
    return sum(comb(relevant, i) * comb(population - relevant, n - i)
               for i in range(0, min(k, relevant) + 1)) / total


def upper_bound(k: int, n: int, population: int = POPULATION, alpha: float = ALPHA) -> int:
    """관측 `k` 에서 모집단 관련 쌍 수의 상한 — `P(K ≤ k | R) > alpha` 인 가장 큰 `R`.

    **경계를 모집단으로 두고 위로 훑는다.** 이분탐색이 더 빠르지만 `p_at_most` 는 `R` 에 대해
    단조 감소이고, 그 단조성이 깨지면 이분탐색은 조용히 틀린 답을 준다. 여기서 측정하는 것은 속도가
    아니다.
    """
    r = k
    while r < population and p_at_most(k, r + 1, n, population) > alpha:
        r += 1
    return r


def required_n(k_rate: int, population: int = POPULATION, threshold: int = THRESHOLD,
               alpha: float = ALPHA) -> int | None:
    """상한을 `threshold` 아래로 내리는 최소 표본 크기.

    `k_rate` 는 그 표본에서 관련으로 판정될 쌍의 수 — 즉 **가정**이다. 지금까지 관측된 비율이
    유지된다고 보고 값을 매기는 것이지, 결과를 예언하는 것이 아니다. 관련이 하나라도 더 나오면
    값은 그만큼 오른다.
    """
    n = k_rate + 1
    while n <= population:
        if upper_bound(k_rate, n, population, alpha) < threshold:
            return n
        n += 1
    return None


def main(argv: list[str] | None = None) -> int:
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:  # noqa: BLE001
            pass
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--judged", type=int, default=30, help="이미 판정된 쌍 수")
    ap.add_argument("--k", type=int, default=0, help="그중 관련으로 판정된 수")
    args = ap.parse_args(argv)

    print(f"모집단 {POPULATION}쌍 · 임계 {THRESHOLD} — 이보다 적으면 판정은 뒤집힐 수 없다\n")

    ub = upper_bound(args.k, args.judged)
    print(f"지금: {args.judged}쌍 판정 · 관련 {args.k} → 상한 {ub}쌍 "
          f"({'해결' if ub < THRESHOLD else '미해결 — 상한이 임계 위'})")

    print("\n결론을 사는 값 (그 표본에서 관련이 k 개 나온다고 가정할 때):")
    print("  가정 k | 필요한 총 n | 추가로 판정할 쌍")
    for k in range(0, 4):
        need = required_n(k)
        extra = "—" if need is None else str(max(0, need - args.judged))
        print(f"    {k}    |     {need or '불가':>4}     |  {extra}")

    print("\n  값이 이렇게 비싼 이유는 임계가 낮기 때문이다 — 746 중 10 은 1.3% 이고,"
          "\n  1.3% 아래임을 표본으로 보이려면 모집단의 4분의 1을 봐야 한다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
