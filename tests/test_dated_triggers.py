"""달력 트리거 검사에 이빨이 있는가 — **일부러 그날로 옮겨서 확인한다.**

⛔ 이 검사기는 **오늘 초록인 것이 아무것도 증명하지 않는** 모양이다. 미래 날짜 하나만 들고
있으므로, 판정 논리가 통째로 망가져도 그날이 오기 전까지는 초록이다. 그래서 `--today` 가
있고, 그 인자로 그날을 가정해 붉어지는 것을 확인한다.
"""

from __future__ import annotations

import datetime as dt
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from check_dated_triggers import declared, fired, trigger_cell, unanchored  # noqa: E402

_SEC4 = """## 5. 달력에 걸린 트리거 (1)

- `SPEC-nexus-sufficiency-signal` — 2026-11-10 — 소비자 게이트를 선언한다

## 6. 다음

- `SPEC-nexus-other` — 2026-01-01 — 여기는 다음 절이다
"""

_ITEMS = """## 5. 달력에 걸린 트리거 (1)

- `H10` — 2026-11-10 — 그날의 평가일

## 6. 다음

| H10 | 무엇이었나 | 2026-11-10 |
"""


def test_it_reads_the_declaration():
    got = declared(_SEC4)
    assert got == [("SPEC-nexus-sufficiency-signal", dt.date(2026, 11, 10),
                    "소비자 게이트를 선언한다")]


def test_an_item_number_is_a_source_too():
    """§1·§2 의 트리거 칸에도 날짜가 있다(H3 · H10). 아무것도 그것을 안 보고 있었다."""
    assert declared(_ITEMS)[0][0] == "H10"
    assert unanchored(_ITEMS) == []


def test_an_item_declaration_must_match_that_item_s_trigger_cell():
    """선언한 날짜가 그 항목의 트리거 칸에 없으면 판정하지 않는다."""
    assert unanchored(_ITEMS.replace("- `H10` — 2026-11-10", "- `H10` — 2027-02-02"))


def test_the_trigger_cell_is_the_last_column():
    assert trigger_cell(_ITEMS, "H10").strip() == "2026-11-10"


def test_it_stops_at_the_next_section():
    """다음 절의 줄을 선언으로 읽으면 다른 절의 날짜가 조용히 트리거가 된다."""
    assert all(spec != "SPEC-nexus-other" for spec, _, _ in declared(_SEC4))


def test_the_day_before_is_not_the_day():
    assert fired(_SEC4, dt.date(2026, 11, 9)) == []


def test_the_day_itself_fires():
    assert len(fired(_SEC4, dt.date(2026, 11, 10))) == 1


def test_a_later_day_still_fires():
    """한 번 지나간 트리거는 계속 울려야 한다 — 하루짜리 빨간불은 놓치라고 있는 것이다."""
    assert len(fired(_SEC4, dt.date(2027, 3, 1))) == 1


def test_a_declaration_the_spec_does_not_carry_is_refused():
    """⛔ 선언과 본문이 갈리면 남은 것은 사본 하나다. 그것을 근거로 초록을 내면
    이 검사기가 막으려는 것을 스스로 한다."""
    bad = _SEC4.replace("2026-11-10", "2027-01-01")
    assert unanchored(bad), "SPEC 에 없는 날짜인데 통과시켰다"


def test_the_real_declaration_is_anchored_in_its_source():
    """정본. 선언한 날짜는 그 SPEC 미해결 절이나 그 항목의 트리거 칸에 실제로 있어야 한다."""
    assert unanchored((ROOT / "OPEN.md").read_text(encoding="utf-8")) == []


def test_the_real_file_declares_every_line_in_that_section():
    """⛔ 서식이 좁아지면 선언이 **조용히 줄고 검사기는 초록이다** — 안 읽은 줄은 안 울린다.
    §5 의 목록 줄 수와 읽어낸 선언 수가 같아야 한다."""
    text = (ROOT / "OPEN.md").read_text(encoding="utf-8")
    lines = text.splitlines()
    i = next(n for n, ln in enumerate(lines) if ln.startswith("## 5. 달력에 걸린 트리거"))
    j = next(n for n, ln in enumerate(lines) if n > i and ln.startswith("## "))
    bullets = [ln for ln in lines[i:j] if ln.startswith("- `")]
    assert bullets, "§5 에 선언 줄이 없다 — 절 제목이 바뀌었는가"
    assert len(declared(text)) == len(bullets)


def test_the_script_exits_zero_today_and_nonzero_on_the_day():
    """대조군 둘. 초록만 확인하면 **늘 초록인 검사기**와 구별되지 않는다."""
    ok = subprocess.run([sys.executable, "scripts/check_dated_triggers.py"],
                        cwd=str(ROOT), capture_output=True)
    assert ok.returncode == 0, ok.stdout.decode("utf-8", "replace")
    then = subprocess.run(
        [sys.executable, "scripts/check_dated_triggers.py", "--today", "2026-11-10"],
        cwd=str(ROOT), capture_output=True)
    assert then.returncode == 1, then.stdout.decode("utf-8", "replace")
