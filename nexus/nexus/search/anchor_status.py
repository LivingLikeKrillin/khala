"""근거가 부른 코드 이름이 **지금도 있는가** — 읽는 순간에 나오는 드리프트.

적재는 문서 청크마다 백틱 이름을 코드 심볼에 바인딩해 `doc_code_anchors` 에 남긴다.
그 표는 2026-08-17 까지 **쓰기만 있었다**: 라이브 테넌트 하나에 2,544행이 앉아 있는데
검색·답변·웹 어디도 읽지 않았고, 드리프트를 보려면 사람이 CLI 를 쳐야 했다. 여기가 그
읽기 경로다 — 답변이 문서를 인용할 때 *"이 문단이 부른 이름 7개 중 5개는 지금 코드에
그대로 있고 `X` 는 없다"* 를 같이 낸다.

⛔ **요청 경로에서 심볼을 해소하지 않는다.** `nexus code drift` 는 앵커마다 조회를 한 번씩
   쳐서(2,544 + 거부 3,799) 10분이 걸렸다. 그 모양을 검색 응답에 넣으면 안 된다. 여기서는
   판정에 필요한 것이 **수 둘**뿐이라는 점을 이용해 집합 쿼리 하나로 끝낸다 —
   질의당 쿼리는 앵커가 몇 개든 **한 개**다. (이 리포는 `hybrid_search` 안에 넣은 진단
   COUNT 두 개로 CI 를 40분 매단 적이 있다.)

판정 규칙은 여기 없다. `index/anchors.py:status_from_counts` 가 정본이고 재검사 경로와
같은 함수를 쓴다 — 규칙을 사본으로 두면 CLI 와 답변이 같은 앵커를 다르게 부른다.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import structlog

from nexus import db
from nexus.index.anchors import (
    AMBIGUOUS_NOW,
    CHANGED,
    FRESH,
    ORPHANED,
    status_from_counts,
)

logger = structlog.get_logger(__name__)

#: 한 줄 서술에 이름을 몇 개까지 부를 것인가. 드리프트가 40건인 문단이 프롬프트를 이름으로
#: 채우면 답을 쓸 자리가 줄어든다.
_MAX_NAMES = 6


@dataclass(frozen=True)
class AnchorStatus:
    """문서가 부른 이름 하나와 그 이름의 현재 상태.

    `name` 은 문서에 적힌 토큰이자 해소 키다 — 바인딩이 이름 단독으로 풀리므로 심볼 이름과
    항상 같고, 그래서 둘을 따로 들지 않는다 (§3.3).
    """
    name: str
    status: str


async def statuses_for_chunks(
    tenant: str, chunk_rids: Sequence[str],
) -> dict[str, list[AnchorStatus]]:
    """이 청크들이 부른 이름의 현재 상태. **쿼리 한 번.**

    앵커가 없는 테넌트(평가 팩·`default`)에서는 빈 결과가 돌아오고 호출부는 아무것도 안 한다.

    조회가 실패하면 **빈 결과**다. 앵커는 보강이지 답의 조건이 아니다 — 진단이 진단 대상을
    죽이면 안 된다.
    """
    if not tenant or not chunk_rids:
        return {}

    try:
        rows = await db.fetch_all(
            """
            SELECT a.chunk_rid,
                   a.candidate,
                   count(s.symbol_name)                                  AS n_match,
                   count(*) FILTER (WHERE s.span_hash = a.span_hash)     AS n_same
              FROM doc_code_anchors a
              LEFT JOIN code_symbols s
                     ON s.tenant = a.tenant
                    AND s.repo   = a.repo
                    AND s.symbol_name = a.symbol_name
             WHERE a.tenant = $1
               AND a.chunk_rid = ANY($2::text[])
             GROUP BY a.chunk_rid, a.candidate, a.span_hash
             ORDER BY a.chunk_rid, a.candidate
            """,
            tenant, list(chunk_rids),
        )
    except Exception as e:  # noqa: BLE001 — 보강 실패가 답변을 죽이지 않는다
        logger.warning("anchor_status_lookup_failed", tenant=tenant, error=str(e))
        return {}

    out: dict[str, list[AnchorStatus]] = {}
    for r in rows:
        out.setdefault(r["chunk_rid"], []).append(
            AnchorStatus(r["candidate"], status_from_counts(r["n_match"], r["n_same"])))
    return out


def summarize(anchors: Sequence[AnchorStatus]) -> dict | None:
    """응답에 실리는 모양. **수는 전부 세고 이름은 어긋난 것만** 낸다.

    fresh 20개를 나열하면 아무도 안 읽고, 분모를 빼면 "1개 없어짐" 이 1/1 인지 1/40 인지
    모른다 — 그 둘은 다른 이야기다.
    """
    if not anchors:
        return None
    return {
        "total": len(anchors),
        "fresh": sum(1 for a in anchors if a.status == FRESH),
        "changed": [a.name for a in anchors if a.status == CHANGED],
        "orphaned": [a.name for a in anchors if a.status == ORPHANED],
        "ambiguous_now": [a.name for a in anchors if a.status == AMBIGUOUS_NOW],
    }


def _names(names: list[str]) -> str:
    head = ", ".join(f"`{n}`" for n in names[:_MAX_NAMES])
    rest = len(names) - _MAX_NAMES
    return f"{head} 외 {rest}개" if rest > 0 else head


def describe(anchors: Sequence[AnchorStatus]) -> str:
    """프롬프트에 들어가는 한 줄. 앵커가 없으면 빈 문자열이다.

    **빈 문자열이 중요하다.** 앵커 없는 테넌트의 프롬프트는 오늘과 바이트 단위로 같아야
    한다 — 평가 팩이 거기서 돌고, 한 줄이 들어가는 순간 지금까지의 점수와 비교가 끊긴다.
    """
    summary = summarize(anchors)
    if summary is None:
        return ""

    parts = [f"이 문단이 부른 코드 이름 {summary['total']}개 중 "
             f"{summary['fresh']}개는 현재 코드에 그대로 있음"]
    if summary["changed"]:
        parts.append(f"내용이 바뀜 {len(summary['changed'])}개({_names(summary['changed'])})")
    if summary["orphaned"]:
        parts.append(f"코드에 없음 {len(summary['orphaned'])}개({_names(summary['orphaned'])})")
    if summary["ambiguous_now"]:
        parts.append(
            f"같은 이름이 여럿이 됨 {len(summary['ambiguous_now'])}개"
            f"({_names(summary['ambiguous_now'])})")
    return "코드 앵커: " + " · ".join(parts)
