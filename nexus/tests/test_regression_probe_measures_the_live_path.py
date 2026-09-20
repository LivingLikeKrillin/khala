"""회귀 평가 하니스가 **라이브 요청이 지나는 경로**를 측정한다.

⛔ **왜 생겼나.** 이 리포는 평가 하니스가 **아무도 안 지나는 경로**를 측정한 사고를 두 번 겪었다
(2026-08-29 근거 조립 · 2026-08-31 테넌트 하나). 두 번 다 숫자는 나왔고, 그 숫자는 제품에
대한 것이 아니었다.

`identifier_channel_regression_probe` 는 사전 등록 §4 부 변수 1 을 측정한다. 그 판정이 서려면
두 실험군의 차이가 **`_search_channels` 의 인자 하나뿐**이어야 한다. 여기서 채널을 손으로
조립하면 T2 는 제품의 T2 가 아니고, 그 숫자로 「기각 아님」을 적는 것은 아무 말도 아니다.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

from scripts import identifier_channel_regression_probe as probe

SOURCE = Path(probe.__file__).read_text(encoding="utf-8")


def test_both_arms_go_through_the_live_seam():
    """⛔ **금지 단언은 호출을 겨눈다** — 부분 문자열로 막으면 제 머리말을 문다."""
    tree = ast.parse(SOURCE)
    calls = [n for n in ast.walk(tree)
             if isinstance(n, ast.Call) and getattr(n.func, "id", "") == "_search_channels"]
    assert calls, "라이브 이음매를 안 지난다 — 채널을 어딘가에서 손으로 조립하고 있다"
    hand_built = [n for n in ast.walk(tree)
                  if isinstance(n, ast.Call) and getattr(n.func, "id", "") == "QueryChannel"]
    assert not hand_built, "채널을 직접 만든다 — 제품이 만드는 것과 갈릴 수 있다"


def test_the_arms_differ_in_exactly_one_argument():
    """실험군 둘이 `(이름, identifiers)` 쌍으로만 갈린다 (§3 「값 하나만 움직인다」)."""
    assert '(("T0", False), ("T2", True))' in SOURCE, \
        "실험군 정의가 바뀌었다 — 무엇이 달라졌는지 여기서 보이게 하라"


def test_it_never_picks_a_corpus_by_default():
    """⛔ **말없이 고른 기본값이 2026-09-05 사고의 재료였다.**

    선언(`corpus.tenant`)이 없는 라벨 파일은 이 실행의 대상이 아니다.
    """
    src = inspect.getsource(probe.label_files)
    assert "corpus" in src and "tenant" in src
    assert "SCOPE" in src, "범위를 안 보고 파일을 고른다"
    assert probe.SCOPE == {"default", "design_docs"}, \
        "회귀가 보이는 코퍼스가 바뀌었다면 사전 등록 §4 도 같이 고쳐야 한다"


def test_the_negative_control_is_two_separate_facts():
    """⭐ **발화했는가**와 **요청했는가**를 따로 적는다 (§5.5).

    한 값으로 뭉치면 「처치가 무해했다」와 「스위치가 조용히 무시됐다」가 구별되지 않는다.
    """
    assert '"fired"' in SOURCE and '"asked"' in SOURCE, \
        "음성 대조군이 한 칸으로 뭉쳤다 — 이 실행은 §5.5 를 못 채운다"
