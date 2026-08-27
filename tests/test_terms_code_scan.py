"""코드 안의 용어를 쓸어낼 때 **무엇을 건드리면 안 되는가**.

이 도구는 용어집이 늘어날 때 다시 돌아간다. 그때 위험한 것은 못 고치는 게 아니라
**고치면 안 되는 것을 고치는 것**이다:

  · 평가 라벨·질문은 측정의 입력이고 서명·매니페스트에 묶여 있다
  · 철회 원장은 승인 도장이 걸려 있다
  · 사전과 검사기는 금지어를 **이름으로** 들고 있어야 한다

그리고 산문(주석·docstring)과 **기능하는 문자열**은 성질이 다르다. 프롬프트 본문이나
테스트 기댓값을 같은 손으로 바꾸면 동작이 조용히 바뀐다.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import _terms_code_scan as scan  # noqa: E402


def test_evaluation_labels_and_signed_ledgers_are_frozen():
    """⛔ 여기가 뚫리면 라벨이 조용히 바뀌고, 그 뒤 모든 수치가 못 쓰게 된다."""
    for path in (
        "nexus/tests/eval/ko/answer-labels.yaml",
        "nexus/tests/eval/local/policy-labels.yaml",
        "nexus/tests/eval/ko/multiturn-threads.yaml",
        "specs/retractions.yaml",
    ):
        assert scan.frozen(path), path


def test_the_dictionary_and_the_checker_are_frozen():
    """금지어를 이름으로 들고 있어야 하는 파일들이다 — 쓸어내면 스스로를 지운다."""
    for path in ("scripts/check_terms.py", "tests/test_check_terms.py"):
        assert scan.frozen(path), path


def test_ordinary_source_is_not_frozen():
    """대조군 — 전부 동결이면 이 도구는 아무것도 안 하고 통과한다."""
    for path in ("nexus/scripts/ko_eval_ann.py", "nexus/nexus/search/hybrid.py"):
        assert not scan.frozen(path), path


def test_comments_and_docstrings_are_prose_but_other_strings_are_not():
    """산문만 고쳐야 한다. 프롬프트 본문·테스트 기댓값을 같이 바꾸면 **동작이 바뀐다.**"""
    src = '\n'.join([
        '"""모듈 설명."""',              # 1  docstring
        '',                              # 2
        'PROMPT = "이 문장은 기능한다"',   # 3  기능하는 문자열
        '',                              # 4
        'def f():',                      # 5
        '    """함수 설명."""',           # 6  docstring
        '    # 주석',                     # 7  주석
        '    return "값"',               # 8  기능하는 문자열
    ])
    prose = scan.prose_lines(src)
    assert 1 in prose and 6 in prose and 7 in prose
    assert 3 not in prose and 8 not in prose


def test_a_file_it_cannot_parse_does_not_become_all_prose():
    """파싱이 깨졌을 때 **전부 산문**으로 취급하면 기능하는 문자열까지 고친다.
    깨지면 아무것도 산문이 아니어야 안전하다."""
    assert scan.prose_lines("def broken(:\n  '문자열'\n") == set()
