"""가리키기만 하는 절은 **가리킨 절을 데리고 온다** — 같은 문서 안에서.

⛔ **왜 생겼나 (실측 2026-09-22, 설명 층 두 판).** SOP-03 §5 2항이 이렇게 적혀 있다:

    2. §4 의 세 조건을 확인한다.

조각내기가 §5 와 §4 를 갈라 놓으므로 **조각 5 는 혼자 간다.** 받는 쪽은 조건이 없는
포인터를 받고, 조건 셋(품번 동일 · 로트 제약 없음 · 대체 슬롯 선언됨)은 안 온다. 그래서
탐색 줄의 절차 절 인용이 **T0·T2 두 판 다 0/1** 이었다 — 채널을 켜도 안 왔다.

⚠ **문서를 고칠 일이 아니다.** 실제 절차서가 원래 그렇게 쓴다. 원문을 읽는 사람에게는
멀쩡한 문장이고, 깨지는 것은 **조각으로 나뉘는 순간**이다.

## ⭐ 무엇을 하고 무엇을 안 하는지 — 측정해서 정했다

라이브 코퍼스(`picasso`·`narrator`) 실측:

    §N 표기      660/2415 조각(27%)     ← 이 표기 하나다
    N절 표기     1건
    N장 표기     2건

    § 참조 388건 중 **같은 문서 안에서 풀리는 것 24건(6%)**
    참조를 가진 조각 139개 · 조각당 중앙값 2 · 최대 45

⛔ **94% 는 다른 문서의 절을 가리킨다**(`limits.md §15.183`, `설계 문서 §6.4`, `ADR 9 §4` …).
그것을 따라가는 것은 **다른 기능**이다 — 문서 이름을 풀어야 하고, 통째로 딸려 오는 문서의
크기를 감당해야 하고, 오해석의 대가가 훨씬 크다. 여기서는 **안 한다.**

⇒ 이 모듈이 덮는 것은 24건이다. 좁다. 그런데 **관측된 실패가 그 안에 있고**(SOP-03 이 4건),
같은 문서 안이라 **풀리는 범위가 그 문서의 절 수로 닫힌다.**

## 절을 **고르지 않는다**

`section_fill.fill_for_sections` 의 규율을 그대로 쓴다 — *"여기서 절을 고르지 않는다.
검색이 이미 고른 절을 쓴다."* 여기서도 고르는 것은 이 코드가 아니라 **문서 자신**이다:
본문이 `§4` 라고 적었으므로 §4 가 온다. 우리가 관련 있어 보이는 절을 추측하는 것이 아니다.
"""

from __future__ import annotations

import re
from collections.abc import Sequence

import structlog

from nexus import db
from nexus.search.scope_sql import tenant_predicate

logger = structlog.get_logger(__name__)

#: 참조 표기. 실측으로 고른 **하나**다(위 머리말). 점 있는 번호(`§15.183`)도 받는다 —
#: 같은 문서 안에 그런 절이 있으면 풀리고, 없으면 안 풀린다. 표기를 늘리지 않는 이유는
#: `N절`·`N장` 이 합쳐 3건이기 때문이다. **늘리려면 먼저 세라.**
REF = re.compile(r"§\s*(\d+(?:\.\d+)*)")

#: 절 경로의 마지막 마디가 제 번호를 말하는 모양 — `4. 대체 슬롯은 기본이 아니다` ·
#: `6.1 SOURCE_MISSING 은 …`.
#:
#: ⛔ **번호 뒤를 `[.\s]` 로 받는 것이 핵심이다.** 앞 판은 `\.` 만 받았는데, 그러면
#: `6.1 제목` 에서 정규식이 **`6.1` 을 잡았다가 되돌아가 `6` + 마침표**로 맞춘다 —
#: 하위 절이 **제 부모 절 번호로 앉고**, `§6` 참조가 `6.1` 을 데려온다. 내 검사가
#: 출하 전에 잡았다(2026-09-23).
_LEADING_NUMBER = re.compile(r"^(\d+(?:\.\d+)*)[.\s]")

#: 참조를 읽어 볼 상위 히트 수. `pairs.py` 와 같은 값이다 — 넓히면 근거가 그만큼 는다.
TOP_HITS = 3

#: 한 판에서 데려올 절 수의 상한.
#:
#: ⛔ **상한이 필요한 이유가 실측에 있다.** 참조가 **45개**인 조각이 있다. 같은 문서 안이라
#: 다 풀리지는 않지만, 상한이 없으면 **한 조각이 그 문서를 통째로 데려올 수** 있다.
#: 중앙값이 2 이므로 이 값은 보통의 경우에 안 닿는다.
MAX_SECTIONS = 5


def referenced_numbers(text: str | None) -> list[str]:
    """본문이 가리킨 절 번호들. **처음 나온 순서**, 중복 없음.

    순서를 지키는 이유는 상한 때문이다 — 잘릴 때 잘리는 것이 **뒤에 적힌 참조**여야, 문서가
    먼저 가리킨 것이 먼저 온다.
    """
    seen: dict[str, None] = {}
    for m in REF.finditer(text or ""):
        seen.setdefault(m.group(1), None)
    return list(seen)


def section_number(section_path: str | None) -> str | None:
    """절 경로 → 그 절의 번호. 번호로 시작하지 않으면 `None`."""
    last = (section_path or "").split(" > ")[-1].strip()
    m = _LEADING_NUMBER.match(last)
    return m.group(1) if m else None


async def referenced_chunks(hits, tenant: str | Sequence[str], clearance: str, *,
                            exclude_rids=None, failed: list | None = None) -> list[dict]:
    """상위 히트가 **가리킨 절**의 청크. 실패는 삼키되 조용하지 않게.

    ⚠ **문서 종류 제외를 따로 안 건다.** 데려오는 절은 **히트가 앉은 바로 그 문서**의 것이고,
    그 문서는 이미 바깥 질의의 종류 필터를 통과했다. `pairs.py` 는 히트 **밖의** 문서를
    데려오므로 거기서는 필요했다 — 여기서는 표현 자체가 불가능하다.
    """
    if not hits:
        return []
    wanted: dict[str, list[str]] = {}          # doc_rid → 가리킨 번호들
    for h in hits[:TOP_HITS]:
        nums = referenced_numbers(getattr(h, "chunk_text", None))
        if nums:
            wanted.setdefault(h.doc_rid, []).extend(nums)
    if not wanted:
        return []

    try:
        tenant_pred, tenant_val = tenant_predicate("c.tenant", 2, tenant)
        rows = await db.fetch_all(
            f"SELECT DISTINCT c.doc_rid, c.section_path FROM chunks c "
            f"WHERE c.doc_rid = ANY($1::text[]) AND {tenant_pred} "
            "AND c.status = 'active' AND c.is_quarantined = false",
            list(wanted), tenant_val)

        #: 같은 문서 안에서 번호 → 절 경로. 한 번호에 절이 둘이면 **안 고른다** — 어느
        #: 쪽인지 모르는 채로 하나를 집으면 문서가 안 가리킨 절을 데려온다.
        by_doc: dict[str, dict[str, list[str]]] = {}
        for r in rows:
            n = section_number(r["section_path"])
            if n:
                by_doc.setdefault(r["doc_rid"], {}).setdefault(n, []).append(r["section_path"])

        sections: list[tuple[str, str]] = []
        for doc, nums in wanted.items():
            paths = by_doc.get(doc, {})
            for n in nums:
                cand = paths.get(n) or []
                if len(cand) == 1 and (doc, cand[0]) not in sections:
                    sections.append((doc, cand[0]))
        if not sections:
            return []
        if len(sections) > MAX_SECTIONS:
            logger.info("crossref_capped", asked=len(sections), cap=MAX_SECTIONS)
            sections = sections[:MAX_SECTIONS]

        from nexus.search.section_fill import fill_for_sections
        out = await fill_for_sections(
            tenant, clearance, sections,
            set(exclude_rids or ()) | {h.rid for h in hits})
    except Exception as e:                       # noqa: BLE001 — 보강 실패가 검색을 죽이면 안 된다
        logger.warning("crossref_fill_failed", error=str(e))
        # ⛔ **빈 목록 하나로 「가리킨 절이 없다」와 「못 봤다」를 둘 다 말하지 않는다** (#533).
        if failed is not None and "crossrefs" not in failed:
            failed.append("crossrefs")
        return []
    if out:
        logger.info("crossref_fill", sections=len(sections), added=len(out))
    return out
