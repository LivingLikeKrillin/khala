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

from nexus.search.scope_sql import tenant_predicate

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


@dataclass(frozen=True)
class DeletedMention:
    """문서가 부르는데 **지워진** 이름 (마이그레이션 029).

    앵커가 아니다 — 바인딩된 적이 없다(스캔 당시 코드에 없었으니까). 그래서 앵커 분모에
    섞지 않는다: 그 분모는 "이 문단이 코드에 걸어 둔 참조" 를 세고, 이쪽은 "걸 곳이 사라진
    참조" 다. 둘을 한 수로 합치면 어느 쪽도 못 읽는다.

    `subject` 가 실린 이유는 **왜 지웠는지가 곧 처방**이기 때문이다.
    """
    name: str
    date: str
    commit: str
    subject: str


@dataclass(frozen=True)
class ScanBasis:
    """이 판정이 **무엇과 비교한 것인가**.

    ⛔ **왜 있나 (실측 2026-09-11).** 이 경로는 `code_symbols` 와 대조해 fresh·changed 를
    가르는데, 그 표가 마지막으로 채워진 시점을 아무 데도 안 실었다. 그래서 표면은 언제나
    *"현재 코드에 그대로 있습니다"* 라고 적었다. 그런데 라이브에서 스캔은 리포당 **한 번**만
    돌아 있었다(`code-src` 2026-08-18 · khala 2026-08-16, `scan_commit` 각 1개). 앵커 5,440건이
    전부 fresh 로 나온 것은 코드가 안 바뀌어서가 아니라 **비교 대상이 안 움직여서**였다.

    ⭐ 같은 리포가 이 규율을 이미 적어 뒀다 — `nexus code drift` 는 작업 트리가 스캔 커밋이
    아니면 `unknown` 을 내고 드리프트를 보고하지 않는다("모름은 정답이다"). 요청 경로는 그
    확인을 할 수 없다(배포된 코드가 어디 있는지 모른다). 그래서 여기서 하는 일은 **판정을
    멈추는 것이 아니라 판정의 기준을 같이 내보내는 것**이다.
    """
    commit: str
    at: str          # YYYY-MM-DD. 시각까지는 필요 없고, 날짜는 사람이 바로 읽는다


@dataclass(frozen=True)
class ChunkAnchors:
    """한 청크가 부른 코드 이름들의 읽기 — 앵커 상태와 지워진 이름.

    `scan` 은 앵커 판정이 무엇과 비교한 것인지다. 앵커가 없거나 스캔 기록이 없으면 `None`
    이고, 그때 표면은 기준을 **모른다고** 말해야 한다.
    """
    anchors: list[AnchorStatus]
    deleted: list[DeletedMention]
    scan: ScanBasis | None = None


async def statuses_for_chunks(
    tenant: str | Sequence[str], chunk_rids: Sequence[str],
) -> dict[str, ChunkAnchors]:
    """이 청크들이 부른 이름의 현재 상태. **쿼리 한 번.**

    두 사실을 한 번에 받는다 — 바인딩된 앵커의 상태, 그리고 바인딩되지 못한 이름 중
    **git 이 지워졌다고 아는 것**. `UNION ALL` 로 묶는 이유는 하나다: 표면마다 쿼리를 더하면
    앵커가 몇 개든 한 개라던 약속이 조용히 두 개, 세 개가 된다.

    앵커가 없는 테넌트(평가 팩·`default`)에서는 빈 결과가 돌아오고 호출부는 아무것도 안 한다.

    조회가 실패하면 **빈 결과**다. 앵커는 보강이지 답의 조건이 아니다 — 진단이 진단 대상을
    죽이면 안 된다.
    """
    if not tenant or not chunk_rids:
        return {}

    _a_pred, _val = tenant_predicate("a.tenant", 1, tenant)
    _r_pred, _ = tenant_predicate("r.tenant", 1, tenant)
    try:
        rows = await db.fetch_all(
            f"""
            SELECT a.chunk_rid,
                   a.candidate                                           AS name,
                   'anchor'                                              AS kind,
                   count(s.symbol_name)                                  AS n_match,
                   count(*) FILTER (WHERE s.span_hash = a.span_hash)     AS n_same,
                   ''::text AS deleted_date, ''::text AS deleted_commit, ''::text AS subject,
                   -- 판정의 **기준**. 이 두 칸이 없으면 표면이 "현재 코드" 라고 단정하게 된다
                   -- (`ScanBasis` 머리말). 리포당 한 행짜리 조인이라 쿼리는 여전히 한 개다.
                   coalesce(sc.scan_commit, '')                          AS scan_commit,
                   coalesce(to_char(sc.scanned_at, 'YYYY-MM-DD'), '')    AS scan_at
              FROM doc_code_anchors a
              LEFT JOIN code_symbols s
                     ON s.tenant = a.tenant
                    AND s.repo   = a.repo
                    AND s.symbol_name = a.symbol_name
              -- `code_scans` 는 (tenant, repo) 가 기본키라 리포당 한 행이다. 심볼 표를
              -- 훑어 최신 스캔을 고르지 않는다 — 같은 사실을 두 곳에서 구하면 갈린다.
              LEFT JOIN code_scans sc
                     ON sc.tenant = a.tenant
                    AND sc.repo   = a.repo
             WHERE {_a_pred}
               AND a.chunk_rid = ANY($2::text[])
             GROUP BY a.chunk_rid, a.candidate, a.span_hash, sc.scan_commit, sc.scanned_at

             UNION ALL

            SELECT r.chunk_rid,
                   r.candidate, 'deleted', 0, 0,
                   d.deleted_date, d.deleted_commit, d.subject,
                   ''::text, ''::text
              FROM doc_code_refusals r
              JOIN code_deleted_symbols d
                     ON d.tenant = r.tenant
                    AND d.repo   = r.repo
                    AND d.symbol_name = r.candidate
             WHERE {_r_pred}
               AND r.chunk_rid = ANY($2::text[])
               -- `ambiguous` 는 여기 오지 않는다. 동명이 여럿이라 못 고른 것이지 사라진 것이
               -- 아니고, 그것을 삭제로 부르면 목록이 거짓을 말한다.
               AND r.reason = 'unresolved'

             ORDER BY 1, 3, 2
            """,
            _val, list(chunk_rids),
        )
    except Exception as e:  # noqa: BLE001 — 보강 실패가 답변을 죽이지 않는다
        logger.warning("anchor_status_lookup_failed", tenant=tenant, error=str(e))
        return {}

    anchors: dict[str, list[AnchorStatus]] = {}
    deleted: dict[str, list[DeletedMention]] = {}
    scans: dict[str, ScanBasis] = {}
    for r in rows:
        rid = r["chunk_rid"]
        if r["kind"] == "deleted":
            deleted.setdefault(rid, []).append(DeletedMention(
                r["name"], r["deleted_date"], r["deleted_commit"], r["subject"]))
        else:
            anchors.setdefault(rid, []).append(
                AnchorStatus(r["name"], status_from_counts(r["n_match"], r["n_same"])))
            # 한 청크의 앵커가 리포 둘에 걸치면 기준도 둘이다. **오래된 쪽을 택한다** —
            # 표면이 말하는 기준은 이 판정 전체가 서 있는 바닥이어야 하고, 바닥은 가장
            # 낡은 쪽이다. 새 쪽을 적으면 실제보다 최근에 확인한 것처럼 읽힌다.
            if r["scan_at"]:
                prev = scans.get(rid)
                if prev is None or r["scan_at"] < prev.at:
                    scans[rid] = ScanBasis(r["scan_commit"], r["scan_at"])

    return {rid: ChunkAnchors(anchors.get(rid, []), deleted.get(rid, []), scans.get(rid))
            for rid in set(anchors) | set(deleted)}


def summarize(anchors: Sequence[AnchorStatus],
              deleted: Sequence[DeletedMention] = (),
              scan: ScanBasis | None = None) -> dict | None:
    """응답에 실리는 모양. **수는 전부 세고 이름은 어긋난 것만** 낸다.

    fresh 20개를 나열하면 아무도 안 읽고, 분모를 빼면 "1개 없어짐" 이 1/1 인지 1/40 인지
    모른다 — 그 둘은 다른 이야기다.

    `deleted` 는 `total` 에 **안 들어간다**. 분모는 바인딩된 참조의 수이고, 지워진 이름은
    바인딩된 적이 없다. 합치면 "7개 중 5개" 가 무엇의 5개인지 아무도 모르게 된다.

    `scan` 은 수가 **무엇과 비교해서 나온 것인지**다(`ScanBasis`). `None` 이면 모른다는
    뜻이고, 표면은 모른다고 말해야 한다. ⚠ 이 키는 `describe` 가 읽지 않는다 — 프롬프트는
    바이트 단위로 같아야 하고 평가 팩이 거기서 돈다(`test_anchor_status_surface.py` 가
    그것을 고정한다).
    """
    if not anchors and not deleted:
        return None
    return {
        "total": len(anchors),
        "fresh": sum(1 for a in anchors if a.status == FRESH),
        "changed": [a.name for a in anchors if a.status == CHANGED],
        "orphaned": [a.name for a in anchors if a.status == ORPHANED],
        "ambiguous_now": [a.name for a in anchors if a.status == AMBIGUOUS_NOW],
        # 날짜와 사유가 같이 간다 — 이름만으로는 문서를 고칠 수 없다.
        "deleted": [{"name": d.name, "date": d.date,
                     "commit": d.commit, "subject": d.subject} for d in deleted],
        "scan": {"commit": scan.commit, "at": scan.at} if scan else None,
    }


def _names(names: list[str]) -> str:
    head = ", ".join(f"`{n}`" for n in names[:_MAX_NAMES])
    rest = len(names) - _MAX_NAMES
    return f"{head} 외 {rest}개" if rest > 0 else head


def describe(anchors: Sequence[AnchorStatus],
             deleted: Sequence[DeletedMention] = ()) -> str:
    """프롬프트에 들어가는 한 줄. 앵커도 지워진 이름도 없으면 빈 문자열이다.

    **빈 문자열이 중요하다.** 앵커 없는 테넌트의 프롬프트는 오늘과 바이트 단위로 같아야
    한다 — 평가 팩이 거기서 돌고, 한 줄이 들어가는 순간 지금까지의 점수와 비교가 끊긴다.
    """
    summary = summarize(anchors, deleted)
    if summary is None:
        return ""

    parts = []
    if summary["total"]:
        parts.append(f"이 문단이 부른 코드 이름 {summary['total']}개 중 "
                     f"{summary['fresh']}개는 현재 코드에 그대로 있음")
    if summary["changed"]:
        parts.append(f"내용이 바뀜 {len(summary['changed'])}개({_names(summary['changed'])})")
    if summary["orphaned"]:
        parts.append(f"코드에 없음 {len(summary['orphaned'])}개({_names(summary['orphaned'])})")
    if summary["ambiguous_now"]:
        parts.append(
            f"같은 이름이 여럿이 됨 {len(summary['ambiguous_now'])}개"
            f"({_names(summary['ambiguous_now'])})")
    if summary["deleted"]:
        # 날짜까지 말한다. "없다" 는 확인 대상이지만 "2026-02-19 에 지워졌다" 는 처분 대상이다.
        shown = summary["deleted"][:_MAX_NAMES]
        listed = " · ".join(f"`{d['name']}`({d['date']} 삭제)" for d in shown)
        rest = len(summary["deleted"]) - len(shown)
        if rest > 0:
            listed += f" 외 {rest}개"
        parts.append(f"문서가 부르지만 코드에서 지워진 이름 {len(summary['deleted'])}개: {listed}")
    return "코드 앵커: " + " · ".join(parts)
