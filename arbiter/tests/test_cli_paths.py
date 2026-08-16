"""ARBITER_ROOT/ARBITER_DOCS 경로 해석 (Git Bash 함정).

Git Bash 는 `$PWD` 를 `/c/Users/...` 로 준다. Windows 의 Python 은 그걸 풀지 못하고,
증상은 "아티팩트를 찾을 수 없음" — 원인과 전혀 닮지 않은 오류다. 이 프로젝트는 이 함정으로
이미 라운드를 날렸고, 그 뒤 같은 형태의 명령을 두 번 더 안내했다. 그래서 도구가 막는다.
"""

from __future__ import annotations

import os

import pytest

from khala.arbiter.cli import _resolve_dir


@pytest.mark.skipif(os.name != "nt", reason="MSYS 경로 변환은 Windows 에서만 의미가 있다")
def test_msys_style_path_is_converted_when_the_windows_form_exists(tmp_path):
    drive, rest = str(tmp_path).split(":", 1)
    msys = f"/{drive.lower()}{rest.replace(chr(92), '/')}"

    assert _resolve_dir(msys) == tmp_path


def test_an_ordinary_existing_path_is_returned_unchanged(tmp_path):
    assert _resolve_dir(str(tmp_path)) == tmp_path


def test_a_path_that_is_not_msys_shaped_is_left_alone():
    assert str(_resolve_dir("relative/dir")).endswith("relative" + os.sep + "dir")
