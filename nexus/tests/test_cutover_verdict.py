"""컷오버 판정 규칙 — **코드 한 곳**에 있는가 (사전 등록 2026-09-01).

⛔ **왜 비율로 바뀌었나.** 컷오버가 세 번 같은 자리에서 막혔다. 매번 *1판은 매번 통과하고
2판만 갈리는* 라벨 하나였다. 산수를 해 보니 `p=0.9` 인 라벨은 10회 균일을 세 번에 한 번
통과하고 다음 비교에서 41% 확률로 갈린다 — **라벨 18개에 기대 오경보 2.57.**
**"n회 균일" 은 "결정론적" 이 아니다.**

여기서 고정하는 것은 **규칙**이지 어느 회차의 숫자가 아니다.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "cv", Path(__file__).resolve().parents[1] / "scripts" / "cutover_verdict.py")
cv = importlib.util.module_from_spec(_spec)
sys.modules["cv"] = cv
_spec.loader.exec_module(cv)


def _runs(**labels):
    return {lid: {str(i): v for i, v in enumerate(vals)} for lid, vals in labels.items()}


# ── 분류는 1판만 본다 ────────────────────────────────────────────────────────

def test_a_label_stable_on_the_first_check_is_stable():
    """⛔ **바뀐 핵심.** 2판이 갈려도 1판이 고정이면 안정으로 센다 — 2판을 분류에 넣은 것이
    컷오버를 세 번 막았다."""
    stable, wobbly = cv.classify(_runs(A=[(True, True), (True, False), (True, True)]))
    assert stable == {"A": True} and wobbly == []


def test_a_label_wobbling_on_the_first_check_is_not_stable():
    stable, wobbly = cv.classify(_runs(A=[(True, True), (False, False)]))
    assert stable == {} and wobbly == ["A"]


def test_a_stably_failing_label_is_still_stable():
    """안정은 '통과' 가 아니라 '변하지 않음' 이다."""
    stable, _ = cv.classify(_runs(A=[(False, False)] * 10))
    assert stable == {"A": False}


def test_the_floor_and_the_detectable_change_are_pinned():
    assert cv.MIN_STABLE == 12
    assert cv.GAUGE_DROP_TO == 0.5


# ── 게이트와 게이지가 갈리는가 ───────────────────────────────────────────────

def _fixtures(tmp_path, base_rows, cmp_rows, n=10):
    d = tmp_path / "tests" / "eval" / "local"
    d.mkdir(parents=True, exist_ok=True)
    for tag, rows in (("BASE", base_rows), ("CUT", cmp_rows)):
        for i in range(1, n + 1):
            payload = [{"id": lid, "pass": p[i - 1], "asserted": a[i - 1]}
                       for lid, (p, a) in rows.items()]
            (d / f"cutover-{tag}-policy-{i}.json").write_text(
                json.dumps({"rows": payload}), encoding="utf-8")
    return d


def _run(tmp_path, monkeypatch, capsys, base_rows, cmp_rows):
    _fixtures(tmp_path, base_rows, cmp_rows)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", ["cv", "--classify", "BASE", "--compare", "CUT"])
    cv.main()
    return capsys.readouterr().out


def _all(v, n=10):
    return [v] * n


def test_the_second_check_wobbling_does_not_block_deployment(tmp_path, monkeypatch, capsys):
    """⛔ **세 번 되돌린 그 모양.** 이제 게이지로만 보고되고 게이트는 통과한다."""
    base = {f"L{i}": (_all(True), _all(True)) for i in range(14)}
    cut = dict(base)
    cut["L0"] = (_all(True), [True, False] * 5)          # 2판만 절반
    out = _run(tmp_path, monkeypatch, capsys, base, cut)
    assert "통과" in out and "되돌린다" not in out


def test_the_first_check_dropping_still_blocks(tmp_path, monkeypatch, capsys):
    """⛔ 대조군. 값이 아예 안 나오는 회귀는 여전히 막아야 한다."""
    base = {f"L{i}": (_all(True), _all(True)) for i in range(14)}
    cut = dict(base)
    cut["L0"] = (_all(False), _all(False))
    out = _run(tmp_path, monkeypatch, capsys, base, cut)
    assert "되돌린다" in out and "게이트 L0" in out


def test_a_large_second_check_drop_is_reported_but_not_gating(tmp_path, monkeypatch, capsys):
    base = {f"L{i}": (_all(True), _all(True)) for i in range(14)}
    cut = dict(base)
    cut["L0"] = (_all(True), _all(False))
    out = _run(tmp_path, monkeypatch, capsys, base, cut)
    assert "게이지 L0" in out and "게이트 아님" in out and "통과" in out


def test_too_few_stable_labels_holds(tmp_path, monkeypatch, capsys):
    base = {f"L{i}": ([True, False] * 5, _all(True)) for i in range(14)}
    out = _run(tmp_path, monkeypatch, capsys, base, base)
    assert "보류" in out
