"""답변 품질 — **LLM 심판 없이** 결정론으로 채점한다.

이 리포는 검색을 엄격하게 측정해 왔고 **답변은 한 번도 안 측정했다.** 있는 것은 결정론적 가드 셋뿐이다
(인용 사후검증·숫자 근거검증·근거 신선도). 셋 다 답변이 근거를 **벗어났는지**를 보지, 답이
**맞는지**를 보지 않는다.

여기서 측정하는 세 가지. 전부 코드가 판단한다 — 답이 좋은지를 LLM 에게 물으면 그 LLM 의 취향을 측정하게
되고, 그 취향은 우리 라벨보다 검증이 덜 된 것이다.

| 측정하는 것 | 방법 | 실패가 뜻하는 것 |
|---|---|---|
| `grounded` | 인용이 하나 이상 있고 전부 근거 packet 안의 문서다 | 출처를 지어냈다 |
| `cites_gold` | 인용 중 하나가 **정답 문서**를 가리킨다 | 엉뚱한 문서로 답했다 |
| `has_facts` | 답변에 `must_contain` 의 사실이 들어 있다 | 검색은 맞았는데 답이 틀렸다 |

**인용이 0개인 답변은 grounded 가 아니다.** 미검증 인용 수만 보면 0이라 통과해 버린다 — 아무것도
인용하지 않는 것이 가장 쉬운 만점이 된다. `ADR-0002`(근거 없는 답변 금지)가 막으려던 바로 그
형태라, 여기서 명시적으로 막는다.

`must_contain` 의 모양: **모든 항목**이 만족돼야 하고, 각 항목은 **표기 후보 중 하나**만 나오면
된다. `[["100"], ["곡", "트랙"]]` = 100 이 있어야 하고, 곡 또는 트랙이 있어야 한다. 한국어 답변은
표기가 흔들리므로 후보를 허용하지 않으면 표현을 측정하게 된다.
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
#: 그래도 어휘 규칙이라는 사실은 변하지 않는다 — LLM 심판을 안 쓰는 이 채점기의 방침을 따르되,
#: 뚫릴 수 있다는 것을 테스트가 실제 문구로 고정한다.
_EVIDENCE = r"(제공된 |검색된 |주어진 )?(근거|문서|자료)"
_NEGATION = r"(없|않|어렵|불가|못 (찾|하)|아닙니다)"
#: 간격 80 — 40 은 `제공된 근거에서 **"재생목록 이동"**에 대한 구체적인 수량 제한 정보를
#: 찾을 수 없습니다` 를 놓쳤다. 40/60/80/120/200 을 실제 40건에 걸어 보니 60 이상은 셋을
#: 모두 잡고 오탐이 0 이었다. 문장 경계가 이미 범위를 막으므로 여유를 둔 80 을 쓴다.
_REFUSAL = re.compile(_EVIDENCE + r".{0,80}?" + _NEGATION)

#: 거절은 **문장(세그먼트) 범위**를 갖는다 — SPEC-nexus-answer-quality-ruler §3.1.
#:
#: 앞선 두 판은 위치만 봤다("앞 110자" → "첫 문장"). 둘 다 같은 자리에서 틀렸다: 답을 다 하면서
#: 하위 항목 하나를 "확인되지 않는다" 고 좁히는 답변을 **전체 기권**으로 셌다(2026-08-11 실행에서
#: `pb-space-01`·`pb-mix-08` 2건). 반대편에는 거절 문장이 질문 어휘를 되풀이해 `must_contain` 을
#: 거저 통과시킨 결함이 있었다(`pb-part-07`). 두 오탐이 반대 방향인 것이 **단위가 틀렸다**는 신호다.
#:
#: 그래서 두 조건을 함께 본다. ① 사실은 거절 세그먼트 **밖**에서 배달돼야 세고, ② 기권은 거절이
#: **선두**에 설 때만이다. ②가 없던 첫 판은 새 45건 표본에서 새 오탐을 만들었다 — 답을 다 하고
#: 근거 등급을 밝히는 **후행 단서**("실제 구현 관측 데이터는 제공된 근거에 없습니다")가 기권으로
#: 세어졌다. 규칙이 표본에 맞춰졌다는 뜻이므로, 다음 반증도 여기 기록될 자리를 비워 둔다.
_SEGMENT = re.compile(r"(?<=다\.)|(?<=습니다\.)|(?<=\?)|(?<=!)|\n")
#: 헤딩·구분선은 실질 세그먼트가 아니다 — `## 결론` 뒤에 오는 거절도 선두다.
_NOT_SUBSTANTIVE = re.compile(r"^(#{1,6}\s.*|[#>*\-\s_|=]*)$")


def segments(answer_text: str) -> list[str]:
    """답변을 문장/줄 단위로 자른다. 표·코드처럼 종결어미가 없는 줄은 줄 단위로 남는다."""
    raw = unicodedata.normalize("NFC", answer_text or "")
    return [s for s in _SEGMENT.split(raw) if s and s.strip()]


def refusal_segments(answer_text: str) -> list[str]:
    """근거를 지목하며 부정하는 세그먼트. **어휘 규칙이고, 한계는 SPEC §4 에 적혀 있다.**"""
    return [s for s in segments(answer_text) if _REFUSAL.search(_norm(s))]


def refuses(answer_text: str) -> bool:
    """답변 어딘가에서 근거를 지목하며 부정했는가. 대조군(답변불가 5건)이 측정하는 값이다."""
    return bool(refusal_segments(answer_text))


def leads_with_refusal(answer_text: str) -> bool:
    """첫 **실질** 세그먼트가 거절인가. 헤딩·구분선은 건너뛴다."""
    for seg in segments(answer_text):
        s = _norm(seg)
        if not s or _NOT_SUBSTANTIVE.match(s):
            continue
        return bool(_REFUSAL.search(s))
    return False


def delivered_text(answer_text: str) -> str:
    """거절 세그먼트를 뺀 나머지 — 답변자가 **배달한** 것. 사실검사는 여기서만 한다."""
    return " ".join(s for s in segments(answer_text) if not _REFUSAL.search(_norm(s)))


def is_abstention(answer_text: str, must_contain: list[list[str]] | None = None) -> bool:
    """답변자가 질문 자체를 거절했는가 = **선두에서 거절했고, 요구한 사실을 배달하지 않았다.**

    `must_contain` 을 안 주면 배달할 것이 없다는 뜻이고(대조군이 그렇다), 그때는 선두 거절이 곧
    기권이다. `all([]) == True` 에 맡기면 반대로 읽히므로 명시적으로 쓴다.
    """
    if not leads_with_refusal(answer_text):
        return False
    if not must_contain:
        return True
    return not all(facts_present(must_contain, delivered_text(answer_text)))


def _norm(text: str) -> str:
    """공백 축약 + NFC. **소문자화는 안 한다** — 한국어에는 대소문자가 없고, 영문 식별자
    (`NexusResponse`, `SELECT`)는 대소문자가 뜻을 가진다."""
    return _WS.sub(" ", unicodedata.normalize("NFC", text or "")).strip()


def facts_present(must_contain: list[list[str]] | None, text: str) -> list[bool]:
    """`must_contain` 각 항목이 이 텍스트에 있는가 — **항목은 AND, 항목 안의 후보는 OR.**

    채점기와 재서명 워크시트가 **같은 함수**를 써야 한다. 워크시트가 '이 요구는 지금 본문에서
    여전히 성립한다' 고 사람에게 말할 때, 그 '성립' 이 채점기가 답변에 적용하는 규칙과 다르면
    워크시트는 재서명하는 사람에게 거짓말을 한다. 공백을 *지우는* 관대한 사본을 따로 두면
    '본문에는 있다' 면서 채점기는 떨어뜨리는 조합이 나온다 — 그래서 사본을 두지 않는다.
    """
    body = _norm(text)
    return [any(_norm(alt) in body for alt in group) for group in (must_contain or [])]


#: **언급과 주장은 다르다.** 2026-08-26 에 이 구분이 없어서 채점기가 천장에 붙었다.
#:
#: 같은 질문에 두 답변이 나왔다. 하나는 *"…4,000점입니다"* 로 열고 낡은 값을 기각했고, 다른
#: 하나는 표에 `개별 문서 | 4,000점` 이라고 **적어 놓고** *"확인 전까지는 어느 수치도 단정할 수
#: 없습니다"* 로 닫았다. 부분일치 채점기는 **둘 다 통과시킨다** — 값이 텍스트에 있기 때문이다.
#: 그래서 절 채움(#318)을 껐다 켜도 15/15 가 그대로였다: 채점기가 처치를 못 봤다.
#:
#: 여기서 측정하는 것은 **답변이 그 값을 자기 답으로 내세웠는가**다. 두 자리만 본다:
#:
#:   선두   시스템 프롬프트가 요구하는 자리 — "핵심 답변을 먼저 제시하세요"
#:   결론   접속 부사가 여는 마무리 — "따라서 …", "요약: …"
#:
#: **왜 두 자리인가.** 선두만 보는 판을 30건에 걸었더니 결론에서 값을 확정하는 답변
#: (선두는 *"근거들 사이에 충돌이 있으며"* 로 열고 끝에서 *"따라서 …10점이 정본"*)을 떨어뜨렸다.
#: 반대로 결론만 보면 선두에서 답하고 끝에 참고를 붙이는 답변을 놓친다. 둘의 합집합이 30건
#: 손라벨과 일치했다 — 그 실측은 `tests/eval/answer-facts/README.md` 에 있다.
#:
#: ⚠ **이것도 어휘 규칙이다.** *"따라서 4,000점일 가능성이 있습니다"* 는 통과한다. 이 채점기는
#: **자리**를 측정하지 확신을 측정하지 않는다. 뚫리는 문구는 테스트에 실물로 박아 둔다.
_VERDICT_OPENER = re.compile(r"(따라서|그러므로|결론적으로|정리하면|요약|최종적으로|즉,)")


def _is_break(seg: str) -> bool:
    """표·인용·구분선·헤딩 — **산문이 끊기는 자리**. 근거를 늘어놓는 부분이 여기서 시작한다."""
    t = seg.strip()
    return bool(t) and (t.startswith("|") or t.startswith(">") or t.startswith("#")
                        or bool(re.fullmatch(r"[-*_=\s]{3,}", t)))


def lead_segments(answer_text: str) -> list[str]:
    """**선두** — 앞머리 헤딩을 건너뛴 뒤, 첫 구조 전환(표·인용·구분선·헤딩)까지의 산문.

    답변 형식 계약이 이 자리를 정한다(`llm/prompts.py`: "핵심 답변을 먼저 제시하세요").
    구조 전환 뒤부터는 근거를 **늘어놓는** 자리이고, 늘어놓기는 주장이 아니다.
    """
    out: list[str] = []
    for seg in segments(answer_text):
        if not seg.strip():
            continue
        if _is_break(seg):
            if out:            # 산문이 시작된 뒤의 전환 = 선두 끝
                break
            continue           # 앞머리 헤딩·구분선은 건너뛴다
        out.append(seg)
    return out


def verdict_segments(answer_text: str) -> list[str]:
    """**결론** — 접속 부사가 여는 세그먼트. 표 행·인용문은 결론이 아니다."""
    return [s for s in segments(answer_text)
            if not _is_break(s) and _VERDICT_OPENER.search(_norm(s))]


def asserts_value(surfaces: list[str] | None, answer_text: str) -> bool:
    """**하나의 값**이 선두 또는 결론에서 주장됐는가. `surfaces` 는 그 값의 표기 후보(OR).

    `facts_present` 가 *"어딘가에 있다"* 를 측정하는 자리에서 이것은 *"답으로 내세웠다"* 를 측정한다.
    둘 다 필요하다 — 전자는 부재 회귀 그물이고, 후자는 개선 게이지다.

    ⚠ **`must_contain` 에 쓰지 마라.** 인자가 `list[list[str]]` 이 아니라 `list[str]` 인 것은
    실수가 아니다. 이 채점기는 *"질문이 물은 값 하나를 답으로 확정했는가"* 만 측정하고, 여러 항목을
    AND 로 요구하는 라벨에는 뜻이 없다 — 2026-08-18 정책 8문항에 걸어 봤더니 세 형태로
    틀렸다:

        p02  "로그인 방식별 개수" 처럼 **나열을 요구하는 질문**은 표가 곧 답이다.
             이 채점기는 표를 '늘어놓기' 로 보므로 옳은 답을 떨어뜨린다.
        p07  요구 항목이 **부차 조건**("충돌을 언급할 것")이면 그것은 결론 자리에 안 온다.
        p08  `파티 개설` 을 요구하는데 답변은 `파티를 개설` 이라 쓴다 — 표기 문제이지
             확정 문제가 아니다.

    즉 이 채점기의 정의역은 **단일 값 질문**이다. 그 밖에서 나온 숫자는 품질이 아니다.
    """
    if not surfaces:
        return False
    said = " ".join(lead_segments(answer_text) + verdict_segments(answer_text))
    return all(facts_present([list(surfaces)], said))


@dataclass
class AnswerScore:
    qid: str
    grounded: bool = False
    cites_gold: bool = False
    facts: list[bool] = field(default_factory=list)
    abstained: bool = False
    #: 답변 어딘가에서 근거를 지목하며 부정했는가. 기권과 **다르다** — 답을 다 하면서 한 항목을
    #: 좁힌 답변도 참이다. 대조군(답변불가)이 측정하는 값이 이것이다.
    refused: bool = False
    llm_failed: bool = False
    n_citations: int = 0
    unverified: int = 0
    #: 인용된 문서 중 **라벨이 한 번도 판정한 적 없는** 것(테넌트에는 실재한다). gold 도 아니고
    #: not_gold 도 아니다 — 사람이 읽고 둘 중 하나로 보내야 닫힌다.
    unjudged: list[str] = field(default_factory=list)

    @property
    def has_facts(self) -> bool:
        """`must_contain` 이 비어 있으면 참이 아니라 **측정할 것이 없다** — 그 구분은 집계가 한다.

        **LLM 이 실패했으면 무조건 거짓이다.** 실패 시 답변 자리에 들어가는 것은 근거 원문 덤프라,
        요구한 사실이 거기 **당연히** 있다 — 그 문서에서 뽑은 사실이니까. 2026-08-08 에 실제로
        3건 중 2건이 그렇게 '통과' 했고, 원인은 API 크레딧 부족이었다. 답을 못 낸 것이 사실을
        맞힌 것으로 세어지면 이 채점기는 거꾸로 읽힌다.
        """
        return not self.llm_failed and bool(self.facts) and all(self.facts)

    @property
    def ok(self) -> bool:
        return not self.llm_failed and self.grounded and self.cites_gold and self.has_facts

    @property
    def outcome(self) -> str:
        """`correct` | `incorrect` | `abstained` | `unadjudicated` | `unmeasurable`.

        **기권이 사실검사보다 먼저다.** 거절 문장은 질문의 어휘를 그대로 되풀이하므로
        `must_contain` 이 거저 통과한다 — 2026-08-10 실측에서 `pb-part-07` 이 "태스크와 디제잉
        포인트의 관계를 확인할 수 없습니다" 라고 거절하면서 `태스크`·`다른` 을 둘 다 담아
        사실검사를 통과했다. 거절을 정답으로 세면 이 채점기는 거꾸로 읽힌다.
        (이제 사실은 **배달**돼야 세므로 그 통과 자체가 막히지만, 순서는 그대로 둔다.)

        **`unadjudicated` 는 오답이 아니다.** 사실을 배달했고 인용이 전부 해소되는데 라벨이 그
        문서를 판정한 적이 없다면, 이 채점기는 그 문서가 답을 담는지 **모른다**. 모르는 것을 오답으로
        세면 `pb-part-02` 처럼 정답이 3회 연속 오답으로 찍힌다(SPEC §1.2).

        **`correct` 는 `grounded` 를 요구한다.** 예전에는 `has_facts and cites_gold` 만 봤고,
        바로 아래 `unadjudicated` 는 `grounded` 를 요구했다 — 그 비대칭 때문에 **인용이 검증되지
        않은 답변이 헤드라인 '정답' 에 들어갔다.** 2026-08-12 `rev6-r1` 이 그것이다: 콘솔은
        `정답 40 오답 0`, 같은 실행의 누적 로그는 `all_three 39`(미검증 인용 2건). 한 리포트가
        두 개의 '정답' 을 담고 있었고 사람 눈에 먼저 닿는 쪽이 후한 값이었다. 근거가 확인되지
        않은 답을 맞았다고 세는 것은 [[ADR-0002]] 가 금지하는 그 형태다.
        """
        if self.llm_failed:
            return "unmeasurable"
        if self.abstained:
            return "abstained"
        if self.has_facts and self.cites_gold and self.grounded:
            return "correct"
        if self.has_facts and self.grounded and self.unjudged:
            return "unadjudicated"
        return "incorrect"


#: 근거 충분성 × 결과. 칸마다 **다른 곳을 고치라고 말한다** — 그것이 이 분류의 유일한 목적이다.
#: (Google, *Sufficient Context*, arXiv:2411.06037 의 2×3 격자를 이 리포의 채점기에 맞춘 것)
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
                 abstained: bool = False, llm_failed: bool = False,
                 not_gold_titles: set[str] | None = None,
                 known_titles: set[str] | None = None) -> AnswerScore:
    """한 질의의 답변을 채점한다. 순수 함수 — DB 도 네트워크도 안 탄다.

    `known_titles` 는 **측정하고 있는 테넌트**의 문서 제목이다. 팩이 아니라 테넌트인 이유: 팩은
    2026-08-07 에 얼린 116건이고 테넌트는 적재마다 자란다. 지난주에 들어온 문서를 인용했다고
    정답을 오답으로 세면 SPEC §1.2 의 결함이 새 문서에 대해 그대로 되살아난다.
    안 주면 해소할 방법이 없다는 뜻이므로 미판정 판정도 하지 않는다(옛 동작 그대로).
    """
    def _get(c, k):
        return c.get(k) if isinstance(c, dict) else getattr(c, k, None)

    verified = [c for c in citations if _get(c, "verified")]
    unverified = len(citations) - len(verified)
    gold_norm = {_norm(t) for t in gold_titles}
    not_gold_norm = {_norm(t) for t in (not_gold_titles or set())}
    known_norm = {_norm(t) for t in known_titles} if known_titles is not None else None

    # `abstained` 인자는 코드가 세운 플래그(`AnswerResult.abstained`, 조건 = 근거 0건)다.
    # 그 조건은 BM25 가 늘 무언가를 돌려주므로 **한 번도 안 터진다**(abstention-never-fires).
    # 그래서 답변 텍스트에서 직접 본다 — 답변자가 질문을 거절했는가.
    s = AnswerScore(qid=qid,
                    abstained=bool(abstained) or is_abstention(answer_text, must_contain),
                    refused=refuses(answer_text),
                    llm_failed=llm_failed,
                    n_citations=len(citations), unverified=unverified)
    # 인용 0개는 grounded 가 아니다 — 아무것도 인용 안 하는 것이 가장 쉬운 만점이 되면 안 된다.
    s.grounded = len(citations) > 0 and unverified == 0
    s.cites_gold = any(_norm(_get(c, "title") or "") in gold_norm for c in verified)

    # 미판정 = 해소되는 인용인데 gold 도 not_gold 도 아니고, **테넌트에 실재**하는 문서.
    # 정답으로 세어질 때도 남긴다 — 안 그러면 미판정 풀이 조용히 자란다(SPEC §3.2).
    seen: list[str] = []
    for c in verified:
        title = _norm(_get(c, "title") or "")
        if not title or title in gold_norm or title in not_gold_norm or title in seen:
            continue
        if known_norm is not None and title in known_norm:
            seen.append(title)
    s.unjudged = seen

    # **사실은 배달돼야 센다.** 거절 세그먼트 안에서 질문 어휘가 되풀이된 것은 배달이 아니다
    # (`pb-part-07`: 거절하면서 `태스크`·`다른` 을 담아 사실검사를 통과했다).
    s.facts = facts_present(must_contain, delivered_text(answer_text))
    return s


def aggregate(scores: list[AnswerScore]) -> dict:
    """집계. **측정할 수 없었던 것과 실패한 것을 섞지 않는다.**"""
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
        # 거절과 기권은 다른 수다. 답을 하면서 한 항목을 좁힌 답변이 `refused` 에는 들어가고
        # `abstained` 에는 안 들어간다 — 그 차이가 §1.1 의 오탐이 살던 자리다.
        "refused": sum(1 for s in scores if s.refused),
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
                     for k in ("correct", "incorrect", "abstained", "unadjudicated",
                               "unmeasurable")},
        "abstained_qids": [s.qid for s in scores if s.outcome == "abstained"],
        "incorrect_qids": [s.qid for s in scores if s.outcome == "incorrect"],
        "unadjudicated_qids": [s.qid for s in scores if s.outcome == "unadjudicated"],
        # **정답으로 세어진 질의의 미판정 인용도 여기 들어온다.** 게이트를 여는 것은
        # `unadjudicated_qids` 뿐이지만, 판정할 거리는 전부 보여야 한다(SPEC §3.2).
        "adjudication_candidates": {s.qid: s.unjudged for s in scores if s.unjudged},
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
