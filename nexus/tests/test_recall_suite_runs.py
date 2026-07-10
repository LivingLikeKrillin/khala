"""재현율 스위트가 조용히 스킵되지 않았는지 확인한다.

`tests/test_search_recall.py` 는 mecab-ko 가 없으면 스킵된다 — 공백 분리 fallback 은
프로덕션 토크나이저가 아니고, 다른 자로 잰 숫자는 바닥값이 아니기 때문이다.

그 스킵이 CI 에서 일어나면 스위트는 존재하지만 아무것도 지키지 않는다. 조용히 건너뛴 테스트는
없는 테스트다. BM25 다리가 몇 년간 침묵한 것도 그렇게 시작했다.

이 파일에는 skipif 가 없다. 그래서 이 단언은 언제나 돈다.
"""

from __future__ import annotations

import os

from nexus.index.bm25 import _get_mecab


def test_where_mecab_is_required_it_is_present():
    """CI 의 재현율 잡은 `NEXUS_REQUIRE_MECAB=1` 로 돈다. 거기서 mecab 이 없으면 빨간불."""
    if os.getenv("NEXUS_REQUIRE_MECAB") != "1":
        return
    assert _get_mecab() is not None, (
        "mecab-ko 가 없다 — 이 환경에서 재현율 스위트는 반드시 돌아야 한다. "
        "이미지 안에서 실행하고 있는지 확인하라."
    )
