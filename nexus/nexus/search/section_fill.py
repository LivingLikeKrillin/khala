"""절 채움 — **한 문서가 다양성 상한을 꽉 채웠다면, 그 문서의 남은 절도 근거에 넣는다.**

검색은 두 가지를 판정한다: *어느 문서인가*, 그리고 *그 문서의 어느 절인가*. 정책 코퍼스에서
2026-08-18 에 실측한 것은 **앞은 맞히고 뒤를 못 맞힌다**는 것이었다:

    어떤 질문의 답을 담은 청크는 코퍼스에 하나뿐이고, BM25·벡터 **후보 20 양쪽 다 밖**이었다.
    같은 문서의 다른 청크는 최종 top-10 에 다섯(=상한) 실려 있었다. 문서는 4위였다.

질문이 쓴 낱말과 정답 절이 쓴 낱말이 하나도 겹치지 않으니, 어느 랭킹으로도 그 절은 안
올라온다. 질의 확장으로 메우려던 구멍인데 — 문서를 이미 맞힌 마당에 **그 문서 안에서 어휘로 절을
고르는 것 자체가 틀린 수**다. 고를 게 아니라 채운다.

**트리거는 상수가 아니라 상한이다.** "문서가 `diversity_per_doc_cap` 만큼 실렸다" = 다양성 규칙이
그 문서를 **깎았다**는 뜻이고, 곧 검색이 그 문서에 몰표를 줬다는 신호다. 상한을 3 으로 되돌리면
트리거도 3 으로 따라간다 — 두 숫자가 갈라질 방법이 없다.

**랭킹에는 손대지 않는다.** 채워진 절은 `SearchResult.hits` 가 아니라 `SearchResult.fill` 로
따로 간다. 사람이 보는 순위·Recall 측정·Top-1 은 오늘과 글자 그대로 같고, 달라지는 것은 답을
쓰는 모델이 받는 근거뿐이다.

한계 둘을 명시한다:
  - 큰 문서는 통째로 붙이지 않는다(`MAX_DOC_CHUNKS`). 42청크짜리 정책 문서를 다 실으면 근거가
    답이 아니라 문서가 된다.
  - 이것은 **재현율을 사는 대신 프롬프트를 늘린다.** 실측(2026-08-18): 다중홉 요구 커버리지
    7/8 → 8/8, 근거 문자수 +29%. 늘어난 근거가 답을 흐리는지는 답변 평가 하니스로 따로 잰다.
"""

from __future__ import annotations

import structlog

from nexus import db

logger = structlog.get_logger(__name__)

#: 이보다 많은 활성 청크를 가진 문서는 통째로 붙이지 않는다. 근거가 문서로 바뀌는 것을 막는
#: 유일한 상한이고, 값의 근거는 라이브 코퍼스의 문서 크기 분포다(중앙값 3, 최장 42청크).
MAX_DOC_CHUNKS = 20

#: **히트가 앉은 절**을 완성할 때의 절 크기 상한.
MAX_SECTION_CHUNKS = 8

#: 절을 완성해 주는 히트의 수. 상위 몇 개만 본다.
#:
#: **왜 상한이 필요한가.** 히트 10개의 절을 전부 완성하면 근거 문자수가 **+102%** 로 뛴다
#: (2026-08-26, 33문항 실측 — 질의당 채움 12.4청크). 절 채움은 재현율을 사는 대신 프롬프트를
#: 늘리는 거래이고, 두 배는 그 거래의 값이 아니다.
#:
#: 상위 히트로 좁히는 것은 **또 고르는 것이 아니다** — 랭킹이 이미 매긴 순서를 그대로 잘라낼
#: 뿐이고, 자르는 자리가 하나의 숫자로 드러나 있다.
FILL_TOP_HITS = 3


async def fill_for_docs(
    tenant: str,
    clearance: str,
    doc_rids: list[str],
    exclude_rids: set[str],
) -> list[dict]:
    """`doc_rids` 문서들의 **아직 안 실린** 활성 청크를 문서 순서대로.

    **정책 필터는 검색 경로와 글자 그대로 같다.** 여기서 한 줄이라도 빠지면 등급이 막아 둔 절이
    근거로 새어 나간다 — 랭킹이 아니라 접근 통제의 문제다.
    """
    if not doc_rids:
        return []

    rows = await db.fetch_all(
        """
        SELECT c.rid, c.doc_rid, c.section_path, c.chunk_text, c.classification,
               c.provenance_tier, c.chunk_index, c.source_uri, c.source_version,
               d.title AS doc_title, d.approved_hash, d.doc_type, d.updated_at,
               coalesce(d.n_images, 0) AS n_images,
               count(*) OVER (PARTITION BY c.doc_rid) AS doc_chunks
        FROM chunks c
        JOIN documents d ON d.rid = c.doc_rid AND d.tenant = c.tenant
        WHERE c.doc_rid = ANY($1::text[])
          AND c.tenant = $2
          AND c.classification <= $3::classification_level
          AND c.is_quarantined = false
          AND c.status = 'active'
          AND d.status = 'active'
          AND d.is_quarantined = false
        ORDER BY c.doc_rid, c.chunk_index, c.rid
        """,
        doc_rids, tenant, clearance,
    )
    # 상한을 넘는 문서는 통째로 뺀다. **부분만 붙이지 않는다** — 어느 절을 고를지가 바로 이
    # 코드가 못 한다고 판정한 일이고, 여기서 다시 고르면 같은 결함을 다른 자리에서 반복한다.
    return [dict(r) for r in rows
            if r["doc_chunks"] <= MAX_DOC_CHUNKS and r["rid"] not in exclude_rids]


async def fill_for_sections(
    tenant: str,
    clearance: str,
    sections: list[tuple[str, str]],
    exclude_rids: set[str],
) -> list[dict]:
    """**히트가 앉은 절**의 나머지 청크.

    **위 `fill_for_docs` 의 주석에 답한다.** 거기서 "부분만 붙이지 않는다 — 어느 절을 고를지가
    이 코드가 못 한다고 판정한 일" 이라고 적었고, 그 판정은 지금도 옳다. 여기서 절을 **고르지
    않는다** — 검색이 이미 고른 절을 쓴다. 히트가 그 절에 앉았다는 사실이 선택이고, 이 함수는
    그 절을 완성할 뿐이다. 문서 단위에서 하던 일과 같은 규율을 한 층 안쪽에서 하는 것이다.

    **왜 필요한가 (2026-08-26 라이브).** 어떤 표가 낡았다고 알리는 문단이 그 표와 **같은 절**에
    있었는데(chunk 2 · 6), 문서가 32청크라 `MAX_DOC_CHUNKS` 에 걸려 채움에서 통째로 빠졌다.
    표만 근거로 가고 그것을 무효화하는 문장은 안 갔다 — 답변은 낡은 숫자를 정본으로 읽었다.
    **검색은 정답 문서를 맞혔고, 그것을 해석할 문장이 따라오지 않은 것이다.**
    """
    if not sections:
        return []
    doc_rids = [d for d, _ in sections]
    paths = [p for _, p in sections]
    rows = await db.fetch_all(
        """
        SELECT c.rid, c.doc_rid, c.section_path, c.chunk_text, c.classification,
               c.provenance_tier, c.chunk_index, c.source_uri, c.source_version,
               d.title AS doc_title, d.approved_hash, d.doc_type, d.updated_at,
               coalesce(d.n_images, 0) AS n_images,
               count(*) OVER (PARTITION BY c.doc_rid, c.section_path) AS section_chunks
        FROM chunks c
        JOIN documents d ON d.rid = c.doc_rid AND d.tenant = c.tenant
        JOIN unnest($1::text[], $2::text[]) AS want(doc_rid, section_path)
          ON want.doc_rid = c.doc_rid AND want.section_path = c.section_path
        WHERE c.tenant = $3
          AND c.classification <= $4::classification_level
          AND c.is_quarantined = false
          AND c.status = 'active'
          AND d.status = 'active'
          AND d.is_quarantined = false
        ORDER BY c.doc_rid, c.chunk_index, c.rid
        """,
        doc_rids, paths, tenant, clearance,
    )
    return [dict(r) for r in rows
            if r["section_chunks"] <= MAX_SECTION_CHUNKS and r["rid"] not in exclude_rids]


def hit_sections(hits) -> list[tuple[str, str]]:
    """히트가 앉은 `(doc_rid, section_path)` — 중복 없이, 순서 유지.

    **포화를 트리거로 쓰지 않는다.** 문서 단위 채움의 트리거는 "다양성 규칙이 이 문서를 깎았다"
    였고 그건 문서를 고르는 신호로 옳다. 그런데 절은 다르다 — 2026-08-26 실측에서 정답 표와
    그것을 무효화하는 문단이 **같은 절**에 있었는데, 그 문서는 히트가 3개뿐이라(상한 5) 포화에
    못 미쳤고 채움이 아예 안 돌았다. 답변은 낡은 숫자를 정본으로 읽었다.

    절은 저자가 한 덩어리로 쓴 단위다. 히트가 그 안에 앉았다는 것은 **검색이 이미 그 절을
    골랐다**는 뜻이고, 남은 문장을 빼놓을 이유가 없다. 크기는 `MAX_SECTION_CHUNKS` 가 막는다.
    """
    out: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for h in hits[:FILL_TOP_HITS]:
        key = (h.doc_rid, h.section_path or "root")
        if key not in seen:
            seen.add(key)
            out.append(key)
    return out


def saturated_docs(hits, per_doc_cap: int) -> list[str]:
    """상한을 꽉 채운 문서들의 rid. 상한이 0 이하면 규칙을 끈 것으로 읽는다."""
    if per_doc_cap <= 0:
        return []
    counts: dict[str, int] = {}
    for h in hits:
        counts[h.doc_rid] = counts.get(h.doc_rid, 0) + 1
    return [rid for rid, n in counts.items() if n >= per_doc_cap]
