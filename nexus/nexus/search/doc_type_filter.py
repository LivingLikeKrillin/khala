"""호출자가 **이 질의에서는 안 보고 싶다**고 말한 문서 종류를 후보에서 뺀다.

⛔ **이것은 보안 경계가 아니다.** `auth/scope.py`·`clearance` 와 같은 칸에 두고 읽으면
안 된다. 그 둘은 *읽을 수 있는가*를 정하고 **요청이 넓힐 수 없다**. 이것은 *이번 질의에
쓸모가 있는가*이고 **요청이 정한다.** 둘을 같은 기제로 만들면 언젠가 이 목록을 비우는 것이
권한을 넓히는 일이 된다.

그래서 성질이 하나뿐이다 — **좁히기만 한다.** 빈 목록은 "안 물었다" 이고 오늘과 글자 그대로
같은 SQL 을 낸다. 목록에 든 종류는 후보에서 빠지고, 목록에 없는 종류는 어떤 경우에도 더
들어오지 않는다.

**왜 `top_k` 를 자른 뒤가 아니라 후보 단계인가 (실측 2026-09-20).** `picasso` 코퍼스에서
사건 분류 질의를 여섯 모양으로 돌려 보니, 3,506줄짜리 설계 일지 한 편이 **상위 20 중
5~7 자리**를 매번 차지했다. 뒤에서 걸러 내면 그 자리는 빈 채로 남는다 — 예산을 이미
쓴 뒤다. 앞에서 빼야 그만큼 다른 문서가 올라온다.

⚠ **이것으로 랭킹 문제를 고치지 마라.** 자리를 비우는 것과 맞는 문서를 올리는 것은 다른
일이다. 설명 계층이 그 구분을 먼저 적었고(*"②만 하면 자리는 비지만 맞는 문서는 여전히
안 온다"*), 맞았다.
"""

from __future__ import annotations

from collections.abc import Sequence

#: 목록이 받을 수 있는 최대 길이. 종류는 `ingest/classifier.py` 가 매기고 손에 꼽는다 —
#: 그보다 긴 목록이 오면 호출자가 종류가 아닌 무언가를 넣고 있다는 뜻이다.
MAX_EXCLUDED = 32


def normalize_doc_types(values: Sequence[str] | None) -> tuple[str, ...]:
    """들어온 목록 → 중복·공백 없는 튜플. 순서는 **처음 나온 순서**를 지킨다.

    순서를 지키는 이유는 SQL 이 아니라 **기록**이다. 이 값이 그대로 로그와 응답에 나가는데,
    정렬해 버리면 호출자가 보낸 것과 우리가 적은 것이 달라 보인다.

    ⛔ 모르는 종류를 거부하지 않는다. 종류 어휘는 적재기가 정하고 코퍼스마다 다르며,
    거부하면 오타 하나가 질의를 죽인다. 없는 종류를 빼라는 요구는 **아무것도 안 빼는 것**과
    같으므로 해롭지 않다.
    """
    if not values:
        return ()
    seen: dict[str, None] = {}
    for raw in values:
        if not isinstance(raw, str):
            continue
        if (cleaned := raw.strip()) and cleaned not in seen:
            seen[cleaned] = None
    return tuple(seen)[:MAX_EXCLUDED]


def doc_type_exclusion_predicate(column: str, param: int,
                                 excluded: Sequence[str]) -> tuple[str, list[object]]:
    """`(SQL 조각, 바인딩할 값들)`. 조각은 `AND` 로 시작하고, 안 물었으면 빈 문자열이다.

    `column` 은 `documents` 별칭을 포함한 칸 이름(예: `d.doc_type`)이고, `param` 은 이
    조각이 쓸 **첫** 바인딩 번호다 — `tenant_predicate`·`origin_window_predicate` 와
    같은 모양이다. 번호를 호출부가 세게 두면 다리 하나를 고칠 때 다른 하나가 조용히 어긋난다.

    ⛔ **`IS NULL` 을 같이 살린다.** 종류를 모르는 문서는 *어느 종류도 아닌 것*이지
    *빼라고 한 종류*가 아니다. `<> ALL` 만 쓰면 NULL 비교가 `NULL` 이 되어 그 행이
    조용히 사라진다 — 시각 범위가 `IS NULL OR` 를 쓰는 것과 같은 이유이고, 그 자리에서
    이 리포는 이미 한 번 코퍼스를 통째로 잃을 뻔했다.
    """
    kinds = normalize_doc_types(excluded)
    if not kinds:
        return "", []
    return f"AND ({column} IS NULL OR {column} <> ALL(${param}::text[]))", [list(kinds)]
