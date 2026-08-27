"""평가 실행이 **얼마를 쓰는가**, 그리고 기본적으로 **안 쓰게** 한다.

2026-08-13 에 하루치 평가를 유료 API 로 돌렸다. 리포에는 키 없이 도는 브리지가 이미 있었고
(`NEXUS_LLM_PROVIDER=claude-code`, PR #130), 그것을 쓰지 않은 이유는 단 하나 — **컨테이너
기본값이 `anthropic` 이라는 것을 아무도 확인하지 않았다.** 실행기는 자기가 어느 백엔드로
나가는지 한 번도 말하지 않았다.

그리고 그 지출은 **장부에도 없었다.** 하니스는 `generate_answer` 를 직접 부르므로
`record_search` 를 안 타고, 그래서 `search_log` 의 비용 컬럼이 가장 많이 쓴 경로를 못 본다.

두 가지를 여기서 고친다:

1. **기본은 무료다.** 유료 백엔드로 도는 평가 실행은 `--paid` 없이는 **거절**된다.
   env 한 줄이 바뀌었을 때 조용히 유료로 새지 않게 하는 것이 목적이다.
2. **쓴 만큼 센다.** 실행이 끝나면 호출 수와 달러를 스스로 보고하고 리포트에 남긴다.

**평가 지출을 `search_log` 에 넣지 않는다.** 넣으면 `budget.py::measured_averages` 의
"답변 1회 비용" 이 평가 트래픽으로 오염된다 — U4 가 재작성 비용을 별도 칸으로 뺀 것과 같은
이유다. 평가는 자기 리포트에서 자기 비용을 말한다.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

#: 무료로 도는 백엔드(로컬 브리지). 이 목록 밖은 전부 "돈이 나간다" 로 친다 — 모르는 백엔드를
#: 무료로 가정하면, 새 백엔드가 추가되는 날 조용히 과금된다.
FREE_BACKENDS = ("_ClaudeCodeBackend",)


def backend_name(llm) -> str:
    return type(getattr(llm, "_backend", llm)).__name__


def is_free(llm) -> bool:
    return backend_name(llm) in FREE_BACKENDS


def require_free(llm, *, allow_paid: bool = False, what: str = "이 실행") -> None:
    """유료 백엔드면 거절한다 — `--paid` 를 명시하지 않는 한.

    **거절이 기본인 이유**: 잊는 쪽이 비싸다. 브리지를 켜는 것을 잊으면 손해는 시간이고,
    유료로 도는 것을 잊으면 손해는 돈이다.
    """
    name, model = backend_name(llm), getattr(llm, "model", "?")
    if is_free(llm):
        print(f"  LLM 백엔드: {name} (무료 브리지) · model={model}")
        return
    if allow_paid:
        print(f"  ⚠ LLM 백엔드: {name} — **유료 API 로 나간다** (--paid 로 명시함) · model={model}")
        return
    raise SystemExit(
        f"✗ {what} 은 유료 백엔드({name})로 나간다 — 거절한다.\n"
        "  개발·평가는 키 없이 도는 브리지로 돌린다:\n"
        "    호스트:   task llm-bridge   (NEXUS_LLM_BRIDGE_TOKEN 필요)\n"
        "    nexus/.env: NEXUS_LLM_PROVIDER=claude-code\n"
        "                NEXUS_LLM_BRIDGE_URL=http://host.docker.internal:8900\n"
        "                NEXUS_LLM_BRIDGE_TOKEN=<브리지와 같은 값>\n"
        "  프로덕션 백엔드로 측정해야 하는 실행이면 --paid 를 명시하라(그리고 비용을 예상하라).")


@dataclass
class Spend:
    """이 실행이 쓴 것. **호출 수는 언제나, 달러는 값이 있을 때만.**

    브리지는 토큰을 안 돌려주므로 `usd` 가 0 으로 남는다 — 그것이 "무료였다" 의 정직한 표현이고,
    0 을 "쟀는데 공짜" 로 오해하지 않도록 `priced` 를 따로 센다.
    """
    calls: int = 0
    priced: int = 0
    usd: float = 0.0
    by_kind: dict[str, int] = field(default_factory=dict)

    def add(self, usage, *, kind: str = "answer") -> None:
        """`Usage`(또는 그 dict) 하나를 더한다. `None` 도 호출로 센다 — 호출은 일어났다."""
        self.calls += 1
        self.by_kind[kind] = self.by_kind.get(kind, 0) + 1
        cost = None
        if usage is not None:
            cost = usage.get("cost_usd") if isinstance(usage, dict) else getattr(
                usage, "cost_usd", None)
        if cost:
            self.priced += 1
            self.usd += float(cost)

    def summary(self) -> str:
        kinds = " · ".join(f"{k} {n}" for k, n in sorted(self.by_kind.items()))
        if not self.priced:
            return f"LLM 호출 {self.calls}회 ({kinds}) — 가격 정보 없음(무료 백엔드)"
        return f"LLM 호출 {self.calls}회 ({kinds}) · 과금 {self.priced}회 · **${self.usd:.4f}**"

    def as_dict(self) -> dict:
        return {"calls": self.calls, "priced_calls": self.priced,
                "usd": round(self.usd, 6), "by_kind": dict(self.by_kind)}


def paid_flag_help() -> str:
    """`--paid` 인자의 설명문. 스크립트마다 다시 쓰면 문구가 갈라진다."""
    return ("유료 API 백엔드를 허용한다. 기본은 거절 — 개발·평가는 키 없이 도는 브리지로 돈다 "
            f"(NEXUS_LLM_PROVIDER=claude-code). 현재 env: "
            f"{os.getenv('NEXUS_LLM_PROVIDER') or '(미설정 → anthropic)'}")
