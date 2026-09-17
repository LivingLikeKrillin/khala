"""문서 **자신의** 시각으로 검색 범위를 좁힌다 — 그리고 모르는 것을 밖으로 내몰지 않는다.

⛔ **`updated_at` 이 아니다.** 그 칸은 우리 적재 시각이라 재적재하면 모든 문서가 새것이 된다.
`documents.origin_updated_at`(migration 039)이 원본이 말하는 문서 자신의 마지막 수정 시각이고,
*"어제도 같은 일 있었나"* 를 물을 수 있는 유일한 칸이다. `ingest/pipeline.py:origin_updated_at`
가 그 값을 frontmatter 의 `origin_last_edited` 에서 읽는다.

⭐ **NULL 은 "모른다" 이지 "범위 밖" 이 아니다.** 스키마 주석이 그렇게 적어 뒀고, 여기서도
그대로 지킨다 — **시각을 아는 문서만 범위 밖으로 떨군다.** 반대로 만들면(NULL 을 제외) 운영자가
"어제" 로 좁힌 순간 시각을 안 싣는 적재 경로의 문서가 통째로 사라지고, 화면에는 *"없습니다"* 가
뜬다. 있는데 안 보인 것과 없는 것을 구별할 방법이 그 화면에는 없다.

**실측 2026-09-18 (라이브):** `origin_updated_at` 이 채워진 비율이 `default` 248건 중 112건
(45.2%)이고 `design_docs` 243건 중 **0건**이다. 값은 노션 커넥터만 싣는다. 즉 NULL 을 제외하는
설계였다면 설계 문서 코퍼스 전체가 이 필터 아래에서 보이지 않았을 것이다.

그 대신 **몇 건이 시각 미상이었는지 세어 돌려준다**(`SearchResult.n_unknown_origin_time`).
좁혔는데 안 좁혀진 만큼을 호출자가 볼 수 있어야, 좁혔다고 믿고 답을 읽는 일이 없다.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class OriginWindow:
    """문서 자신의 시각에 거는 범위. 둘 다 `None` 이면 **안 물은 것**이다."""

    since: datetime | None = None
    until: datetime | None = None

    @property
    def asked(self) -> bool:
        """범위를 물었는가. 안 물었으면 미상 건수도 세지 않는다 — 0 과 미측정은 다른 사실이다."""
        return self.since is not None or self.until is not None


def origin_window_predicate(column: str, param: int,
                            window: OriginWindow) -> tuple[str, list[object]]:
    """`(SQL 조각, 바인딩할 값들)`. 조각은 `AND` 로 시작하고, 안 물었으면 빈 문자열이다.

    `column` 은 `documents` 별칭을 포함한 칸 이름(예: `d.origin_updated_at`)이고, `param` 은
    이 조각이 쓸 **첫** 바인딩 번호다. 번호를 호출부가 세게 두면 다리 하나를 고칠 때 다른 하나가
    조용히 어긋난다 — `tenant_predicate` 와 같은 이유로 같은 모양을 쓴다.

    각 경계가 `IS NULL OR` 로 감싸인 것이 이 함수의 전부다. 그 두 낱말이 빠지면 설계 문서
    코퍼스가 통째로 사라진다(모듈 독스트링의 실측).
    """
    parts: list[str] = []
    values: list[object] = []
    for bound, op in ((window.since, ">="), (window.until, "<=")):
        if bound is None:
            continue
        parts.append(f"AND ({column} IS NULL OR {column} {op} ${param})")
        values.append(bound)
        param += 1
    return " ".join(parts), values


def count_unknown(origin_times: list[datetime | None], window: OriginWindow) -> int | None:
    """돌려준 근거 중 시각을 모르는 건수. **안 물었으면 `None`** — 세지 않은 것이다.

    `0` 을 돌려주면 "물었고 전부 시각을 안다" 는 뜻이 된다. 안 물은 요청과 그것을 같은 값으로
    내보내면 호출자가 둘을 못 가른다.
    """
    if not window.asked:
        return None
    return sum(1 for t in origin_times if t is None)
