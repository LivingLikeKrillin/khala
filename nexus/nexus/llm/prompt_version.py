"""어떤 프롬프트가 이 답을 만들었는가 — **사람이 번호를 올리지 않아도** 남는다.

프롬프트를 고치면 답이 달라진다. 그런데 지금까지 기록에는 그 경계가 없었다: `SYSTEM_PROMPT`
한 줄을 바꿔도 어제 행과 오늘 행이 똑같아 보이고, "지난주보다 답이 나빠졌다" 를 조사할 때
**무엇이 바뀌었는지 알 방법이 없다.** U3 가 턴당 프롬프트를 둘로 늘리면서 더 아파졌다.

**버전은 손으로 매기지 않는다.** `PROMPT_VERSION = 3` 같은 상수는 고치는 사람이 올려야 하고,
그 규율은 반드시 한 번은 깨진다 — 그리고 깨진 순간 기록은 조용히 거짓이 된다. 그래서 여기서는
**프롬프트 텍스트 자체에서 파생**한다. 텍스트가 바뀌면 값이 바뀌고, 안 바뀌면 안 바뀐다.
잊을 수 있는 단계가 없다.

공백만 바꿔도 값이 바뀐다. 그것은 결함이 아니라 의도다 — 모델에게 가는 바이트가 달라졌으면
그 실행은 다른 실행이다. **의미가 같다는 판단은 사람의 것이고, 이 값은 사실만 적는다.**
"""

from __future__ import annotations

import hashlib
import inspect

#: 짧게 자른다. 이 값은 **구간을 가르는 표시**이지 암호학적 증명이 아니다 — 12 hex 면
#: 로그에서 눈으로 비교할 수 있고 충돌은 실무적으로 문제되지 않는다.
_LEN = 12


def fingerprint(*parts: str) -> str:
    """주어진 조각들의 안정적 해시. 순서와 내용이 같으면 같은 값."""
    h = hashlib.sha256()
    for p in parts:
        h.update((p or "").encode("utf-8"))
        h.update(b"\x00")          # 조각 경계 — 이어붙임 모호성을 없앤다
    return h.hexdigest()[:_LEN]


def _source_of(fn) -> str:
    """함수 본문 텍스트. 못 읽으면 빈 문자열 — 진단이 답변 경로를 죽일 수 없다.

    사용자 프롬프트는 **템플릿**이 행동을 정한다(근거를 어떻게 감싸는지, 무엇을 지시하는지).
    질의·근거는 매 요청 달라지므로 해시에 넣지 않는다 — 넣으면 모든 행이 서로 달라 아무것도
    구분하지 못한다.
    """
    try:
        return inspect.getsource(fn)
    except (OSError, TypeError):
        return ""


def answer_prompt_sha() -> str:
    """답변 생성 프롬프트(시스템 + 사용자 템플릿)의 지문."""
    from nexus.llm.prompts import SYSTEM_PROMPT, build_user_prompt

    return fingerprint(SYSTEM_PROMPT, _source_of(build_user_prompt))


def rewrite_prompt_sha() -> str:
    """질의 재작성 프롬프트의 지문 (SPEC-nexus-multi-turn-retrieval §3.2)."""
    from nexus.search.rewrite import SYSTEM_PROMPT, build_user_prompt

    return fingerprint(SYSTEM_PROMPT, _source_of(build_user_prompt))
