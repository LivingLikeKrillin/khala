"""근거 문서에 붙은 **갱신 부채** — 읽는 순간에 알린다.

답변이 근거를 인용할 때, 그 근거 자체에 문제가 있으면 읽는 사람이 알아야 한다. 지금 이 층이
아는 것은 **결정론적으로 저장돼 있는 것**뿐이다:

- **supersede 됨** — 이 문서는 다른 문서로 대체됐다고 사람이 선언했다.
- **제목 중복** — 같은 제목의 활성 문서가 둘 이상이다. 인용이 `[출처: 제목]` 이라 **어느 쪽인지
  가리키지 못한다.** 라이브 정책 코퍼스에서 16건이었다.

⛔ **의미적 모순은 여기서 판정하지 않는다.** "이 문서는 A 라고 하고 저 문서는 B 라고 한다" 를
   기계가 판정하려면 심판 모델이 필요한데, 그 길은 이 리포가 이미 근거를 들어 기각했다
   (DocPrism: 순진한 심판이 함수의 98% 를 플래그하고 정확도는 14%). 모순은 답변자가 **서술**할
   수 있고(서술 규칙 7), 시스템은 그것을 **보증하지 않는다**. 보증할 수 있는 것만 여기 온다.

⛔ 요청 경로에 N+1 을 두지 않는다 — 앵커 상태와 같은 규율이다. 쿼리 하나로 끝낸다.
"""

from __future__ import annotations

from nexus.search.scope_sql import tenant_predicate

from dataclasses import dataclass
from typing import Sequence

import structlog

from nexus import db

logger = structlog.get_logger(__name__)

#: supersede 안 됨을 뜻하는 값. 이 리포의 관례는 NULL 이 아니라 **빈 문자열**이다
#: (`lifecycle.py` 의 unsupersede 가 `superseded_by=''` 로 되돌린다). `IS NOT NULL` 로 읽으면
#: 모든 문서가 대체된 것으로 보인다 — 2026-08-18 에 실제로 그렇게 잘못 읽었다.
_NOT_SUPERSEDED = ""


@dataclass(frozen=True)
class DocDebt:
    """한 근거 문서에 붙은 부채. 없으면 이 객체가 아예 안 만들어진다."""
    doc_rid: str
    title: str
    superseded_by_title: str = ""
    same_title_docs: int = 0
    #: 대체됐다는 **사실**. 제목과 갈라 둔다 — 대체한 문서를 읽을 권한이 없으면 이름은
    #: 못 주지만, *"이 문서는 은퇴했다"* 는 읽는 사람이 볼 수 있는 문서에 대한 사실이다.
    superseded: bool = False


async def debts_for_docs(tenant: str | Sequence[str],
                         clearance: str,
                         doc_rids: Sequence[str]) -> dict[str, DocDebt]:
    """이 근거 문서들에 붙은 부채. **쿼리 한 번.** 실패하면 빈 결과(진단이 답을 죽이지 않는다).

    ⛔ **`clearance` 는 선택이 아니다** (외부 평가 F3, 2026-09-02). 대체 문서를 잇는 조인에
    `tenant` 만 있고 등급·격리·상태 필터가 없어서, **읽을 권한이 없는 문서의 제목이 프롬프트에
    들어갈 수 있었다.** `nexus/CLAUDE.md` 는 *"모든 SELECT 에 정책 필터를 건다. 예외 없음."*
    이라고 적어 두었고 그 예외가 여기였다.

    ⚠ **비어 있으면 조회하지 않는다.** 빈 등급을 "필터 없음" 으로 읽으면 이 함수를 등급 없이
    부르는 자리가 곧 우회로가 된다 — 앵커 조회가 `tenant` 에 대해 쓰는 것과 같은 규율이다.

    ⚠ 라이브 실측(2026-09-02): 누출 조합 **0건**. 다만 재료는 다 있다 — 대체 관계 121 ·
    `RESTRICTED` 17 · 격리 4. 잠복이지 안전이 아니다.
    """
    if not tenant or not clearance or not doc_rids:
        return {}
    try:
        _pred, _val = tenant_predicate("d.tenant", 1, tenant)
        rows = await db.fetch_all(
            f"""
            SELECT d.rid, d.title,
                   (d.superseded_by IS NOT NULL AND d.superseded_by <> '')  AS superseded,
                   coalesce(s.title, '')                                  AS superseded_by_title,
                   (SELECT count(*) FROM documents t
                     WHERE t.tenant = d.tenant AND t.title = d.title
                       AND t.status = 'active' AND t.is_quarantined = false) AS same_title
              FROM documents d
              -- 대체한 문서에도 **같은 네 절**을 건다. 하나라도 빠지면 읽을 권한이 없는
              -- 문서의 제목이 프롬프트로 나간다 (외부 평가 F3).
              LEFT JOIN documents s
                     ON s.rid = d.superseded_by AND s.tenant = d.tenant
                    AND s.classification <= $3::classification_level
                    AND s.is_quarantined = false
                    AND s.status = 'active'
             WHERE {_pred} AND d.rid = ANY($2::text[])
            """,
            _val, list(doc_rids), clearance)
        out: dict[str, DocDebt] = {}
        for r in rows:
            title = r["superseded_by_title"] or ""
            same = int(r["same_title"] or 1)
            is_sup = bool(r["superseded"])
            if not is_sup and same <= 1:
                continue                  # 부채 없음 — 조용한 것이 기본이다
            out[r["rid"]] = DocDebt(r["rid"], r["title"], title, same, is_sup)
        return out
    except Exception as e:  # noqa: BLE001
        # **행 파싱까지 감싼다.** 조회는 성공했는데 모양이 다른 경우가 실제로 있었다(검사가
        # `db.fetch_all` 을 가짜로 바꾸면 이 모듈도 그 가짜를 받는다 — 모듈이 같아서다).
        # 보강이 답변을 죽이지 않는다는 약속은 쿼리에만 걸린 것이 아니다.
        logger.warning("doc_debt_lookup_failed", tenant=tenant, error=str(e))
        return {}


def describe(debts: Sequence[DocDebt]) -> str:
    """프롬프트에 들어가는 한 줄. 부채가 없으면 빈 문자열 — 그때 프롬프트는 오늘과 같다.

    **제목 단위로 접는다.** 제목이 겹치는 문서가 근거에 여럿 들어오면(정확히 그 부채의 정의다)
    같은 문장이 그 수만큼 반복된다 — 실측에서 한 줄이 세 번 나왔다. 접지 않으면 부채를 알리는
    줄이 그 자체로 소음이 된다.
    """
    seen: set[str] = set()
    parts = []
    for d in debts:
        if d.title in seen:
            continue
        seen.add(d.title)
        if d.superseded_by_title:
            parts.append(f"`{d.title}` 은 `{d.superseded_by_title}` 로 대체된 문서다")
        elif d.superseded:
            # 대체한 문서를 읽을 권한이 없다. **이름은 안 주고 사실은 준다** — 은퇴했다는
            # 것은 읽는 사람이 이미 보고 있는 문서에 대한 사실이고, 그것을 감추면 낡은
            # 근거를 낡은 줄 모르고 읽는다 (외부 평가 F3).
            parts.append(f"`{d.title}` 은 대체된 문서다")
        elif d.same_title_docs > 1:
            parts.append(f"`{d.title}` 은 같은 제목의 문서가 {d.same_title_docs}개 있어 "
                         f"인용만으로는 어느 것인지 가리키지 못한다")
    return "문서 부채: " + " · ".join(parts) if parts else ""


def summarize(debts: Sequence[DocDebt]) -> list[dict] | None:
    """응답에 실리는 모양. 표현계층이 배지를 달 수 있을 만큼만."""
    if not debts:
        return None
    return [{"title": d.title, "superseded_by": d.superseded_by_title,
             "same_title_docs": d.same_title_docs} for d in debts]
