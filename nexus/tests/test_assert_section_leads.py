"""2판의 주장 자리에 **절 머리**를 더한 개정 (사전 등록 2026-08-31).

⛔ **개정은 점수를 보고 쓴 것이 아니다.** 드리프트를 아침에 `A28` 로 등록했고, 규칙이 컷오버를
막은 뒤 **등록 문단을 먼저 커밋하고** 구현했다. `tests/eval/answer-facts/README.md` 참조.

여기서 지키는 것은 개정이 **무엇을 느슨하게 하지 않았는가**다 — 표 행과 인용문은 여전히
주장이 아니다. 그것까지 열면 `늘어놓기는 주장이 아니다` 가 무너지고, 2판은 1판이 된다.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "koq", Path(__file__).resolve().parents[1] / "scripts" / "ko_eval_answer_quality.py")
koq = importlib.util.module_from_spec(_spec)
# `@dataclass` 가 `sys.modules[cls.__module__]` 를 찾는다 — 등록 안 하면 None 이라 터진다.
sys.modules["koq"] = koq
_spec.loader.exec_module(koq)

CONFLICT_ANSWER = """**문서와 코드가 서로 다른 값을 말합니다. 둘 다 적겠습니다.**

---

**문서 기준: 최대 50자**

공지 등록 팝업 정책에 명시돼 있습니다.

---

**코드 기준: 최대 255자**
"""


def test_the_shape_that_wobbled_now_passes():
    """⛔ 기준선 5회에서 라벨 다섯이 이 모양 때문에 회차마다 갈렸다."""
    assert koq.asserts_value(["50자"], CONFLICT_ANSWER) is True


def test_the_old_shape_still_passes():
    """대조군 — 값이 선두에 있는 답변은 그대로 통과해야 한다."""
    assert koq.asserts_value(["30자"], "**핵심 답변: 30자**입니다.\n\n---\n\n근거는 아래와 같습니다.")


def test_a_value_only_in_a_table_row_still_fails():
    """⛔ **가장 중요한 대조군.** 표에만 있으면 늘어놓기다 — 여기까지 열면 2판이 1판이 된다."""
    answer = "값을 정리하면 다음과 같습니다.\n\n| 항목 | 값 |\n|---|---|\n| 제한 | 77자 |\n"
    assert koq.asserts_value(["77자"], answer) is False


def test_a_value_only_in_a_quote_still_fails():
    """인용은 근거이지 주장이 아니다."""
    answer = "정책을 확인했습니다.\n\n---\n\n> 원문: 한글 88자 제한\n"
    assert koq.asserts_value(["88자"], answer) is False


def test_a_value_nowhere_near_a_section_lead_still_fails():
    answer = "질문에 답하기 어렵습니다.\n\n---\n\n참고로 근거가 부족합니다.\n"
    assert koq.asserts_value(["99자"], answer) is False


def test_section_leads_take_the_first_prose_after_each_break_only():
    """절의 **머리**만 본다 — 절 전체를 열면 표·인용을 뺀 의미가 없어진다."""
    got = koq.section_lead_segments(CONFLICT_ANSWER)
    joined = " ".join(got)
    assert "문서 기준: 최대 50자" in joined
    assert "코드 기준: 최대 255자" in joined
    assert "공지 등록 팝업 정책에 명시돼" not in joined
