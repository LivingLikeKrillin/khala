"""채점기가 **모순 라벨을 볼 수 있는가.**

⛔ **왜 이 파일이 있나 (2026-08-31, 첫 서명 회차).** 소유자가 서명한 직후 점수를 냈더니
A-10(닉네임 모순 라벨)이 `언급=실패 · 주장=통과` 로 찍혔다. **2판은 1판의 부분집합**이어야
하므로 그 조합은 성립할 수 없고, 그것이 결함을 드러냈다.

결함은 둘이었다.

1. `type: conflict` 갈래가 `ok` 를 다시 계산하지 않았다. 모순 라벨은 `expect` 가 비고
   `expect_all` 만 갖는데 `ok` 는 위에서 `expect` 로만 계산돼 `any([])` = False 였다 —
   **답이 무엇이든 1판 실패.**
2. `mentioned` 가 `expect` 없는 라벨에서 무조건 False 였다. 그래서 요약이 `1판 14/15` 를
   냈는데, 빠진 하나는 답이 나빠서가 아니라 **1판이 그 라벨을 볼 수 없어서**였다.

분모에 넣고 항상 떨어뜨리는 것은 측정이 아니다. 그리고 이 파일에는 검사가 하나도 없었다.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "answer_fact_probe",
    Path(__file__).resolve().parents[1] / "scripts" / "answer_fact_probe.py")
probe = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(probe)

CONFLICT = [["12자", "12 자"], ["8자", "8 자"]]


def test_a_conflict_label_can_pass_at_all():
    """⛔ 이것이 False 로 굳어 있어서 모순 라벨은 어떤 답으로도 통과하지 못했다."""
    text = "문서 둘이 다릅니다: 한글·영문 포함 12자, 그리고 한글 8자 / 영문 16자."
    assert probe._all_groups_present(CONFLICT, probe._norm(text)) is True


def test_a_conflict_label_still_fails_when_a_value_is_missing():
    """⛔ 대조군. 통과시키려고 고친 것이 아니라 **볼 수 있게** 고친 것이다."""
    text = "닉네임은 12자 제한입니다."
    assert probe._all_groups_present(CONFLICT, probe._norm(text)) is False


def test_any_surface_form_in_a_group_counts():
    """묶음 안은 같은 값의 표기 후보다 — 하나만 맞으면 된다."""
    assert probe._all_groups_present([["30자", "30 자"]], probe._norm("최대 30 자")) is True


def test_a_plain_string_group_is_treated_as_one_surface():
    """`expect_all` 은 문자열과 묶음을 섞어 쓴다 (설계 라벨이 그렇다)."""
    assert probe._all_groups_present(["DjChangeType"], probe._norm("DjChangeType 이 온다")) is True
    assert probe._all_groups_present(["DjChangeType"], probe._norm("아무것도")) is False


def test_normalisation_ignores_spaces_and_commas():
    """`4,000` 과 `4000`, `최대 1` 과 `최대1` 은 같은 값이다."""
    assert probe._all_groups_present([["4000"]], probe._norm("4,000 건")) is True


def test_the_summary_does_not_make_a_ratio_before_signature():
    """⛔ 대조군 — 서명 전에 분수가 나오면 점수를 보고 라벨을 고칠 수 있다."""
    import re
    rows = [{"id": "X", "pass": True, "asserted": True, "mentioned": True,
             "distractor_seen": [], "chars": 10}]
    out = chr(10).join(probe.summary_lines(rows, for_signature=True))
    # 분수만 막는다 — 안내문의 `(1)`·`(2)` 같은 번호는 점수가 아니다.
    assert not re.search(r"\d+\s*/\s*\d+", out), out
