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

#: 답변자가 **질문 전체에 대해** 답을 거절했는가. 문구 목록이 아니라 **구조**로 잡는다:
#: 거절은 *근거를 지목하며* 부정한다.
#:
#: 앞선 판은 관찰한 문구 3개를 나열했고, **바로 다음 실행에서 4번째 표현에 뚫렸다** —
#: "제공된 근거로는 해당 질문에 답변하기 어렵습니다". 목록을 늘리는 것은 다음 표현에서 또
#: 뚫린다. 반면 "근거"를 언급하며 부정하는 모양은 네 표현 전부에 공통이고, 내용이 부정인
#: **답변**("차감되지 않습니다", "401로 실패합니다")은 근거를 지목하지 않으므로 안 걸린다.
#:
#: 그래도 어휘 규칙이라는 사실은 변하지 않는다 — LLM 심판을 안 쓰는 이 자의 방침을 따르되,
#: 뚫릴 수 있다는 것을 테스트가 실제 문구로 고정한다.
_EVIDENCE = r"(제공된 |검색된 |주어진 )?(근거|문서|자료)"
_NEGATION = r"(없|않|어렵|불가|못 (찾|하)|아닙니다)"
#: 간격 80 — 40 은 `제공된 근거에서 **"재생목록 이동"**에 대한 구체적인 수량 제한 정보를
#: 찾을 수 없습니다` 를 놓쳤다. 40/60/80/120/200 을 실제 40건에 걸어 보니 60 이상은 셋을
#: 모두 잡고 오탐이 0 이었다. 문장 경계가 이미 범위를 막으므로 여유를 둔 80 을 쓴다.
_REFUSAL = re.compile(_EVIDENCE + r".{0,80}?" + _NEGATION)

#: 거절은 **첫 문장**에서만 센다. 답을 하면서 하위 항목 하나만 "확인되지 않는다" 고 덧붙이는
#: 경우가 흔하고(2026-08-10 실행 40건 중 2건), 그것은 기권이 아니라 답변이다. 진짜 기권은 첫
#: 문장에서 거절한다.
#:
#: 앞선 판은 "앞 110자" 였다. 같은 40건에서 결과는 같았지만, 그건 그 답변들이 길었기 때문이지
#: 규칙이 맞아서가 아니다 — 짧은 답변이 끝에서 거절하면 기권으로 잘못 세어진다. 위치가 아니라
#: **문장 경계**가 뜻을 가진 단위다.
_LEADING_MARKUP = re.compile(r"^[#\s*_>-]+")
_SENTENCE_END = re.compile(r"(다\.|습니다\.|\?|!)")
_NO_SENTENCE_END_CAP = 160


def _first_sentence(text: str) -> str:
    head = _LEADING_MARKUP.sub("", _norm(text))
    m = _SENTENCE_END.search(head)
    return head[: m.end()] if m else head[:_NO_SENTENCE_END_CAP]


def is_abstention(answer_text: str) -> bool:
    """답변자가 질문 자체를 거절했는가. **어휘 규칙이고, 한계는 여기 적어 둔다.**

    LLM 심판을 안 쓰는 이 자의 방침을 따른다(그쪽 취향을 재게 되므로). 대신 어휘 규칙은
    표현이 바뀌면 놓치고, 그때는 `_REFUSAL` 이 늘어야 한다 — 조용히 틀리지 않도록 테스트가
    실제 답변 문구를 고정한다.
    """
    return bool(_REFUSAL.search(_first_sentence(answer_text)))


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

    @property
    def outcome(self) -> str:
        """`correct` | `incorrect` | `abstained` | `unmeasurable`.

        **기권이 사실검사보다 먼저다.** 거절 문장은 질문의 어휘를 그대로 되풀이하므로
        `must_contain` 이 거저 통과한다 — 2026-08-10 실측에서 `pb-part-07` 이 "태스크와 디제잉
        포인트의 관계를 확인할 수 없습니다" 라고 거절하면서 `태스크`·`다른` 을 둘 다 담아
        사실검사를 통과했다. 거절을 정답으로 세면 이 자는 거꾸로 읽힌다.
        """
        if self.llm_failed:
            return "unmeasurable"
        if self.abstained:
            return "abstained"
        return "correct" if (self.has_facts and self.cites_gold) else "incorrect"


#: 근거 충분성 × 결과. 칸마다 **다른 곳을 고치라고 말한다** — 그것이 이 분류의 유일한 목적이다.
#: (Google, *Sufficient Context*, arXiv:2411.06037 의 2×3 격자를 이 리포의 자에 맞춘 것)
CELL_MEANING = {
    ("sufficient", "correct"): "정상",
    ("sufficient", "incorrect"): "생성 결함 — 근거가 왔는데 답이 틀렸다",
    ("sufficient", "abstained"): "과잉 기권 — 답할 수 있었는데 안 했다",
    ("insufficient", "correct"): "파라메트릭 — 근거 없이 맞혔다(운이거나 사전지식)",
    ("insufficient", "incorrect"): "**환각** — 근거 없이 그럴듯한 답을 했다",
    ("insufficient", "abstained"): "정직한 기권 — 검색을 고쳐라",
}


def score_answer(qid: str, answer_text: str, citations: list[dict] | list,
                 gold_titles: set[str], must_contain: list[list[str]],
                 abstained: bool = False, llm_failed: bool = False) -> AnswerScore:
    """한 질의의 답변을 채점한다. 순수 함수 — DB 도 네트워크도 안 탄다."""
    def _get(c, k):
        return c.get(k) if isinstance(c, dict) else getattr(c, k, None)

    verified = [c for c in citations if _get(c, "verified")]
    unverified = len(citations) - len(verified)
    gold_norm = {_norm(t) for t in gold_titles}

    # `abstained` 인자는 코드가 세운 플래그(`AnswerResult.abstained`, 조건 = 근거 0건)다.
    # 그 조건은 BM25 가 늘 무언가를 돌려주므로 **한 번도 안 터진다**(abstention-never-fires).
    # 그래서 답변 텍스트에서 직접 본다 — 답변자가 질문을 거절했는가.
    s = AnswerScore(qid=qid, abstained=bool(abstained) or is_abstention(answer_text),
                    llm_failed=llm_failed,
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
        # **오답과 기권을 한 칸에 뭉치지 않는다.** 정직한 기권(검색 결함)과 오답(생성 결함)은
        # 정반대 사건인데, `all_three` 는 둘을 같은 0점으로 센다. 2026-08-10 에 그 뭉침 때문에
        # "답변 품질이 내려갔다" 를 잘못 읽었다.
        "outcomes": {k: sum(1 for s in scores if s.outcome == k)
                     for k in ("correct", "incorrect", "abstained", "unmeasurable")},
        "abstained_qids": [s.qid for s in scores if s.outcome == "abstained"],
        "incorrect_qids": [s.qid for s in scores if s.outcome == "incorrect"],
    }


def grid(scores: list[AnswerScore], sufficiency: dict[str, str]) -> dict:
    """근거 충분성 × 결과. `sufficiency` 는 qid → 'sufficient'|'insufficient'.

    충분성을 안 주면 격자를 만들지 않는다 — 절반만 아는 격자는 칸의 뜻을 잃는다.
    """
    cells: dict[str, list[str]] = {}
    for s in scores:
        suff = sufficiency.get(s.qid)
        if suff not in ("sufficient", "insufficient") or s.outcome == "unmeasurable":
            continue
        cells.setdefault(f"{suff}/{s.outcome}", []).append(s.qid)
    return {k: {"n": len(v), "qids": sorted(v),
                "means": CELL_MEANING.get(tuple(k.split("/")), "")}
            for k, v in sorted(cells.items())}
