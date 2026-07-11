"""근거 스니펫 경계 truncation — SPEC-nexus-snippet-boundary-truncation §6.

_truncate_snippet 순수 함수: 단어/문장 중간을 자르지 않고, 가능한 많이 남기며 경계에서 자른다.
"""

from __future__ import annotations

from nexus.search.hybrid import _truncate_snippet


def test_short_text_unchanged_no_ellipsis():
    assert _truncate_snippet("짧은 근거", 20) == "짧은 근거"


def test_cuts_after_sentence_boundary_near_end():
    text = "First sentence here. Second sentence continues on and on and on."
    out = _truncate_snippet(text, 22)          # window 끝 근처에 첫 문장 종결
    assert out == "First sentence here. …"      # 문장부호 뒤에서 컷
    assert "…" in out and "Second" not in out


def test_korean_sentence_boundary():
    text = "결제는 완료된다. 다음 문장은 아주 길게 계속 이어진다 계속."
    out = _truncate_snippet(text, 12)
    assert out.startswith("결제는 완료된다.")     # 마침표 뒤, 단어 중간 아님
    assert out.endswith("…")


def test_early_boundary_falls_back_to_word_boundary():
    # 문장 종결이 너무 앞(< 0.7*max)이면 문장컷 포기, 단어경계로 내용 보존
    text = "Hi. This is a much longer continuation without any period at all here"
    out = _truncate_snippet(text, 30)
    assert not out.startswith("Hi. …")          # 이른 문장경계 안 씀
    assert out.endswith("…")
    # 단어 중간에서 안 잘림: … 를 뗀 본문이 원문의 접두사여야 한다(토큰 온전)
    body = out[:-1].rstrip()
    assert text.startswith(body)


def test_intra_token_dot_not_a_boundary():
    # '3.14159' 의 마침표는 종결부호 아님(뒤가 숫자) → 숫자 중간에서 안 자름
    text = "Version 3.14159 is the documented constant value used across the system"
    out = _truncate_snippet(text, 15)
    assert "3.1" not in out or "3.14159" in out  # '3.' 로 잘리지 않는다
    assert out.endswith("…")


def test_no_space_no_boundary_hard_cut():
    text = "a" * 50
    out = _truncate_snippet(text, 20)
    assert out == "a" * 20 + " …"                # 최후 하드컷(오늘과 동일)


def test_closing_punctuation_kept():
    text = '그는 "끝났다." 그리고 다음 이야기가 아주 길게 이어졌다 계속 계속.'
    out = _truncate_snippet(text, 14)
    # 종결부호 뒤 닫는 따옴표까지 포함
    assert '."' in out
    assert out.endswith("…")
