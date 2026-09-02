"""점수를 낸 실행은 **그 답변 원문을 갖고 있어야 한다**, 그리고 갈린 회차를 가리켜야 한다.

⛔ **왜 생겼나 (실측 2026-09-02).** 컷오버 판정에 쓴 실행들이 요약만 남기고 원문을 버렸다.
그래서 *"2판이 왜 이 라벨에서 갈렸는가"* 를 **다시 볼 방법이 없었다** — 답변 백엔드에
temperature·seed 가 없으므로 같은 답변을 다시 만들 수도 없다.

그 공백이 실제로 값을 치렀다: 미결 `A28` 이 *"A-3·A-5 가 2판만 실패한다"* 는 진단을 달고
앉아 있었는데, 실물을 보니 **두 라벨 모두 10/10** 이었다. 원문이 없으니 아무도 대조하지
못했고, 그 사이 진단은 낡은 채로 다음 작업의 근거가 될 뻔했다.

이 리포는 같은 일로 이미 한 번 3시간을 태우고 *"채점기 리포트는 답변 원문 사이드카를 남긴다"* 고
적어 뒀다. 그런데 그 규율이 **옵션 하나 뒤에** 있었고, 판정 실행이 그 옵션을 안 켰다.
"""

from __future__ import annotations

from scripts.answer_fact_probe import sidecar_path
from scripts.cutover_verdict import flips


# ── 원문을 남기는가 ──────────────────────────────────────────────────────────

def test_a_scored_run_keeps_its_answers_without_being_asked():
    """⛔ 핵심. `--out` 을 주면 원문 자리도 같이 정해진다 — 켜는 것을 잊을 자리가 없다."""
    assert sidecar_path("tests/eval/local/cutover-CUT-policy-3.json", "", False) \
        .endswith("cutover-CUT-policy-3.answers.json")


def test_an_explicit_path_still_wins():
    assert sidecar_path("a.json", "somewhere/else.json", False) == "somewhere/else.json"


def test_it_can_be_turned_off_on_purpose():
    """끄는 길은 남긴다 — 다만 **명시해야** 꺼진다."""
    assert sidecar_path("a.json", "", True) == ""
    assert sidecar_path("a.json", "b.json", True) == ""


def test_no_out_means_no_sidecar():
    """점수를 파일로 안 남기는 실행은 원문도 안 남긴다 — 짝이 맞는다."""
    assert sidecar_path("", "", False) == ""


# ── 갈린 회차를 가리키는가 ───────────────────────────────────────────────────

def _runs(**per_label):
    """`{라벨: {회차: (1판, 2판)}}`."""
    return {lid: {run: vals for run, vals in runs.items()}
            for lid, runs in per_label.items()}


def test_it_names_the_runs_where_the_label_fell():
    """숫자만 내면 다음 사람이 원문을 못 찾고, 못 찾으면 진단이 추측이 된다."""
    runs = _runs(A9={"1": (True, True), "4": (True, False), "8": (True, False)})
    assert flips(runs, "A9", 1) == ["4", "8"]


def test_a_label_that_never_fell_names_nothing():
    """대조군 — 전건 통과 라벨이 회차를 내면 읽는 사람이 없는 결함을 찾으러 간다."""
    runs = _runs(A3={"1": (True, True), "2": (True, True)})
    assert flips(runs, "A3", 1) == []


def test_an_unknown_label_is_empty_not_an_error():
    assert flips({}, "nope", 1) == []


def test_the_first_ruler_is_reachable_by_the_same_call():
    """인덱스 0 = 1판. 두 채점기가 같은 함수를 지난다 — 사본을 두지 않는다."""
    runs = _runs(X={"1": (False, True), "2": (True, True)})
    assert flips(runs, "X", 0) == ["1"]
    assert flips(runs, "X", 1) == []
