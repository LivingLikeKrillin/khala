"""근거가 답하기에 **충분한가** — 답변자와 분리된 판정자.

이 리포는 2026-08-09 에 "근거가 약하면 기권" 문턱을 세우려다 실측으로 막혔다: 선언한 질의와
답한 질의의 RRF 점수 분포가 완전히 겹쳤고(`top` 은 오히려 선언 쪽 최소값이 더 높았다), 45건
어디에도 자를 자리가 없었다. 검색 점수는 *어휘·의미가 가까운가* 를 재지 *답이 그 안에 있는가* 를
재지 않는다.

**이것은 알려진 문제이고 이름이 있다.** Google Research 의 "sufficient context"(arXiv 2411.06037):

* 충분 = 근거가 확정적 답에 필요한 정보를 **전부** 담는다. 불충분 = 없거나·불완전하거나·
  결론이 안 나거나·**서로 모순된다**.
* RAG 는 오히려 **기권 능력을 떨어뜨린다** — 근거가 붙으면 모델이 확신해서 기권 대신 틀린 답을
  낸다.
* 판정은 **질의 + 근거만** 보고 내린다. 정답을 안 본다.
* 그리고 **구조적 변경이 필요하다. 프롬프트 개선으로는 안 된다.**

**판정자는 답변자와 분리한다.** 답변하는 LLM 에게 "네 답이 근거에 있었냐" 를 함께 물으면
판정자와 피판정자가 같아지고, 같은 논문이 "모델은 자기 불충분을 잘 못 본다" 고 한 구도가 된다.
여기서는 답변을 보지 않고 **질의와 근거만** 준다.

ADR-0002 의 "시스템이 판정하고 LLM은 서술한다" 와의 관계: 이 컴포넌트는 **판정 쪽**이다. 서술을
맡은 LLM 에게 판정을 겸하게 하는 것이 아니라, 판정을 별도 자리로 꺼내 코드가 읽게 한다. 판정
결과는 문장이 아니라 값이다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum


class Sufficiency(str, Enum):
    SUFFICIENT = "sufficient"
    INSUFFICIENT = "insufficient"
    #: 판정자가 읽을 수 없는 것을 냈다. **충분도 불충분도 아니다** — 삼키면 "판정했다" 는
    #: 거짓이 된다. 호출자가 degrade 를 고르게 한다.
    UNPARSEABLE = "unparseable"


@dataclass(frozen=True)
class SufficiencyVerdict:
    label: Sufficiency
    reason: str = ""
    raw: str = ""

    @property
    def is_sufficient(self) -> bool:
        """**불명은 충분이 아니다.** 읽을 수 없는 판정을 충분으로 접으면, 판정자가 고장 난
        순간부터 모든 질의가 조용히 통과한다."""
        return self.label is Sufficiency.SUFFICIENT


SYSTEM = (
    "너는 검색 근거가 어떤 질문에 답하기에 충분한지 판정한다. 답을 쓰지 않는다.\n\n"
    "충분(sufficient): 주어진 근거만으로 그 질문에 확정적으로 답할 수 있다.\n"
    "불충분(insufficient): 근거에 그 정보가 없거나, 일부만 있거나, 결론이 나지 않거나, "
    "근거끼리 모순된다.\n\n"
    "판단 기준은 **근거에 그 사실이 실재하는가** 이지, 주제가 비슷한가가 아니다. "
    "네가 이미 알고 있는 지식으로 메우지 마라 — 근거에 없으면 불충분이다.\n\n"
    "반드시 아래 두 줄만 출력하라. 다른 말은 쓰지 마라.\n"
    "VERDICT: sufficient\n"
    "REASON: <한 문장>"
)

_VERDICT = re.compile(r"^\s*VERDICT:\s*(sufficient|insufficient)\s*$", re.M | re.I)
_REASON = re.compile(r"^\s*REASON:\s*(.+)$", re.M)


def build_prompt(query: str, evidence: str) -> str:
    """판정자에게 가는 사용자 프롬프트. **답변은 넣지 않는다.**"""
    return f"## 질문\n{query}\n\n## 근거\n{evidence}\n"


def parse(raw: str) -> SufficiencyVerdict:
    """판정자 출력 → 값. 순수 함수, 예외 없음.

    형식을 못 맞추면 **추측하지 않는다.** 산문에서 '충분해 보인다' 를 읽어내려는 순간 이 판정은
    문자열 대조가 되고, 이 리포는 그 방식으로 이미 한 번 데였다(인용 검증기가 따옴표 한 글자에
    무너졌다).
    """
    m = _VERDICT.search(raw or "")
    if not m:
        return SufficiencyVerdict(Sufficiency.UNPARSEABLE, raw=raw or "")
    label = (Sufficiency.SUFFICIENT if m.group(1).lower() == "sufficient"
             else Sufficiency.INSUFFICIENT)
    r = _REASON.search(raw or "")
    return SufficiencyVerdict(label, reason=(r.group(1).strip() if r else ""), raw=raw or "")


async def judge_raw(query: str, evidence: str, llm_svc) -> SufficiencyVerdict:
    """한 번의 판정. **예외를 삼키지 않는다.**

    `judge()` 는 백엔드 장애를 `UNPARSEABLE` 로 접는데, 신호로 기록할 때는 그 접기가 거짓이 된다 —
    "판정자가 이상한 걸 냈다" 와 "판정자를 부르지도 못했다" 는 다른 사실이고, 후자만 골라 세야
    공급자 장애를 근거 부족으로 오독하지 않는다. 그래서 기록 경로는 이 쪽을 부르고 error/timeout 을
    자기가 구분한다 (SPEC-nexus-sufficiency-signal §3.3).
    """
    raw = await llm_svc.generate(SYSTEM, build_prompt(query, evidence))
    return parse(raw if isinstance(raw, str) else getattr(raw, "text", "") or "")


async def judge(query: str, evidence: str, llm_svc) -> SufficiencyVerdict:
    """한 번의 판정. 실패는 `UNPARSEABLE` 로 — 요청 경로를 깨지 않는다.

    평가 하니스용. 판정 실패와 호출 실패를 구분해야 하면 `judge_raw` 를 써라.
    """
    try:
        return await judge_raw(query, evidence, llm_svc)
    except Exception:  # noqa: BLE001 — 판정자 장애가 답변 경로를 죽이면 안 된다
        return SufficiencyVerdict(Sufficiency.UNPARSEABLE)


def judge_identity(llm_svc) -> str:
    """`{backend}/{model}/{prompt_sha}` — 이 행을 만든 판정자.

    셋 다 필요하다. **backend** 는 어느 클라이언트가 텍스트를 밖으로 날랐는지다(브리지는 키가 없을
    뿐 로컬이 아니다 — 같은 공급자로 나간다). **prompt_sha** 는 실제로 보낸 프롬프트에서 유도한다:
    손으로 관리하는 `v1` 은 누가 프롬프트를 고치고 잊는 순간 서로 다른 두 판정자를 한 이름 아래
    조용히 섞는다. 시스템 프롬프트만이 아니라 사용자 템플릿 모양까지 넣는 이유도 같다.
    """
    import hashlib
    import os

    backend = (os.getenv("NEXUS_LLM_PROVIDER") or "anthropic").strip().lower()
    model = getattr(llm_svc, "model", "unknown")
    material = SYSTEM + "\x00" + build_prompt("\x01", "\x02")   # 템플릿 모양까지 포함
    sha = hashlib.sha256(material.encode("utf-8")).hexdigest()[:8]
    return f"{backend}/{model}/{sha}"[:128]
