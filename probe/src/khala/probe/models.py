from dataclasses import dataclass


@dataclass(frozen=True)
class Survivor:
    # NOTE(M1): spec §4의 `surviving_tests`는 여기 없음 — M1은 suite 요약(테스트 개수)을
    # Critic에 out-of-band로 전달(SKILL.md Step 2). per-survivor coverage 매핑은 M2.
    module: str
    lineno: int
    operator: str
    mutation_diff: str

    @property
    def key(self) -> str:
        """안정 키: module:lineno:operator (원장 매칭용, M2에서 사용)."""
        return f"{self.module}:{self.lineno}:{self.operator}"


@dataclass(frozen=True)
class Verdict:
    survivor_key: str
    verdict: str            # "real-gap" | "equivalent" | "low-value"
    rationale: str
    suggested_test_intent: str | None = None
