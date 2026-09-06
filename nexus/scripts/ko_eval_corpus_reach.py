"""이 라벨이 **지금 묻는 코퍼스에서** 답해질 수 있는가 — 결정론, LLM 0회.

⛔ **왜 생겼나 (실측 2026-09-05).** `synthesis-recency` 4건이 전부 `귀속=upstream`(요구한 사실이
근거에 하나도 없음)으로 나왔고, 나는 그것을 *"코퍼스에 답이 없다"* 로 읽어 `OPEN.md` 에 항목까지
올렸다. **틀렸다.** 요구한 사실은 전부 코퍼스에 있었다 — `design_docs` 에. 라벨 파일은 자기가 어느
테넌트에서 저술됐는지 **적지 않고**, 러너 기본값은 `default` 다. 테넌트를 바꿔 다시 돌리니 곧바로
통과했다.

`answer_fact_probe.py` 는 2026-08-31 에 같은 사고를 이미 주석으로 적어 두었다 — *"컷오버 뒤
하니스가 `default` 하나만 물어서 설계 라벨이 떨어졌고, 나는 그것을 제품 회귀로 읽을 뻔했다."*
**주석은 사람이 읽어야 작동한다.** 그래서 검사로 옮긴다.

**문턱을 만들지 않는다.** 몇 %가 도달 불가면 멈출지는 지어낸 수가 되고, 이 리포는 그런 수를
이미 여러 번 인용당했다. 멈추는 것은 **퇴화 조건 하나**뿐이다 — 요구 사실이 있는 라벨이
**하나도** 코퍼스에 닿지 못할 때. 그때는 측정이 아니라 겨냥이 틀린 것이다. 일부만 못 닿으면
멈추지 않고 **그 라벨을 이름으로 부른다** — 진짜 문서 부재(FP1)일 수 있고, 그건 사람이 판정한다.
"""

from __future__ import annotations

from collections.abc import Sequence

#: `ILIKE` 의 와일드카드. 라벨의 요구 문자열에는 식별자가 흔하고(`crew_partyroom_id_user_id_IDX`),
#: `_` 는 **아무 글자 하나**다 — 안 막으면 없는 것이 있다고 읽힌다. 검사가 관대해지는 방향이라
#: 조용하다: 도달 불가를 도달 가능으로 세고, 그러면 이 파일이 막으려는 그 사고를 그대로 통과시킨다.
def escape_like(needle: str) -> str:
    r"""`\`, `%`, `_` 를 막는다. SQL 쪽은 `ESCAPE '\'` 로 받는다."""
    return needle.replace("\\", "\\\\").replace("%", r"\%").replace("_", r"\_")


_SQL = r"""
SELECT n.needle
FROM unnest($1::text[]) AS n(needle)
WHERE EXISTS (
    SELECT 1 FROM chunks c
    WHERE c.tenant = ANY($2::text[])
      AND c.status = 'active'
      AND c.chunk_text ILIKE '%' || n.needle || '%' ESCAPE '\'
)
"""


async def needles_in_corpus(needles: Sequence[str], tenants: Sequence[str], pool) -> set[str]:
    """이 문자열들 중 **어느 것이 코퍼스에 실재하는가.** 한 번의 왕복으로 전부 본다.

    ⚠ 본문 부분일치다 — 청크 어딘가에 그 글자열이 있는지만 본다. 검색이 그 청크를 물어올지는
    보지 않는다. 그것이 이 검사의 **전부**이고, 그래서 값이 있다: 못 닿은 이유가 *코퍼스에
    없어서*인지 *검색이 못 물어서*인지를 가른다.
    """
    if not needles or not tenants:
        return set()
    escaped = {escape_like(n): n for n in needles if n}
    if not escaped:
        return set()
    rows = await pool.fetch(_SQL, list(escaped), list(tenants))
    return {escaped[r["needle"]] for r in rows}


def groups_reached(groups: list[list[str]], found: set[str]) -> list[bool]:
    """묶음별로 — 후보 중 **하나라도** 코퍼스에 있으면 그 묶음은 닿는다 (`must_contain` 규칙과 같다)."""
    return [any(alt in found for alt in group) for group in groups]


def aiming_is_wrong(reach: list[list[bool]]) -> bool:
    """**퇴화 조건**: 요구 사실이 있는 라벨이 하나도 코퍼스에 닿지 못한다.

    비율이 아니라 전부/전무다. 이 상태의 실행은 시스템이 아니라 **겨냥**을 측정한다.
    요구 사실이 없는 라벨(대조군 등)은 세지 않는다 — 그것은 닿을 것이 원래 없다.
    """
    scored = [r for r in reach if r]
    return bool(scored) and not any(any(r) for r in scored)


def unreachable_ids(ids: Sequence[str], reach: list[list[bool]]) -> list[str]:
    """요구 사실이 **하나도** 코퍼스에 없는 라벨의 id. 멈추지는 않는다 — 이름을 부른다."""
    return [qid for qid, r in zip(ids, reach) if r and not any(r)]
