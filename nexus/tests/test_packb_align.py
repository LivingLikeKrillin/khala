"""스냅샷을 **서명된 본문**에 맞추는 규칙 (`OPEN.md` A55).

⛔ 왜 있나 (실측 2026-09-03). 재서명 워크시트는 스냅샷과 지금 본문을 대조해 무엇이 달라졌는지
보여 준다. 그런데 스냅샷이 서명 시점과 묶여 있지 않아 스스로 흘러갔고, 본문이 달라진 문서
13장 중 **5장은 서명된 본문이 어디에도 없었다**. 결속은 해시만 저장하므로 복원되지 않는다.
볼 것이 없는 사람이 하는 일은 계산된 블록을 붙여넣는 것이고, 워크시트는 정확히 그것을 막으려고 있다.

안전 조건 하나: **지금 본문이 곧 서명된 본문인 문서만 맞춘다.** 아래 검사는 전부 그 한 줄이
지켜지는가를 본다.
"""

from __future__ import annotations

from scripts.ko_eval_packb import alignment_plan


def test_a_signed_body_that_the_snapshot_lacks_is_refreshed():
    """서명 == 라이브 != 스냅샷 — 서명이 이미 이 본문을 가리키므로 잃을 대조 근거가 없다."""
    refresh, _ = alignment_plan({"a": "x"}, {"a": "x"}, {"a": "old"})
    assert refresh == ["a"]


def test_an_expired_document_is_never_touched():
    """⛔ 이게 이 규칙의 핵심이다 — 서명 != 라이브면 스냅샷의 옛 본문이 **유일한** 대조 기준이다."""
    refresh, left = alignment_plan({"a": "signed"}, {"a": "live"}, {"a": "signed"})
    assert refresh == [] and "만료" in left[0]


def test_the_reason_says_why_it_was_left_alone():
    """사유를 안 적으면 다음 사람이 강제로 맞추는 방법을 찾는다."""
    _, left = alignment_plan({"a": "signed"}, {"a": "live"}, {"a": "signed"})
    assert "대조 기준" in left[0]


def test_an_already_aligned_document_is_not_rewritten():
    refresh, left = alignment_plan({"a": "x"}, {"a": "x"}, {"a": "x"})
    assert refresh == [] and "이미 맞다" in left[0]


def test_a_document_absent_from_the_snapshot_is_left_to_extend():
    """여기서 만들지 않는다 — 더하는 것과 맞추는 것은 다른 일이고 거부 조건도 다르다."""
    refresh, left = alignment_plan({"a": "x"}, {"a": "x"}, {})
    assert refresh == [] and "extend" in left[0]


def test_a_document_missing_from_live_is_left_alone():
    refresh, left = alignment_plan({"a": "x"}, {}, {"a": "old"})
    assert refresh == [] and "라이브에 없다" in left[0]


def test_every_signed_document_is_accounted_for():
    """맞추거나 두거나 — 둘 중 하나에 반드시 들어가야 한다. 조용히 빠지면 아무도 모른다."""
    signed = {"a": "x", "b": "y", "c": "z", "d": "w"}
    refresh, left = alignment_plan(signed, {"a": "x", "b": "other", "c": "z"},
                                   {"a": "old", "b": "y", "d": "w"})
    assert len(refresh) + len(left) == len(signed)


def test_only_the_signed_documents_are_considered():
    """서명 밖의 문서를 맞추면 아무도 판정하지 않은 본문을 기준점으로 삼는 것이다."""
    refresh, left = alignment_plan({"a": "x"}, {"a": "x", "z": "q"}, {"a": "old", "z": "old"})
    assert refresh == ["a"] and not any("z" in line for line in left)


def test_the_output_order_is_stable():
    """실행마다 순서가 바뀌면 두 실행의 출력을 대조할 수 없다."""
    signed = {"c": "1", "a": "1", "b": "1"}
    live = dict(signed)
    assert alignment_plan(signed, live, {})[1] == sorted(alignment_plan(signed, live, {})[1])
