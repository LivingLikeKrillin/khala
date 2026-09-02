"""읽기 범위를 SQL 술어 하나로 — **12곳이 같은 함수를 쓴다.**

⛔ **왜 함수인가 (SPEC-nexus-tenant-read-scope §1.2).** `effective_read_scope` 가 목록을
반환하면 그 값을 받는 검색 읽기 경로의 술어가 **전부** 바뀌어야 한다. 한 곳이라도 스칼라로
남으면 조용히 `tenants[0]` 으로 강제되거나 타입에서 깨진다 — 비평(3R I-004)이 잡은 자리다.
그래서 술어를 **한 함수**로 만든다. 새 읽기 경로가 생기면 이것을 부른다.

⛔ **이 자리에 *"안 부르면 검사가 잡는다"* 고 적혀 있었고, 그런 검사는 없었다** (실측
2026-09-02). `test_tenant_read_scope.py` 는 이 함수 자체를 시험할 뿐 부르는 쪽을 세지
않는다. 그 사이 `section_fill` 이 범위를 `= $n` 에 그대로 묶고 있었고, 읽기 범위가 튜플이 된
2026-08-31 부터 **모든 HTTP 답변 요청에서** 절 채움과 짝 확장이 예외로 죽었다 — 부르는 쪽이
보강 실패를 삼키므로 사용자에게도 검사에도 안 보였다.

지금 부르는 쪽을 보는 검사는 `tests/test_read_scope_reaches_every_enrichment.py` 하나다.
그것은 이름을 세지 않고 **답변 경로를 세 가지 범위 모양으로 한 번씩 돌려**, 보강이 조용히
죽었는지를 로그와 프롬프트 본문으로 본다. 새 보강은 그 검사에 저절로 든다.

⚠ **원소 하나면 스칼라 술어를 그대로 낸다.** `= $n` 과 `= ANY($n)` 은 계획이 달라질 수 있고
(복합 인덱스 사용·행수 추정), 라이브 코퍼스는 테넌트당 수천 청크다. 목록 미설정 principal 의
지연이 바뀌면 그것은 회귀다 (3R I-012, SPEC §5 C-5). 배열 경로는 검사로만 돈다 — U1 에서는
원소 둘 이상이 기동에서 막히기 때문이다.
"""

from __future__ import annotations

from collections.abc import Sequence


def normalize_scope(tenant: str | Sequence[str] | None) -> tuple[str, ...]:
    """문자열 하나든 목록이든 튜플로. 호출부가 옛 계약(문자열)을 그대로 쓸 수 있게 한다."""
    if tenant is None:
        return ()
    if isinstance(tenant, str):
        return (tenant,)
    return tuple(str(t) for t in tenant)


def tenant_predicate(column: str, param: int,
                     tenant: str | Sequence[str]) -> tuple[str, object]:
    """`(SQL 조각, 바인딩할 값)`.

    원소 하나 → `col = $n` 과 문자열. 여럿 → `col = ANY($n)` 과 리스트.
    """
    scope = normalize_scope(tenant)
    if not scope:
        raise ValueError("읽기 범위가 비었다 — 범위 없는 조회는 격리를 깬다")
    if len(scope) == 1:
        return f"{column} = ${param}", scope[0]
    return f"{column} = ANY(${param})", list(scope)
