"""답변 계약(시스템 프롬프트)이 지켜야 할 성질.

계약은 산문이라 조용히 바뀐다. 측정으로 넣은 조항은 여기서 잡아 둔다 — 지우려면
같은 방법으로 측정하고 지워야 한다.
"""

from __future__ import annotations

def test_the_contract_requires_every_part_of_a_multi_part_question():
    """**두 부분짜리 질문에 한 부분만 답하고 나머지를 조용히 버리는 실패**를 막는 조항.

    측정(2026-08-28, 근거를 양쪽 실험군에 글자 단위로 고정하고 조항만 바꿈):
      · 다중 부분 라벨 하나가 실패 → 통과 (2회 재현)
      · 단일 값 15문항 14/15 — 앞선 기준선 세 번과 동일, 실패도 같은 항목
      · 답변 평균 길이 510자 → 506자
    ⚠ 이 하니스의 잡음 폭은 라벨 ±1 이다. 그보다 작은 해는 이 측정이 못 본다.
    """
    from nexus.llm.prompts import build_system_prompt
    sys_prompt = build_system_prompt(False, False)
    assert "질문이 여러 부분이면" in sys_prompt
    assert "부분마다 답을 하나씩" in sys_prompt
    assert "이 부분은 제공된 근거에 없습니다" in sys_prompt
