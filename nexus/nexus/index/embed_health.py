"""임베딩 커버리지·웨이버 — 검색에서 빠진 내용의 양.

**세대(드리프트) 판정은 여기 없다.** 이 모듈이 원래 하던 그 일은 `chunks.embed_model` 을
읽었는데, 그 라벨은 행당 한 칸이라 벡터 컬럼 둘을 설명하지 못해 균일한 컬럼을 혼합이라
불렀다. 정본은 `index/provenance.py`(컬럼별 출처)이고, 읽는 곳은 전부 그리로 옮겼다
(SPEC-nexus-embedding-provenance-grain §3.2). 여기 남은 것은 **커버리지와 웨이버**다.
"""

from __future__ import annotations

import structlog

from nexus import db

logger = structlog.get_logger(__name__)


async def fetch_waived_count() -> int:
    """임베딩을 포기한 청크 수 — 검색에서 빠진 내용의 양이다 (§4.5)."""
    return int(await db.fetch_val("SELECT count(*) FROM embed_waivers") or 0)


async def fetch_refusals(column: str, *, tenant: str | None = None, limit: int = 3) -> dict:
    """**왜** 못 넣었는가 — `embed_refusals` 의 이유를 세어서 돌려준다.

    이 표는 2026-08-07 부터 백엔드 메시지를 요약 없이 적어 왔다(`413 max_seq_length(8192)` 처럼
    곧 처방이 되는 문장). 그런데 **읽는 곳이 코퍼스 뷰 하나뿐이었다.** 적재는 구멍의 크기와
    `nexus reembed run` 을 안내하고, 그 재시도는 같은 이유로 다시 실패한다 — 수는 "무엇을 할까"
    에 답하지 않기 때문이다.

    모집단은 커버리지와 **같은 것**이어야 한다. 커버리지가 세는 청크와 거부가 세는 청크가 다르면
    "구멍 45 · 거부 3" 같은 짝이 안 맞는 한 쌍이 나오고, 읽는 사람은 그 차이를 설명할 방법이 없다.
    그래서 정책 필터를 그대로 걸고, 부모 문서가 죽은 청크는 양쪽에서 똑같이 빠진다.

    `reasons` 는 많은 순으로 `limit` 개. `distinct` 가 그보다 크면 안 보여준 종류가 있다는 뜻이다.
    """
    rows = await db.fetch_all(
        """
        SELECT r.reason, count(*) AS n
          FROM embed_refusals r
          JOIN chunks c ON c.rid = r.chunk_rid
         WHERE r.column_name = $1
           AND ($2::text IS NULL OR c.tenant = $2)
           AND c.status = 'active' AND c.is_quarantined = false
           AND EXISTS (SELECT 1 FROM documents d
                       WHERE d.rid = c.doc_rid AND d.status = 'active')
         GROUP BY r.reason
         ORDER BY n DESC, r.reason
        """,
        column, tenant)
    return {
        "total": sum(r["n"] for r in rows),
        "distinct": len(rows),
        "reasons": [(r["reason"], r["n"]) for r in rows[:limit]],
    }


async def fetch_coverage_by_tenant() -> list[dict]:
    """테넌트별 · 다리별 커버리지 (SPEC-nexus-embedding-cutover-seam §4.2,
    SPEC-nexus-index-completeness §3.1).

    **집계 쿼리 하나**로 두 벡터 컬럼과 키워드 다리를 함께 센다 — `/status` 가 테넌트마다 쿼리를
    날리기 시작하면 "필드 하나 더" 가 조용히 팬아웃이 된다. 여기서 지키는 경계다.

    커버리지가 보고돼야 하는 이유는 하나다: 컬럼이 비어 있으면 벡터 다리가 **예외 없이** 0행을
    내고, 그 배포는 키워드 전용으로 답하면서 건강해 보인다.

    세 가지가 이 함수의 판정을 정한다 (index-completeness §3.1):

    * **모집단은 다리가 실제로 읽는 것이다.** `status='active' AND NOT is_quarantined` 에
      **부모 문서가 active** 라는 조건이 붙는다 (ADR-0006 containment, `search/hybrid.py`).
      죽은 문서 아래 살아있는 청크는 어느 다리도 읽지 않으므로, 세면 절대 안 꺼지는 구멍이 된다.
    * **키워드 다리의 어두운 상태는 NULL 만이 아니다.** 형태소 분석기가 품사 화이트리스트로
      거르므로 토큰이 하나도 안 남으면 `''::tsvector` 가 저장된다 — NULL 이 아니면서 안 잡힌다.
      (그 함수 이름은 여기 적지 않는다: `test_tokenizer_seam` 은 문자열로 검사하고, 주석에
      적힌 이름과 우회하는 import 를 구별하지 못한다.)
    * **웨이버는 빼지 않는다.** `embed_waivers` 는 `chunk_rid` 가 PK 라 컬럼이 둘인 동안 세대를
      표현하지 못한다. 768 세대에서 받은 웨이버가 1024 의 진짜 구멍을 가리게 둘 수 없다.
      개수는 `fetch_waived_count()` 로 **옆에** 보여 준다.

    `gap_*` 는 `active - <다리>` 다. 빼기 한 번이지만 여기서 한다 — 읽는 쪽마다 다시 빼면
    "무엇에서 뺐는가" 가 곧 갈린다.
    """
    rows = await db.fetch_all(
        """
        WITH readable AS (
            SELECT c.*
            FROM chunks c
            WHERE c.status = 'active' AND c.is_quarantined = false
              AND EXISTS (SELECT 1 FROM documents d
                          WHERE d.rid = c.doc_rid AND d.status = 'active')
        )
        SELECT tenant,
               count(*) AS active,
               count(*) FILTER (WHERE embedding IS NOT NULL) AS embedding,
               count(*) FILTER (WHERE embedding_1024 IS NOT NULL) AS embedding_1024,
               count(*) FILTER (WHERE tsvector_ko IS NOT NULL
                                  AND tsvector_ko <> ''::tsvector) AS bm25
        FROM readable
        GROUP BY tenant
        ORDER BY tenant
        """
    )
    return [
        {
            "tenant": r["tenant"],
            "active": r["active"],
            "embedding": r["embedding"],
            "embedding_1024": r["embedding_1024"],
            "bm25": r["bm25"],
            "gap_768": r["active"] - r["embedding"],
            "gap_1024": r["active"] - r["embedding_1024"],
            "gap_bm25": r["active"] - r["bm25"],
        }
        for r in rows
    ]


async def fetch_unreachable_documents(limit_examples: int = 3) -> list[dict]:
    """**어떤 다리도 읽을 수 없는 active 문서** — 테넌트별 개수와 예시.

    `fetch_coverage_by_tenant()` 의 사각지대다. 그 함수의 모집단은 *청크*라, 읽을 수 있는
    청크가 **0건인 문서**는 분모에도 분자에도 안 들어간다 → 커버리지 100% 로 건강하게 보인다.
    같은 논리를 한 층 위에 적용한 것이 이 함수다: 컬럼이 비면 벡터 다리가 0행을 내듯,
    청크가 없으면 **모든** 다리가 그 문서에 대해 0행을 낸다.

    격리 문서는 뺀다 — 청크가 없는 것이 **의도**이고, 이미 `nexus status` 가 따로 센다.
    빼지 않으면 정상 상태가 매번 울려 경보가 무의미해진다.

    라이브에서 이 함수가 처음 지목한 것: `default:SLACK_BOT.md`(청크 12개 전부 soft_deleted,
    세대 키 불일치로 revive 가 하나도 못 살림) — 팀이 묻는 코퍼스에 있던 유령이다.
    """
    rows = await db.fetch_all(
        """
        SELECT d.tenant,
               count(*) AS unreachable,
               (array_agg(d.source_uri ORDER BY d.updated_at DESC))[1:$1] AS examples
        FROM documents d
        WHERE d.status = 'active'
          AND d.is_quarantined = false
          AND NOT EXISTS (
              SELECT 1 FROM chunks c
              WHERE c.doc_rid = d.rid
                AND c.status = 'active'
                AND c.is_quarantined = false
          )
        GROUP BY d.tenant
        ORDER BY d.tenant
        """,
        limit_examples,
    )
    return [
        {"tenant": r["tenant"], "unreachable": r["unreachable"], "examples": list(r["examples"])}
        for r in rows
    ]


def exempt_tenants(config: dict | None = None) -> set[str]:
    """벡터를 **일부러** 안 만드는 테넌트 (SPEC-nexus-index-completeness §3.3).

    고정된 비교 코퍼스(평가 팩)가 그렇다. 이들이 매 기동마다 `embedding_column_empty` 를
    error 로 뱉는 동안, 진짜 신호 하나가 그 사이에 끼어 하루를 지나갔다.

    **면제는 선언이지 추론이 아니다.** 이름 접두사나 "커버리지가 0이니 의도겠지" 같은 규칙을
    두지 않는다 — 0 을 조용히 숨기는 규칙은 안 꺼지는 경보와 같은 종류의 실패다.
    """
    return set(((config or {}).get("index") or {}).get("coverage_exempt_tenants") or [])


async def log_embedding_coverage(column: str, config: dict | None = None) -> list[dict]:
    """설정된 세대의 커버리지를 기동 시점에 한 번 남긴다. **거부하지 않는다.**

    빈 컬럼을 부팅 거부로 막는 설계는 검토에서 기각됐다: NULL 벡터는 평범한 과도상태(적재 직후,
    죽은 적재, 웨이버 대기 중인 413)이고, 새 테넌트의 첫 적재는 정상적으로 커버리지 0 이다.
    그걸 거부로 만들면 평범한 적재 사고가 **배포 전체 장애**가 된다. 강제는 컷오버 조건이 있는
    자리에서 한다 — 결정이 붙어 있는 검사만이 거부할 자격이 있다 (§4.2).

    선언된 면제 테넌트는 `info` 로 한 줄 남기고 끝낸다 (index-completeness §3.3).
    """
    coverage = await fetch_coverage_by_tenant()
    exempt = exempt_tenants(config)
    for row in coverage:
        active, embedded = row["active"], row[column]
        if not active:
            continue
        if row["tenant"] in exempt:
            logger.info("embedding_coverage_exempt", tenant=row["tenant"], column=column,
                        active=active, embedded=embedded,
                        reason="config.index.coverage_exempt_tenants 에 선언된 테넌트")
            continue
        if embedded == 0:
            logger.error("embedding_column_empty", tenant=row["tenant"], column=column,
                         active=active,
                         hint="이 세대로 flip 했는데 재임베딩을 안 했을 때의 모양이다 — "
                              "벡터 다리는 조용히 0행을 낸다")
        elif embedded < active:
            logger.warning("embedding_coverage_partial", tenant=row["tenant"], column=column,
                           active=active, embedded=embedded, pending=active - embedded)
    return coverage
