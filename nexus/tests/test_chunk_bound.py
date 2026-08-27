"""청크 길이에 상한이 있는가.

`KOREAN_SEARCH_QUALITY.md` §3.2 가 남긴 마지막 조각: **아무것도 청크 길이를 막지 않는다.**
`_split_text_with_overlap` 에 "단일 문단이 target 보다 크면 그 자체로 청크" 라는 경로가 있어서,
빈 줄이 없는 문단 하나가 얼마든지 커질 수 있었다.

2026-08-07 에 실물에서 터졌다 — 정책 표가 18,751자 청크가 되고 임베딩 사이드카가
`413 max_seq_length(8192)` 로 거부해서, 그 청크는 벡터 다리에서 영구히 사라졌다.

여기서 측정하는 것은 "쪼개진다" 가 아니라 **"어떤 입력에도 상한을 넘지 않는다"** 이다. 병적인 입력이
하나라도 빠져나가면 상한은 상한이 아니다.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from nexus.ingest.chunker import (  # noqa: E402
    _estimate_tokens,
    _split_oversize,
    _split_text_with_overlap,
)

TARGET = 100


def _tokens(s: str) -> int:
    return _estimate_tokens(s, "ko")


def _pathological(name: str) -> str:
    """병적인 문단을 **본문에서** 만든다 — parametrize 인자로 넘기면 pytest 가 그 거대 문자열로
    테스트 id 를 만들다 깨진다(실제로 깨졌다)."""
    if name == "table":
        return "| a | b |\n|---|---|\n" + "\n".join(
            f"| 행{i} 값 | 설명 {i} |" for i in range(400))
    if name == "codeblock":
        return "```python\n" + "\n".join(f"x{i} = compute({i})" for i in range(400)) + "\n```"
    if name == "prose":
        return "\n".join(f"문장 {i} 은 어떤 정책을 설명한다." for i in range(400))
    raise AssertionError(name)


@pytest.mark.parametrize("name", ["table", "codeblock", "prose"])
def test_no_piece_exceeds_the_target_however_pathological(name):
    para = _pathological(name)
    assert _tokens(para) > TARGET, "입력이 상한을 안 넘으면 이 검사는 아무것도 안 본다"
    for piece in _split_oversize(para, TARGET, "ko"):
        assert _tokens(piece) <= TARGET, f"{name}: 조각이 {_tokens(piece)} 토큰 (상한 {TARGET})"


def test_the_whole_path_is_bounded_not_just_the_helper():
    """헬퍼만 고치고 호출부가 옛 경로를 그대로 타면 아무것도 안 고쳐진 것이다."""
    for chunk in _split_text_with_overlap(_pathological("table"), TARGET, 10, "ko"):
        assert _tokens(chunk) <= TARGET, f"{_tokens(chunk)} 토큰이 통과했다"


def test_a_table_keeps_its_header_on_every_piece():
    """표를 그냥 자르면 두 번째 조각부터 열의 뜻이 사라진다. 실제로 터진 것이 정책 표였다."""
    pieces = _split_oversize(_pathological("table"), TARGET, "ko")
    assert len(pieces) > 1, "쪼개지지 않으면 이 검사는 아무것도 안 본다"
    for p in pieces:
        assert p.startswith("| a | b |\n|---|---|"), "헤더 없는 조각이 나왔다"


def test_nothing_is_lost_when_a_table_is_split():
    """상한을 지키느라 행이 사라지면 그건 고친 게 아니라 지운 것이다."""
    para = _pathological("table")
    rows = [ln for ln in para.split("\n") if ln.startswith("| 행")]
    joined = "\n".join(_split_oversize(para, TARGET, "ko"))
    missing = [r for r in rows if r not in joined]
    assert not missing, f"행 {len(missing)}개가 사라졌다: {missing[:3]}"


def test_a_paragraph_that_already_fits_is_left_alone():
    """상한 아래인 것까지 건드리면 기존 청킹이 통째로 바뀐다."""
    para = "짧은 문단이다."
    assert _split_oversize(para, TARGET, "ko") == [para]


def test_splitting_prefers_line_boundaries():
    """줄 중간을 자르는 것은 최후 수단이다 — 표 행이나 코드 문장이 깨진다."""
    lines = [f"줄 {i} 내용" for i in range(60)]
    pieces = _split_oversize("\n".join(lines), TARGET, "ko")
    assert len(pieces) > 1
    for p in pieces:
        for ln in p.split("\n"):
            assert ln in lines, f"줄이 잘렸다: {ln!r}"


def test_the_bound_is_in_estimator_tokens_and_the_estimator_is_blind_to_spaceless_text():
    """**남은 구멍을 숨기지 않고 드러낸다.**

    `_estimate_tokens` 는 공백 기준 단어 수 × 계수다. 공백이 없는 2만자 줄을 **2토큰**으로 센다.
    그래서 이 상한은 *추정기 토큰* 의 상한이지 **임베딩 모델 토큰의 상한이 아니다.**

    이 검사가 실패하면 추정기가 바뀐 것이고, 그러면 상한의 의미도 바뀐 것이라 §3.2 의 기록과
    `chunk-bound-is-estimator-tokens` 항목을 다시 읽어야 한다. 통과한다고 안전한 것이 아니라,
    **무엇이 안전하지 않은지가 여기 적혀 있다는 뜻**이다.
    """
    spaceless = "가" * 20000
    assert _tokens(spaceless) <= TARGET, "추정기가 바뀌었다 — 상한의 의미를 다시 보라"
    assert _split_oversize(spaceless, TARGET, "ko") == [spaceless], \
        "추정기가 크다고 안 보므로 쪼개지지 않는다. 이것이 남은 구멍이다."
