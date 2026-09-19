"""걸린 숫자가 **무엇인지** 응답에 오는가.

⛔ **실측 2026-09-19, 설명 층 보고.** `llm/answer.py` 는 `result.numbers` 를 이미 만들고
있었는데 응답에는 `unverified_numbers`(개수)만 나갔다. 그래서 읽는 쪽은 그 수를 한동안
**「지어낸 통계」로 읽었다.** 뒤늦게 답의 숫자를 직접 뽑아 보니 거의 전부 인용의 절 번호였다
(`§15.148` · `§4.4`). 아홉 답에서 단위 붙은 수(%·초·개·kg)는 하나도 없었다.

⚠ 그 결론조차 **추정**이다 — 답 전체의 분포에서 미룬 것이지 걸린 그 숫자를 본 것이 아니다.
목록이 가면 미루지 않아도 된다. `timing_ms` 와 같은 모양이다: 값은 있었고 전달이 없었다.

⚠ **그리고 이 목록이 가면 확인할 수 있는 것이 하나 더 있다.** `numbers.py` 는 *"% 거나,
소수거나, 정수값 >=10"* 을 검사 대상으로 삼는다. `15.148` 은 소수라 **절 번호가 수치 주장으로
잡힌다.** 그것이 맞는 설계인지는 목록을 보고 사람이 정할 일이고, 여기서 바꾸지 않는다.
"""

from __future__ import annotations

import pathlib

from nexus import api
from nexus.llm.answer import AnswerResult


def _src() -> str:
    return pathlib.Path(api.__file__).read_text(encoding="utf-8")


def test_the_answer_result_already_carried_it():
    """⭐ 만드는 쪽은 처음부터 있었다 — 없던 것은 전달이다."""
    assert "numbers" in AnswerResult.__dataclass_fields__
    assert "unverified_numbers" in AnswerResult.__dataclass_fields__


def test_both_answer_surfaces_send_the_list():
    """⛔ 한 표면만 내보내면 그 표면의 소비자만 조용히 못 본다 — 이 리포가 반복해서 데인 모양이다
    (`packet_for_answer` 주석의 2026-09-02 사고가 같은 계열이다)."""
    src = _src()
    assert src.count('"numbers":') == 2, "답변 표면 둘 다에서 나가야 한다"


def test_the_count_still_goes_too():
    """개수를 목록으로 **대체**하지 않는다 — 세는 쪽 소비자가 이미 있다."""
    assert _src().count('"unverified_numbers":') == 2


def test_the_list_carries_whether_each_number_was_grounded():
    """⛔ 값만 있고 판정이 없으면 읽는 쪽이 다시 대조해야 한다 — 그러면 전달한 뜻이 없다."""
    src = _src()
    assert '"value": n.value, "grounded": n.grounded' in src


def test_the_streaming_shape_matches_the_non_streaming_one():
    """두 표면이 같은 이름·같은 모양이어야 소비자가 분기 없이 읽는다."""
    from nexus.llm import numbers as N

    assert {"value", "grounded"} <= set(N.NumberCheck.__dataclass_fields__)
