"""풀 판정 값 계산에 이가 있는가.

이 계산이 하는 일은 **결론을 사는 값을 매기는 것**이고, 값이 틀리면 사지 말아야 할 것을 사거나
사야 할 것을 안 사게 된다. 그래서 여기서 측정하는 것은 "숫자가 나온다" 가 아니라 **틀린 방향으로
기울지 않는다** 이다.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.ko_eval_pool_power import (  # noqa: E402
    POPULATION,
    THRESHOLD,
    p_at_most,
    required_n,
    upper_bound,
)


def test_the_probability_is_a_probability():
    assert p_at_most(0, 0, 30) == 1.0, "관련이 0이면 0개를 뽑을 확률은 1이다"
    assert p_at_most(0, POPULATION, 30) == 0.0, "전부 관련이면 0개는 불가능하다"
    assert 0.0 < p_at_most(0, 50, 30) < 1.0


def test_more_relevant_pairs_make_an_empty_sample_less_likely():
    """`upper_bound` 가 위로 훑는 것은 이 단조성에 기댄다. 깨지면 상한이 조용히 틀린다."""
    ps = [p_at_most(0, r, 30) for r in range(0, 120, 10)]
    assert ps == sorted(ps, reverse=True)


def test_a_bigger_sample_never_loosens_the_bound():
    bounds = [upper_bound(0, n) for n in (30, 60, 120, 200)]
    assert bounds == sorted(bounds, reverse=True), bounds


def test_finding_a_relevant_pair_raises_the_bound():
    """관련이 나올수록 모집단 추정은 올라가야 한다 — 반대면 부호가 뒤집힌 것이다."""
    assert upper_bound(0, 100) < upper_bound(1, 100) < upper_bound(2, 100)


def test_the_sample_already_taken_does_not_resolve_it():
    """n=30 · k=0 은 상한 69 로, 임계 10 위다. '미해결' 이 결론이었고 그대로여야 한다.

    이 값이 10 아래로 내려가면 30쌍짜리 표본이 결론을 샀다는 뜻이고, 그건 사실이 아니다.
    """
    assert upper_bound(0, 30) == 69
    assert upper_bound(0, 30) > THRESHOLD


def test_the_price_is_reported_and_is_large():
    """작게 나오면 사지 말아야 할 것을 사게 된다. 실제 값은 모집단의 4분의 1이다."""
    n0 = required_n(0)
    assert n0 == 192
    assert n0 > POPULATION // 4
    # 관련이 나오면 값이 오른다 — 내려가면 계산이 뒤집힌 것이다
    assert required_n(0) < required_n(1) < required_n(2)


def test_the_hypergeometric_is_tighter_than_the_binomial_here():
    """§4.5.1 은 Clopper–Pearson(이항)을 쓰면서 근사임을 명시했다.

    비복원 추출이라 정확 분포는 초기하이고, n 이 클수록 이항은 **보수적(넓은)** 쪽으로 틀린다.
    값을 매기는 데 쓰는 것이 그 차이라, 어느 쪽이 넓은지를 못박는다.
    """
    n = 192
    hyper = upper_bound(0, n)
    # 이항 상한: (1 - n/N)^R = 0.05 를 R 에 대해 푼 것의 정수 하한
    import math
    binom = math.floor(math.log(0.05) / math.log(1 - n / POPULATION))
    assert hyper <= binom, f"초기하 {hyper} 가 이항 {binom} 보다 넓다 — 방향이 뒤집혔다"


def test_it_refuses_an_impossible_population():
    with pytest.raises(ValueError):
        p_at_most(0, POPULATION + 1, 30)
