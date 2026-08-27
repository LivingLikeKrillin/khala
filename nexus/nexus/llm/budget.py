"""답변 서술 비용을 **쓰기 전에** 재는 추정기.

`providers.llm.compute_cost` 는 *이미 일어난* 호출의 비용을 낸다 — 토큰이 없으면 추정하지 않고
`None` 을 돌려준다. 그 규율은 옳지만, 그래서 **아직 안 쓴 기능의 예산은 아무도 못 잡는다.**
현재 `search_log` 943건 중 토큰이 있는 행은 **0건**이다(답변 경로 사용이 2건뿐).

여기서 하는 일은 그 빈칸을 메우는 것이고, 두 가지를 지킨다.

* **추정과 실측을 섞지 않는다.** 실측이 있으면 실측을 쓰고, 없을 때만 추정한다. 어느 쪽인지
  결과에 적는다 — `compute_cost` 가 `None` 으로 지키려던 성질과 같은 이유다.
* **파라미터는 측정에서 온다.** 스니펫 개수는 `search_log` 실측(평균 9.8·최대 12, 943건),
  길이 상한은 `config.search.snippet_max_chars`, 단가는 `config.llm.pricing`. 손으로 고른
  숫자는 토큰/문자 비율 하나뿐이고, 그것도 왜 그 값인지 아래에 적는다.

**코퍼스가 커져도 답변 1회 비용은 거의 안 는다** — 스니펫 개수와 길이가 상한으로 묶여 있기
때문이다. 늘어나는 것은 문서 수가 아니라 질의 수다. 예산은 그쪽으로 잡아야 한다.
"""

from __future__ import annotations

from dataclasses import dataclass

# 한국어 기술 문서의 문자→토큰 비율. 순한글은 글자당 ~1토큰이지만 실제 문서는 라틴 식별자·공백·
# 마크다운이 섞여 훨씬 적게 든다(KOREAN_SEARCH_QUALITY §3.2 가 같은 착오로 20배 틀린 적이 있다).
# 보수적으로 낮게(=토큰 많게) 잡는다: 3.5 글자/토큰.
CHARS_PER_TOKEN = 3.5

# 시스템 프롬프트 + 인용 규칙 + 질의. `llm/prompts.py` 가 커지면 여기도 커진다.
FIXED_PROMPT_TOKENS = 800

# 출력 상한이 아니라 관측되는 전형값. 상한(max_tokens)으로 잡으면 예산이 몇 배 부풀어
# 아무도 안 믿게 된다.
TYPICAL_OUTPUT_TOKENS = 450


@dataclass
class Estimate:
    input_tokens: int
    output_tokens: int
    cost_per_answer_usd: float | None
    basis: str                      # "measured" | "estimated"
    model: str
    note: str = ""

    def monthly(self, answers_per_month: int) -> float | None:
        if self.cost_per_answer_usd is None:
            return None
        return self.cost_per_answer_usd * answers_per_month


def estimate_answer_tokens(n_snippets: float, snippet_max_chars: int) -> tuple[int, int]:
    """한 번의 답변이 태우는 (입력, 출력) 토큰.

    스니펫은 상한 길이로 가정한다 — 실제로는 더 짧은 것이 섞이므로 이 값은 **상한 쪽**이다.
    """
    snippet_tokens = n_snippets * (snippet_max_chars / CHARS_PER_TOKEN)
    return int(FIXED_PROMPT_TOKENS + snippet_tokens), TYPICAL_OUTPUT_TOKENS


def estimate_cost(
    *,
    model: str,
    pricing: dict,
    n_snippets: float,
    snippet_max_chars: int,
    measured: tuple[float, float] | None = None,
) -> Estimate:
    """답변 1회 비용. `measured=(평균 입력토큰, 평균 출력토큰)` 이 있으면 그것을 쓴다."""
    from nexus.providers.llm import compute_cost

    if measured is not None:
        in_tok, out_tok = int(measured[0]), int(measured[1])
        basis, note = "measured", "search_log 의 실제 토큰 평균"
    else:
        in_tok, out_tok = estimate_answer_tokens(n_snippets, snippet_max_chars)
        basis = "estimated"
        note = (f"스니펫 {n_snippets:g}개 × 최대 {snippet_max_chars}자 ÷ {CHARS_PER_TOKEN}자/토큰 "
                f"+ 고정 {FIXED_PROMPT_TOKENS} — 실사용 기록이 없어 추정")

    cost = compute_cost(in_tok, out_tok, model, pricing)
    if cost is None:
        note += f" · 단가표에 {model} 이 없어 비용은 미상"
    return Estimate(input_tokens=in_tok, output_tokens=out_tok, cost_per_answer_usd=cost,
                    basis=basis, model=model, note=note)


async def measured_averages(con) -> tuple[float, float] | None:
    """`search_log` 에 토큰이 기록된 행들의 평균. 없으면 None — **0 으로 채우지 않는다.**"""
    row = await con.fetchrow(
        "SELECT avg(prompt_tokens)::float AS i, avg(completion_tokens)::float AS o, "
        "       count(prompt_tokens) AS n FROM search_log")
    if not row or not row["n"] or row["i"] is None:
        return None
    return float(row["i"]), float(row["o"])
