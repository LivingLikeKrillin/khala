"""README 수 검사에 이빨이 있는가 — **일부러 어긋나게 해서 확인한다.**

⛔ 이 리포는 *"찾아내고 종료코드 0"* 인 검사기를 만든 적이 있다. 초록을 보는 것만으로는
아무것도 증명하지 못한다.
"""

from __future__ import annotations

import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from check_readme_counts import claimed, counts, problems  # noqa: E402

_DOC = ("2,585 test functions and 17 CI jobs, ... Governance artifacts "
        "(10 ADRs, 52 SPECs) are stamped ...")


def test_it_reads_all_four_numbers():
    got = claimed(_DOC)
    assert got == {"tests": 2585, "ci_jobs": 17, "adrs": 10, "specs": 52}


def test_a_thousands_separator_is_not_a_different_number():
    """`2,585` 와 `2585` 는 같은 수다 — 쉼표 때문에 검사가 헛돌면 곧 꺼진다."""
    assert claimed("1,900 test functions")["tests"] == 1900


def test_a_drifted_number_is_caught():
    """⛔ 실제로 난 사고 — README 가 1,900 이라 적고 실제는 2,585 였다."""
    bad = problems(_DOC.replace("2,585", "1,900"))
    assert bad and any("tests" in b for b in bad)


def test_a_changed_sentence_is_caught_too():
    """문장을 고치면서 수를 지우면 **검사가 조용해지는 것**이 아니라 빨간불이 돼야 한다."""
    bad = problems("이 문서에는 수가 없다")
    assert len(bad) == 4


def test_the_real_readme_agrees_with_itself():
    """정본. 빨간불이면 README 를 **세어서** 고쳐라."""
    assert problems((ROOT / "README.md").read_text(encoding="utf-8")) == []


def test_the_counter_actually_counts_something():
    """대조군 — 전부 0을 세는 계수기는 어떤 README 와도 안 맞거나 다 맞는다."""
    real = counts()
    assert real["tests"] > 100 and real["adrs"] >= 1 and real["specs"] >= 1


def test_the_script_exits_zero_when_it_agrees():
    out = subprocess.run([sys.executable, "scripts/check_readme_counts.py"],
                         cwd=str(ROOT), capture_output=True)
    assert out.returncode == 0, out.stdout.decode("utf-8", "replace")
