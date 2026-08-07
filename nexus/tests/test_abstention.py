"""기권 — 코드가 내리는 판단인가, 문장에서 읽어낸 것인가.

`KOREAN_SEARCH_QUALITY.md` §2.3 은 답변불가 라벨 5건이 "어떤 집계에도 안 들어간다" 고 적고
이유를 "Nexus 에 기권 기제가 없어 잴 것이 없다" 로 남겼다. 기제는 사실 **있었다** — 근거가 하나도
없으면 LLM 을 부르지 않고 정해진 문장을 돌려준다. 없던 것은 **기계가 읽을 수 있는 형태**였다.

여기서 재는 두 가지:

1. 기권이 `abstained` 로 나온다 — 답변 문장을 한국어로 대조하지 않고.
2. **문장이 바뀌어도 플래그가 산다.** 문자열에 기대는 순간 그 문구를 다듬는 커밋 하나가 조용히
   측정을 껐다 켠다.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from nexus.llm.answer import AnswerResult, generate_answer  # noqa: E402
from scripts.ko_eval_harness import score_abstention  # noqa: E402


class _Packet:
    """근거가 없는 패킷 — 기권 경로를 타는 유일한 조건."""

    def __init__(self, snippets):
        self.snippets = snippets
        self.graph = None
        self.provenance = []
        self.route_used = "keyword"


def _answer(packet):
    return asyncio.run(generate_answer("아무 질의", packet, llm_svc=None))


def test_no_evidence_abstains_and_says_why():
    r = _answer(_Packet([]))
    assert r.abstained is True
    assert r.abstain_reason == "no_evidence"


def test_the_flag_does_not_depend_on_the_wording():
    """문구를 바꿔도 플래그가 서 있어야 한다.

    문자열 대조로 기권을 읽으면, 그 문장을 다듬는 커밋 하나가 측정을 조용히 끈다. 그래서
    **플래그를 먼저 세우고 문장은 그 다음**이다.
    """
    r = _answer(_Packet([]))
    original = r.answer
    r.answer = "말을 완전히 다르게 바꿔 놓아도"
    assert r.abstained is True, "기권이 문장에 실려 있다면 여기서 무너진다"
    assert original != r.answer


def test_a_fresh_result_does_not_claim_abstention():
    """기본값이 True 면 아무것도 안 한 답변까지 기권으로 세어져 비율이 부풀려진다."""
    r = AnswerResult()
    assert r.abstained is False and r.abstain_reason == ""


def test_the_unanswerable_labels_are_counted_apart_from_the_forty():
    """§4.3 의 분모는 답변가능 40 이고 그건 그대로다. 답변불가는 다른 것을 잰다."""
    unanswerable = [{"id": "u1"}, {"id": "u2"}, {"id": "u3"}, {"id": "u4"}, {"id": "u5"}]
    r = score_abstention({"u1": True, "u3": True}, unanswerable)
    assert (r.total, r.abstained) == (5, 2)
    assert r.answered == ["u2", "u4", "u5"], "기권했어야 하는데 답한 것이 이름으로 남아야 한다"
    assert abs(r.rate - 0.4) < 1e-9


def test_answering_everything_scores_zero_rather_than_erroring():
    """0 은 이 채점기의 실패가 아니라 **측정된 사실**이다 — 그 숫자가 있어야 고칠지를 정한다."""
    unanswerable = [{"id": "u1"}, {"id": "u2"}]
    r = score_abstention({}, unanswerable)
    assert r.abstained == 0 and r.rate == 0.0 and len(r.answered) == 2
