"""판정 규칙에 이가 있는가 — 특히 **잡음 폭이 검정보다 먼저 걸리는가.**

검정을 먼저 돌려 p 를 본 뒤 "그래도 잡음 범위라서" 라고 쓰면 사후 선택이다. 규칙 2 가 규칙 3
앞에 있어야 하고, 그 순서를 코드가 지켜야 한다.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.ko_eval_answer_verdict import ArmSummary, compare  # noqa: E402


def _arm(tag, per_query):
    return ArmSummary(tag=tag, per_query=per_query)


def _steady(tag, oks, n=20, runs=3):
    """회차 간 흔들림이 없는 팔 — 앞 `oks` 개가 매 회차 통과."""
    return _arm(tag, {f"q{i}": [i < oks] * runs for i in range(n)})


def test_majority_folds_one_bad_run():
    a = _arm("x", {"q1": [True, True, False], "q2": [False, False, True]})
    assert a.majority() == {"q1": True, "q2": False}


def test_the_noise_band_is_the_spread_across_runs():
    a = _arm("x", {"q1": [True, False, True], "q2": [True, True, True]})
    assert a.totals() == [2, 1, 2]
    assert a.noise_band == 1


def test_a_difference_inside_the_noise_band_is_not_tested():
    """**규칙 2 가 규칙 3 보다 먼저.** 폭 안이면 p 를 아예 내지 않는다."""
    champ = _arm("sonnet", {f"q{i}": [i < 10, i < 11, i < 10] for i in range(20)})   # 폭 1
    chal = _steady("opus", 11)
    out = compare(champ, chal)
    assert out["noise_band"] >= 1
    assert "p" not in out and "wins" not in out
    assert "구별되지 않는다" in out["decision"]


def test_a_difference_beyond_the_band_but_thin_is_underpowered():
    """폭을 넘어도 불일치쌍이 모자라면 '차이 없음' 이 아니라 '검정력 부족' 이다."""
    champ = _steady("sonnet", 10)
    chal = _arm("opus", {f"q{i}": [i < 10 or i in (10, 11)] * 3 for i in range(20)})
    out = compare(champ, chal)
    assert out["difference"] == 2 and out["noise_band"] == 0
    assert "p" not in out
    assert "검정력 부족" in out["decision"]


def test_a_clear_win_is_reported_with_a_p_value():
    champ = _steady("sonnet", 6)
    chal = _steady("opus", 14)
    out = compare(champ, chal)
    assert out["wins"] == 8 and out["losses"] == 0
    assert out["p"] <= 0.05 and "opus 우세" in out["decision"]


def test_the_incumbent_survives_a_non_significant_result():
    """결론 못 내면 현직 유지 — 규칙 5."""
    champ = _steady("sonnet", 10)
    chal = _arm("opus", {**{f"q{i}": [True] * 3 for i in range(4)},
                         **{f"q{i}": [False] * 3 for i in range(4, 10)},
                         **{f"q{i}": [True] * 3 for i in range(10, 16)},
                         **{f"q{i}": [False] * 3 for i in range(16, 20)}})
    out = compare(champ, chal)
    assert out["difference"] == 0
    assert "유지" in out["decision"]


def test_only_queries_both_arms_ran_are_compared():
    """한쪽만 돈 질의를 세면 팔의 크기 차이가 승패로 둔갑한다."""
    champ = _arm("a", {"q1": [True] * 3, "q2": [True] * 3})
    chal = _arm("b", {"q1": [True] * 3})
    assert compare(champ, chal)["queries"] == 1


# ── 러너 배선 (2026-08-08) ───────────────────────────────────────────────────
#
# 누적 파일을 쓰는 코드가 **편집 실패로 빠진 채** 3회 실행이 다 돌았다. `--tag` 는 먹었으므로
# 새 버전이 도는 것처럼 보였고, 한 시간을 쓴 뒤에야 파일이 없다는 걸 알았다. 배선은 눈으로 확인할
# 게 아니라 검사로 박는 것이다.


def test_the_runner_actually_appends_to_the_accumulating_file():
    src = (ROOT / "scripts" / "ko_eval_answer_run.py").read_text(encoding="utf-8")
    assert "RUNS.open(" in src, "누적 파일을 여는 코드가 없다 — 잡음 폭을 낼 수 없다"
    assert '"a"' in src.split("RUNS.open(")[1][:40], "append 가 아니면 회차가 서로를 지운다"
    assert '"ok":' in src, "질의별 ok 가 없으면 다수결을 못 낸다"


def test_the_runner_takes_a_tag_and_a_model():
    src = (ROOT / "scripts" / "ko_eval_answer_run.py").read_text(encoding="utf-8")
    assert '"--tag"' in src and '"--model"' in src
