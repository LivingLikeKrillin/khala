"""답변 품질 — **LLM 심판 없이** 결정론으로 채점한다.

이 리포는 검색을 엄격하게 재 왔고 **답변은 한 번도 안 쟀다.** 있는 것은 결정론적 가드 셋뿐이다
(인용 사후검증·숫자 근거검증·근거 신선도). 셋 다 답변이 근거를 **벗어났는지**를 보지, 답이
**맞는지**를 보지 않는다.

여기서 재는 세 가지. 전부 코드가 판단한다 — 답이 좋은지를 LLM 에게 물으면 그 LLM 의 취향을 재게
되고, 그 취향은 우리 라벨보다 검증이 덜 된 것이다.

| 재는 것 | 방법 | 실패가 뜻하는 것 |
|---|---|---|
| `grounded` | 인용이 하나 이상 있고 전부 근거 packet 안의 문서다 | 출처를 지어냈다 |
| `cites_gold` | 인용 중 하나가 **정답 문서**를 가리킨다 | 엉뚱한 문서로 답했다 |
| `has_facts` | 답변에 `must_contain` 의 사실이 들어 있다 | 검색은 맞았는데 답이 틀렸다 |

**인용이 0개인 답변은 grounded 가 아니다.** 미검증 인용 수만 보면 0이라 통과해 버린다 — 아무것도
인용하지 않는 것이 가장 쉬운 만점이 된다. `ADR-0002`(근거 없는 답변 금지)가 막으려던 바로 그
형태라, 여기서 명시적으로 막는다.

`must_contain` 의 모양: **모든 항목**이 만족돼야 하고, 각 항목은 **표기 후보 중 하나**만 나오면
된다. `[["100"], ["곡", "트랙"]]` = 100 이 있어야 하고, 곡 또는 트랙이 있어야 한다. 한국어 답변은
표기가 흔들리므로 후보를 허용하지 않으면 표현을 재게 된다.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

_WS = re.compile(r"\s+")


def _norm(text: str) -> str:
    """공백 축약 + NFC. **소문자화는 안 한다** — 한국어에는 대소문자가 없고, 영문 식별자
    (`NexusResponse`, `SELECT`)는 대소문자가 뜻을 가진다."""
    return _WS.sub(" ", unicodedata.normalize("NFC", text or "")).strip()


@dataclass
class AnswerScore:
    qid: str
    grounded: bool = False
    cites_gold: bool = False
    facts: list[bool] = field(default_factory=list)
    abstained: bool = False
    llm_failed: bool = False
    n_citations: int = 0
    unverified: int = 0

    @property
    def has_facts(self) -> bool:
        """`must_contain` 이 비어 있으면 참이 아니라 **잴 것이 없다** — 그 구분은 집계가 한다.

        **LLM 이 실패했으면 무조건 거짓이다.** 실패 시 답변 자리에 들어가는 것은 근거 원문 덤프라,
        요구한 사실이 거기 **당연히** 있다 — 그 문서에서 뽑은 사실이니까. 2026-08-08 에 실제로
        3건 중 2건이 그렇게 '통과' 했고, 원인은 API 크레딧 부족이었다. 답을 못 낸 것이 사실을
        맞힌 것으로 세어지면 이 자는 거꾸로 읽힌다.
        """
        return not self.llm_failed and bool(self.facts) and all(self.facts)

    @property
    def ok(self) -> bool:
        return not self.llm_failed and self.grounded and self.cites_gold and self.has_facts


def score_answer(qid: str, answer_text: str, citations: list[dict] | list,
                 gold_titles: set[str], must_contain: list[list[str]],
                 abstained: bool = False, llm_failed: bool = False) -> AnswerScore:
    """한 질의의 답변을 채점한다. 순수 함수 — DB 도 네트워크도 안 탄다."""
    def _get(c, k):
        return c.get(k) if isinstance(c, dict) else getattr(c, k, None)

    verified = [c for c in citations if _get(c, "verified")]
    unverified = len(citations) - len(verified)
    gold_norm = {_norm(t) for t in gold_titles}

    s = AnswerScore(qid=qid, abstained=abstained, llm_failed=llm_failed,
                    n_citations=len(citations), unverified=unverified)
    # 인용 0개는 grounded 가 아니다 — 아무것도 인용 안 하는 것이 가장 쉬운 만점이 되면 안 된다.
    s.grounded = len(citations) > 0 and unverified == 0
    s.cites_gold = any(_norm(_get(c, "title") or "") in gold_norm for c in verified)

    text = _norm(answer_text)
    s.facts = [any(_norm(alt) in text for alt in group) for group in must_contain]
    return s


def aggregate(scores: list[AnswerScore]) -> dict:
    """집계. **잴 수 없었던 것과 실패한 것을 섞지 않는다.**"""
    n = len(scores)
    measurable = [s for s in scores if s.facts and not s.llm_failed]
    failed_llm = [s for s in scores if s.llm_failed]
    return {
        "queries": n,
        # **LLM 이 실패한 실행은 결과가 아니다.** 실패 시 답변 자리에 근거 덤프가 들어가므로
        # 사실 검사가 거저 통과한다 — 그 상태의 집계를 '답변 품질' 로 읽으면 거꾸로 읽힌다.
        "llm_failed": len(failed_llm),
        "grounded": sum(1 for s in scores if s.grounded),
        "cites_gold": sum(1 for s in scores if s.cites_gold),
        "abstained": sum(1 for s in scores if s.abstained),
        "unverified_citations": sum(s.unverified for s in scores),
        "no_citation_at_all": sum(1 for s in scores if s.n_citations == 0),
        "facts_measurable": len(measurable),
        "facts_present": sum(1 for s in measurable if s.has_facts),
        "all_three": sum(1 for s in scores if s.ok),
        "failed": [s.qid for s in scores if not s.ok],
    }
