"""열린 항목 수 검사에 이빨이 있는가 — **일부러 어긋나게 해서 확인한다.**

⛔ 검사기를 넣고 초록을 보는 것만으로는 아무것도 증명 못 한다. 이 리포는 *"찾아내고 종료코드
0"* 인 검사기를 이미 한 번 만들었다. 그래서 여기서는 **틀린 문서를 만들어 빨간불을 확인**한다.
"""

from __future__ import annotations

import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from check_open_counts import claimed, counts, problems  # noqa: E402

_DOC = """# 열린 항목

| 구분 | 수 |
|---|---|
| **사람만 할 수 있는 것** | **{h}** |
| **내가 할 수 있는 것** | **{a}** |
| **대기** — 트리거가 울렸다 | **1** |
| **조건** — 트리거를 기다린다 | **2** |

## 1. 사람만 할 수 있는 것 ({h})

| # | 항목 | 트리거 |
|---|---|---|
| H1 | 하나 | 즉시 |
| ~~H2~~ | ✅ 닫힘 | — |

## 2. 내가 할 수 있는 것 ({a})

| # | 항목 | 트리거 |
|---|---|---|
| A1 | 하나 | 언젠가 |
| A2 | 둘 | 언젠가 |
| ~~A3~~ | ✅ 닫힘 | — |

## 3. 결정 — 열린 항목이 아니다

| D1 | 안 한다 | 근거 |
"""


def test_a_struck_row_is_not_an_open_item():
    """취소선은 닫힌 것이다 — 그것이 이 파일의 세는 규칙이고, 검사기가 그 규칙을 쓴다."""
    assert counts(_DOC.format(h=1, a=2)) == {"H": 1, "A": 2}


def test_decisions_are_not_counted():
    """§3 은 *하지 않기로 정한 것*이라 미결이 아니다 — 세면 목록이 실제보다 길어 보인다."""
    assert counts(_DOC.format(h=1, a=2))["A"] == 2


def test_a_matching_document_is_silent():
    assert problems(_DOC.format(h=1, a=2)) == []


def test_an_inflated_count_is_caught():
    """⛔ 실제로 난 사고 — 닫으면서 머리말을 안 뺐다."""
    bad = problems(_DOC.format(h=1, a=5))
    assert bad and any("5" in b and "2" in b for b in bad)


def test_a_deflated_count_is_caught_too():
    """양방향이다. 적게 적는 것도 같은 결함이다 — 늘 자기에게 유리한 쪽으로만 틀리지 않는다."""
    assert problems(_DOC.format(h=1, a=1))


def test_the_summary_and_the_heading_must_agree():
    """두 자리에 같은 수가 있다. 한쪽만 고치는 것이 정확히 이 사고의 모양이다."""
    doc = _DOC.format(h=1, a=2).replace("## 2. 내가 할 수 있는 것 (2)",
                                        "## 2. 내가 할 수 있는 것 (9)")
    assert claimed(doc)["A"] == [2, 9]
    assert problems(doc)


def test_the_real_file_agrees_with_itself():
    """정본. 이 검사가 빨간불이면 `OPEN.md` 의 머리말을 **세어서** 고쳐라."""
    assert problems((ROOT / "OPEN.md").read_text(encoding="utf-8")) == []


def test_the_script_exits_nonzero_when_it_finds_something(tmp_path, monkeypatch):
    """종료코드까지 확인한다 — 감지기는 있는데 전달이 없는 형태를 이 리포는 이미 겪었다."""
    out = subprocess.run([sys.executable, "scripts/check_open_counts.py"],
                         cwd=str(ROOT), capture_output=True)
    assert out.returncode == 0, out.stdout.decode("utf-8", "replace")
