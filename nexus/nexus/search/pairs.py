"""짝 문서 확장 — **설계와 구현 계획은 같은 일의 두 문서다.**

**왜 있나.** 팀은 한 가지 일을 문서 둘로 쓴다: `specs/<날짜>-<슬러그>-design.md` 와
`plans/<날짜>-<슬러그>.md`. 설계는 *왜* 와 *무엇* 을 갖고, 계획은 *어느 파일* 과 *어떤 순서*
를 갖는다. 그러니 *"무엇을 왜 넣고, 그것을 어떤 과제로 검증하나"* 같은 질문은 **한 문서만으로는
답이 안 된다.** 유사도는 둘을 각각 찾아야 하고, 둘째가 상위에 못 오면 답변은 반쪽이 된다.

**이 관계는 지어내는 것이 아니라 이미 파일 이름에 있다.** 라이브 코퍼스에서 27쌍이 이름만으로
맞는다. LLM 추출도, 판단도 필요 없다 — 그래서 이 리포의 `edges` 가 두 달째 1행인 동안에도
이것은 공짜로 얻을 수 있었다.

**측정 (라벨 4개 × 5회, 근거는 실행군 안에서 동일)**::

    처치 대상 S2   0/5 → 4/5      (짝 문서에만 있는 값이 답변에 선다)
    대조군 S1·R2·R1  5/5 → 5/5    (셋 다 안 떨어짐)
    지연           +3 ms          (검색이 아니라 rid 로 직접 가져온다)
    근거 분량      +26 ~ +134%    ← **이것이 값이다**

근거가 두 배 넘게 느는 경우가 있다. 대조군이 안 떨어진 것은 **이 규모에서** 확인한 것이고,
더 큰 문서 쌍에서도 그런지는 측정하지 않았다. 값이 붙는 곳은 짝이 있는 코퍼스뿐이다 —
정책 문서 테넌트에는 `specs/`·`plans/` 가 없어 이 경로가 아예 안 돈다.

**코드 기본값은 꺼짐**이다(`section_fill`·정정 패스와 같은 이유).
"""

from __future__ import annotations

import re

import structlog

from nexus import db

logger = structlog.get_logger(__name__)

#: 짝을 찾아 볼 상위 히트 수. 넓히면 근거가 그만큼 더 는다.
TOP_HITS = 3

_PREFIX = re.compile(r"^superpowers/(specs|plans)/")
_SUFFIX = re.compile(r"(-design)?\.md$")


def slug_of(source_uri: str) -> str:
    """`design_docs:superpowers/specs/2026-05-09-x-design.md` → `2026-05-09-x`.

    설계와 계획이 **같은 슬러그**로 떨어지는 것이 이 모듈의 전부다.
    """
    tail = (source_uri or "").split(":", 1)[-1]
    return _SUFFIX.sub("", _PREFIX.sub("", tail))


def mates_from(rows: list[dict]) -> dict[str, list[str]]:
    """문서 목록에서 rid → 짝 rid 들. **짝이 정확히 둘일 때만** 잇는다 —
    같은 슬러그로 셋 이상이 붙으면 그것은 짝이 아니라 무리이고, 무리를 통째로 실으면
    근거가 답이 아니라 문서 더미가 된다."""
    by_slug: dict[str, list[str]] = {}
    for r in rows:
        by_slug.setdefault(slug_of(r["source_uri"]), []).append(r["rid"])
    return {rid: [o for o in group if o != rid]
            for group in by_slug.values() if len(group) == 2 for rid in group}


async def paired_chunks(hits, tenant: str, clearance: str, *, exclude_rids=None) -> list[dict]:
    """상위 히트 문서들의 **짝 문서** 청크. 실패는 삼키되 조용하지 않게."""
    if not hits:
        return []
    try:
        rows = await db.fetch_all(
            "SELECT rid, source_uri FROM documents WHERE tenant = $1 AND status = 'active' "
            "AND (source_uri LIKE '%/specs/%' OR source_uri LIKE '%/plans/%')", tenant)
        if not rows:
            return []
        mates = mates_from([dict(r) for r in rows])
        wanted, seen = [], set()
        for h in hits[:TOP_HITS]:
            for m in mates.get(h.doc_rid, []):
                if m not in seen:
                    seen.add(m)
                    wanted.append(m)
        if not wanted:
            return []
        from nexus.search.section_fill import fill_for_docs
        out = await fill_for_docs(tenant, clearance, wanted,
                                  set(exclude_rids or ()) | {h.rid for h in hits})
    except Exception as e:  # noqa: BLE001 — 보강 실패가 검색을 죽이면 안 된다
        logger.warning("pair_expansion_failed", error=str(e))
        return []
    if out:
        logger.info("pair_expansion", docs=len(wanted), added=len(out))
    return out
