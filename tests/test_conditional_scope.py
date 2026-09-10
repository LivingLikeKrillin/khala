"""§4 의 집합 검사에 이빨이 있는가 — **일부러 어긋나게 해서 확인한다.**

⛔ 이 리포는 *"찾아내고 종료코드 0"* 인 검사기를 만든 적이 있다. 초록을 보는 것만으로는
아무것도 증명하지 못한다. 그리고 이 검사기는 **빈 집합을 초록으로 읽을 위험**이 특히 큰
모양이다 — 제목 서식이 셋이라 정규식 하나가 틀리면 *"처분 안 된 SPEC 이 없다"* 가 나온다.
"""

from __future__ import annotations

import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from check_conditional_scope import (  # noqa: E402
    accounted, problems, specs_with_open_sections,
)

_SEC4 = """## 4. 조건부 잔여 (2)

| SPEC | 건 | 남은 것의 성격 |
|---|---|---|
| alpha | 1 | 어떤 것 |

- `SPEC-nexus-beta` — §3 결정

## 5. 다음
"""


def test_it_reads_the_table_and_the_declaration():
    assert accounted(_SEC4) == {
        "SPEC-nexus-alpha.md": "§4 표",
        "SPEC-nexus-beta.md": "§3 결정",
    }


def test_it_stops_at_the_next_section():
    """§5 로 넘어간 뒤의 목록을 §4 의 선언으로 읽으면, 다른 절에 적힌 SPEC 이름이
    조용히 처분으로 세어진다."""
    spill = _SEC4 + "\n- `SPEC-nexus-gamma` — 여기는 §5 다\n"
    assert "SPEC-nexus-gamma.md" not in accounted(spill)


def test_an_unaccounted_spec_is_caught():
    """⛔ 실제로 난 사고 — `embedding-provenance-grain` 의 미해결 셋 중 하나가
    §1·§2·§3·§4 어디에도 없었다(2026-09-10)."""
    bad = problems(_SEC4, {"SPEC-nexus-alpha.md", "SPEC-nexus-beta.md", "SPEC-nexus-gamma.md"})
    assert len(bad) == 1 and "gamma" in bad[0]


def test_a_declaration_for_a_spec_that_does_not_exist_is_caught_too():
    """지운 SPEC 을 선언에 남겨 두면 목록이 실제보다 커 보이고, 그 방향으로는
    영원히 붉어지지 않는다."""
    bad = problems(_SEC4, {"SPEC-nexus-alpha.md"})
    assert len(bad) == 1 and "beta" in bad[0]


def test_the_finder_actually_finds_something():
    """대조군 — 빈 집합을 세는 계수기는 어떤 OPEN.md 와도 다 맞는다."""
    assert len(specs_with_open_sections()) > 5


def test_all_three_heading_forms_are_found():
    """서식이 셋이다(`Open items` · `Open questions` · `미해결`). 하나라도 빠지면
    그 서식을 쓰는 SPEC 전부가 조용히 사라진다."""
    found = specs_with_open_sections()
    assert "SPEC-nexus-screenshot-text-extraction.md" in found      # Open items
    assert "SPEC-nexus-a2a-server-phase0-spike.md" in found         # Open questions
    assert "SPEC-nexus-multi-turn-retrieval.md" in found            # 미해결


def test_the_real_file_agrees_with_itself():
    """정본. 빨간불이면 §4 표에 줄을 넣거나 선언 목록에 어디서 세는지 적어라."""
    assert problems(OPEN_MD_TEXT, specs_with_open_sections()) == []


OPEN_MD_TEXT = (ROOT / "OPEN.md").read_text(encoding="utf-8")


def test_the_script_exits_zero_when_it_agrees():
    out = subprocess.run([sys.executable, "scripts/check_conditional_scope.py"],
                         cwd=str(ROOT), capture_output=True)
    assert out.returncode == 0, out.stdout.decode("utf-8", "replace")
