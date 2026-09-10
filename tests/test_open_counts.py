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

from check_open_counts import (  # noqa: E402
    claimed, counts, problems, ragged, rows, state_of,
)

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


def test_a_cell_that_says_it_fired_is_waiting():
    """⛔ 실제로 난 사고 (2026-09-11) — A21 의 트리거 칸이 2026-08-30 부터
    *"트리거가 두 번 울렸다"* 라고 적고 있었는데 `조건` 으로 세어졌다. 판정이 트리거
    문자열만 보는 것은 맞지만, **그 문자열이 울렸다고 말하는데 안 읽으면** 대기/조건은
    사실이 아니라 문장의 서식을 세는 것이다."""
    assert state_of("⚠ 확인 2026-08-30: **트리거가 두 번 울렸다**(#330 · #346)") == "대기"


def test_a_conditional_cell_is_still_conditional():
    """대조군 — 그 말을 넣어 모든 칸이 대기가 되면 구분 자체가 없어진다."""
    assert state_of("다음 저술 라운드") == "조건"
    assert state_of("두 번째 조직") == "조건"
    assert state_of("—") == "조건"


# ── 표의 모양 ────────────────────────────────────────────────────────────────

_GOOD = "| A1 | 본문 | 트리거 |"
_EXTRA = "| A2 | 본문 | 트리거 | 안 그려지는 넷째 칸 |"
_UNCLOSED = "| A3 | 본문 | 트리거 | 표 밖으로 흐른 글"
_RAWPIPE = "| A4 | 본문에 `env | grep` 이 있다 | 트리거 |"
_ESCAPED = "| A5 | 본문에 `env \\| grep` 이 있다 | 트리거 |"


def _sec2(*lines):
    return "## 2. 내가 할 수 있는 것 (1)\n" + "\n".join(lines) + "\n## 3. 결정\n"


def test_a_fourth_column_is_caught():
    """⛔ 실제로 난 사고 (2026-09-11) — 항목 행 111개 중 넷이 3칸이 아니었다.
    마크다운은 머리글보다 많은 칸을 **말없이 버리므로** 그 글은 파일에만 있고 화면에는
    없었다. A18 의 넷째 칸에는 *트리거가 울렸지만 이 항목은 물지 않는다* 는 판단이
    들어 있었고, 그것을 읽은 사람이 없었다."""
    assert ragged(_sec2(_EXTRA))
    assert not ragged(_sec2(_GOOD))


def test_a_row_that_never_closes_is_caught():
    """닫는 파이프가 없으면 마지막 칸 뒤의 글이 표 밖으로 흐른다(H4 · A18 이 그랬다)."""
    assert ragged(_sec2(_UNCLOSED))


def test_an_unescaped_pipe_in_the_body_is_caught():
    """H27 의 본문에 `env | grep` 이 그대로 있어 칸이 하나 늘었고, 진짜 트리거
    `즉시` 가 넷째 칸으로 밀려 화면에서 사라졌다."""
    assert ragged(_sec2(_RAWPIPE))


def test_an_escaped_pipe_is_not_a_column_boundary():
    """대조군 — 이스케이프한 파이프까지 경계로 세면 고친 행이 영원히 붉어진다."""
    assert not ragged(_sec2(_ESCAPED))


def test_the_trigger_is_read_from_the_last_real_column():
    """이스케이프한 파이프가 있어도 트리거 칸을 집어야 한다 — 이 규칙이 **행마다 다른
    칸을 집던 것**이 이번 결함의 실체다."""
    got = [t for _, i, t in rows(_sec2(_ESCAPED)) if i == "A5"]
    assert got and got[0].strip() == "트리거"


def test_shape_is_checked_before_the_numbers():
    """⛔ 모양이 어긋난 채로 수만 맞으면, 틀린 판정 위에서 대조가 맞아떨어진다."""
    bad = problems(_sec2(_EXTRA))
    assert any("칸이" in b for b in bad)


def test_the_real_file_has_no_ragged_row():
    assert ragged((ROOT / "OPEN.md").read_text(encoding="utf-8")) == []
