"""어떤 프롬프트가 이 답을 만들었는가 — **사람이 번호를 올리지 않아도** 남는다.

프롬프트를 고치면 답이 달라진다. 그런데 지금까지 기록에는 그 경계가 없었다: `SYSTEM_PROMPT`
한 줄을 바꿔도 어제 행과 오늘 행이 똑같아 보이고, "지난주보다 답이 나빠졌다" 를 조사할 때
**무엇이 바뀌었는지 알 방법이 없다.** U3 가 턴당 프롬프트를 둘로 늘리면서 더 아파졌다.

**버전은 손으로 매기지 않는다.** `PROMPT_VERSION = 3` 같은 상수는 고치는 사람이 올려야 하고,
그 규율은 반드시 한 번은 깨진다 — 그리고 깨진 순간 기록은 조용히 거짓이 된다. 그래서 여기서는
**프롬프트를 만드는 코드 자체에서 파생**한다. 코드가 바뀌면 값이 바뀌고, 안 바뀌면 안 바뀐다.
잊을 수 있는 단계가 없다.

공백만 바꿔도 값이 바뀐다. 그것은 결함이 아니라 의도다 — 모델에게 가는 바이트가 달라졌을 수
있으면 그 실행은 다른 실행이다. **의미가 같다는 판단은 사람의 것이고, 이 값은 사실만 적는다.**

⛔ **첫 판은 재료가 좁았다 (실측 2026-09-27).** `SYSTEM_PROMPT` · `USER_REQUEST_RULE` ·
`build_user_prompt` 소스 셋만 찍었다. 근거가 약할 때 붙는 규칙(08-18), 근거 꾸러미를 글로 바꾸는
`format_for_llm`(코드 값 절 · 판정 · 인용 문법 벗기기 · 등급 주석), 꾸러미를 채우는
`packet_for_answer` 는 전부 밖이었다. 그래서 08-29 ~ 09-23 의 답변 572행이 **한 값**이다 — 그
사이 모델이 받는 글은 여러 번 바뀌었다.

⇒ 재료를 함수가 아니라 **모듈 소스 전체**로 잡는다. 함수 하나를 찍으면 그 함수가 읽는 모듈
상수(인용 문법의 여는 괄호, 이름을 몇 개까지 보이는가)와 도우미가 빠진다 — 옛 결함이 정확히
그 모양이었다. 목록이 실제로 도는 코드를 덮는지는 `tests/test_prompt_version.py` 가 **프롬프트를
한 벌 써 보고 그동안 실행된 모듈을 세어** 확인한다. 이름을 보고 단정하지 않는다.

⚠ 모듈 전체라서 **프롬프트와 무관한 수정에도 판이 바뀐다**(예: `citations.py` 의 검증기). 판이
하나 더 갈라지면 기록이 조금 더 잘게 나뉘고, 판이 안 갈라지면 기록이 거짓이 된다. 앞쪽을 택한다.

⚠ **코드만 본다.** 설정으로 켜고 끄는 보강(정정 확인 패스 · 짝 확장 · 참조 채움 · 코드 값)은 이
값에 안 들어간다 — 그것이 바뀐 것은 이 값으로 못 본다.
"""

from __future__ import annotations

import functools
import hashlib
import importlib
import inspect

#: 짧게 자른다. 이 값은 **구간을 가르는 표시**이지 암호학적 증명이 아니다 — 12 hex 면
#: 로그에서 눈으로 비교할 수 있고 충돌은 실무적으로 문제되지 않는다.
_LEN = 12

#: 모델에게 가는 글을 **만드는** 코드가 사는 모듈. 모듈 소스 전체가 판에 들어간다.
#: 프롬프트를 쓰는 동안 실행되는 nexus 모듈은 전부 여기 있어야 한다 — 검사가 실행으로 센다.
ASSEMBLY_MODULES: tuple[str, ...] = (
    "nexus.llm.prompts",             # 시스템 프롬프트 · 규칙들 · 사용자 템플릿
    "nexus.search.evidence_packet",  # 꾸러미 조립(assemble_packet) · 글로 바꾸기(format_for_llm)
    "nexus.search.reconcile",        # 꾸러미를 채우는 이음매(packet_for_answer) · 정정 확인 · 코드 값
    "nexus.search.pairs",            # 짝 문서 채움
    "nexus.search.crossrefs",        # 가리킨 절 데려오기
    "nexus.search.provenance",       # 등급 주석과 표시
    "nexus.search.anchor_status",    # 문서가 부른 코드 이름의 현재 상태 한 줄
    "nexus.llm.citations",           # 근거 본문의 인용 문법 벗기기(as_quoted_content)
)


def fingerprint(*parts: str) -> str:
    """주어진 조각들의 안정적 해시. 순서와 내용이 같으면 같은 값."""
    h = hashlib.sha256()
    for p in parts:
        h.update((p or "").encode("utf-8"))
        h.update(b"\x00")          # 조각 경계 — 이어붙임 모호성을 없앤다
    return h.hexdigest()[:_LEN]


def _source_of(obj) -> str:
    """함수·모듈의 소스 텍스트. 못 읽으면 빈 문자열 — 진단이 답변 경로를 죽일 수 없다.

    재료는 **코드**다. 질의·근거는 매 요청 달라지므로 해시에 넣지 않는다 — 넣으면 모든 행이
    서로 달라 아무것도 구분하지 못한다.
    """
    try:
        return inspect.getsource(obj)
    except (OSError, TypeError):
        return ""


def _module_source(name: str) -> str:
    """모듈 소스 전체. 못 불러오거나 못 읽으면 빈 문자열.

    ⚠ 빈 문자열은 **언제나 같은 값**이라, 그 모듈을 고쳐도 판이 안 바뀐다. 목록의 오타가 그렇게
    조용히 재료를 줄이므로 검사가 목록의 모듈마다 소스가 실제로 읽히는지 본다.
    """
    try:
        return _source_of(importlib.import_module(name))
    except Exception:  # noqa: BLE001 — 진단이 답변 경로를 죽일 수 없다
        return ""


@functools.lru_cache(maxsize=1)
def _assembly_sources() -> tuple[str, ...]:
    """재료는 **프로세스당 한 번** 읽는다. 도는 코드는 기동할 때 정해지므로 매 요청 파일을 읽을
    이유가 없고, 기동 뒤 디스크의 파일이 바뀌어도 도는 코드는 안 바뀐다(`--reload` 로 도는 개발
    배포는 파일이 바뀌면 프로세스가 새로 뜬다)."""
    return tuple(_module_source(m) for m in ASSEMBLY_MODULES)


def prompt_version() -> str:
    """답변 프롬프트와 근거 꾸러미를 **만드는 코드**의 판.

    응답(`prompt_version`)과 기록(`search_log.prompt_version`)이 같은 값을 싣는다 — 값은 공유
    이음매(`search/reconcile.py::packet_for_answer`)가 꾸러미에 찍고, 표면은 그것을 옮긴다.

    `USER_REQUEST_RULE` 과 `WEAK_EVIDENCE_RULE` 은 요청에 따라 붙는 조각이라 **한 배포에 프롬프트가
    여러 변종**이다. 판은 변종을 가르지 않고 **재료 전체**를 찍는다 — 이 값이 답하는 질문은 "어느
    변종이 이 답을 만들었나" 가 아니라 "어떤 프롬프트 코드가 배포돼 있었나" 이고, 변종들은 언제나
    같이 배포되기 때문이다. 어느 변종이었는지는 요청별 신호(`weak_evidence` 등)가 답한다.
    """
    return fingerprint(*ASSEMBLY_MODULES, *_assembly_sources())


def rewrite_prompt_sha() -> str:
    """질의 재작성 프롬프트의 지문 (SPEC-nexus-multi-turn-retrieval §3.2)."""
    from nexus.search.rewrite import SYSTEM_PROMPT, build_user_prompt

    return fingerprint(SYSTEM_PROMPT, _source_of(build_user_prompt))
