"""컷오버 판정 규칙 — **코드 한 곳**에 있는가.

⛔ 1차 시도에서 판정을 매번 손으로 짰다. 그때마다 안정 라벨의 정의와 비교 방식을 다시 썼고,
그 상태에서 오경보 하나가 컷오버를 되돌렸다. **규칙이 사람 머릿속에만 있으면 사전 등록이
아니다.** 여기서 고정하는 것은 규칙 자체이지 이번 회차의 숫자가 아니다.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "cv", Path(__file__).resolve().parents[1] / "scripts" / "cutover_verdict.py")
cv = importlib.util.module_from_spec(_spec)
sys.modules["cv"] = cv
_spec.loader.exec_module(cv)


def _runs(**labels):
    return {lid: {str(i): v for i, v in enumerate(vals)} for lid, vals in labels.items()}


def test_a_label_uniform_on_both_checks_is_stable():
    stable, wobbly = cv.classify(_runs(A=[(True, True)] * 10))
    assert stable == {"A": (True, True)} and wobbly == []


def test_a_label_wobbling_on_the_second_check_alone_is_not_stable():
    """⛔ 오경보를 낸 바로 그 모양 — 1판은 매번 통과하고 2판만 갈린다."""
    stable, wobbly = cv.classify(_runs(A=[(True, True), (True, False)]))
    assert stable == {} and wobbly == ["A"]


def test_a_stably_failing_label_is_still_stable():
    """안정은 '통과' 가 아니라 '변하지 않음' 이다 — 실패도 기준선이 된다."""
    stable, _ = cv.classify(_runs(A=[(False, False)] * 10))
    assert stable == {"A": (False, False)}


def test_the_floor_is_twelve():
    """사전 등록된 하한. 그 아래로는 비교가 공허하다."""
    assert cv.MIN_STABLE == 12


def test_the_script_actually_runs(tmp_path, monkeypatch, capsys):
    """⛔ **배선 검사.** 앞의 검사들은 `classify()` 만 불렀고 `main()` 은 한 번도 안 돌았다.
    그래서 제거한 인자를 참조하는 줄이 남아 있는 것을 못 잡았고, 판정을 돌리자 그 자리에서
    터졌다 — *검사가 초록인데 스크립트가 죽는다.* 이 리포가 반복해서 데인 모양이다.
    """
    import json
    d = tmp_path / "tests" / "eval" / "local"
    d.mkdir(parents=True)
    for tag in ("CLS", "X"):
        n = 10 if tag == "CLS" else 5
        for i in range(1, n + 1):
            (d / f"cutover-{tag}-policy-{i}.json").write_text(json.dumps(
                {"rows": [{"id": f"L{k}", "pass": True, "asserted": True} for k in range(14)]}),
                encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", ["cv", "--classify", "CLS", "--compare", "X"])
    cv.main()
    out = capsys.readouterr().out
    assert "전건 일치" in out
