"""근거 충분성 판정자 — 순수 부분에 이가 있는가.

이 판정자가 존재하는 이유는 검색 점수로 문턱을 못 세웠기 때문이다(2026-08-09 실측: 선언한
질의와 답한 질의의 `top`/`mean`/`gap` 분포가 완전히 겹쳤고, `top` 은 오히려 선언 쪽 최소값이
더 높았다). 그러니 이 판정이 틀리면 대안이 없다.

여기서 재는 것은 대부분 **읽으면 안 되는 입력**이다.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from nexus.llm.sufficiency import (  # noqa: E402
    SYSTEM,
    Sufficiency,
    build_prompt,
    judge,
    parse,
)


def test_a_clean_verdict_is_read():
    v = parse("VERDICT: sufficient\nREASON: 표에 그 값이 그대로 있다")
    assert v.label is Sufficiency.SUFFICIENT and v.is_sufficient
    assert v.reason == "표에 그 값이 그대로 있다"


def test_insufficient_is_read_and_is_not_sufficient():
    v = parse("VERDICT: insufficient\nREASON: 근거에 수치가 없다")
    assert v.label is Sufficiency.INSUFFICIENT and v.is_sufficient is False


def test_case_and_stray_whitespace_do_not_break_it():
    assert parse("  verdict:  Sufficient  \nreason: x").label is Sufficiency.SUFFICIENT


def test_prose_is_not_guessed_at():
    """**가장 중요한 대조군.** 산문에서 '충분해 보인다' 를 읽어내려는 순간 이 판정은 문자열
    대조가 되고, 이 리포는 그 방식으로 이미 인용 검증기에서 데였다."""
    for raw in ("근거가 충분해 보입니다.", "네, 답할 수 있습니다", "sufficient", ""):
        assert parse(raw).label is Sufficiency.UNPARSEABLE, raw


def test_unparseable_is_not_sufficient():
    """판정자가 고장 난 순간부터 모든 질의가 조용히 통과하면 안 된다."""
    assert parse("무슨 소리인지 모를 출력").is_sufficient is False


def test_a_verdict_buried_in_extra_prose_is_still_read():
    """형식은 지키되 앞뒤로 말을 붙이는 경우 — 판정 자체는 있다."""
    v = parse("생각해보면...\nVERDICT: insufficient\nREASON: 표가 없다\n이상입니다")
    assert v.label is Sufficiency.INSUFFICIENT


def test_the_judge_never_sees_the_answer():
    """판정자와 피판정자가 같아지면 안 된다 — 논문이 지적한 실패 구도다."""
    p = build_prompt("질의", "근거 본문")
    assert "질의" in p and "근거 본문" in p
    assert "답변" not in p.replace("## 근거", ""), "프롬프트에 답변 자리가 있으면 안 된다"


def test_the_instruction_forbids_filling_gaps_from_model_knowledge():
    """근거에 없는 것을 아는 지식으로 메우면 이 판정은 무의미해진다."""
    assert "근거에 없으면 불충분" in SYSTEM


def test_a_backend_failure_degrades_rather_than_raising():
    class _Boom:
        async def generate(self, *a, **k):
            raise RuntimeError("backend down")

    v = asyncio.run(judge("q", "e", _Boom()))
    assert v.label is Sufficiency.UNPARSEABLE and v.is_sufficient is False
