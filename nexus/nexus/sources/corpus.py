"""코퍼스 현황 — 무엇이 들어와 있고, 무엇이 안 보이는가.

세 가지를 한 곳에서 답한다. 지금은 셋 다 psql 을 쳐야 알 수 있고, 그래서 아무도 안 본다.

* **얼마나 있나.** 활성 문서 수. 한국어 검색 평가의 Pack B 트리거가 **활성 문서 100건** 인데
  (창이 상위 10문서라 코퍼스가 20건이면 매 질의가 절반을 돌려줘 아무것도 못 가린다), 그 거리를
  보려면 지금은 손으로 세어야 한다.
* **어디서 왔나.** 출처별 분포. "팀 지식 12건 + 리포 문서 8건" 같은 구성이 보여야 코퍼스를 키울
  때 무엇을 늘릴지 판단할 수 있다.
* **무엇이 안 보이나.** 본문이 거의 없는 문서. 정책 표를 스크린샷으로 붙이면 검색 텍스트가 사실상
  0 인데 경고가 없다 — `KOREAN_SEARCH_QUALITY.md` §3.2 가 기록한 "조용한 실패" 와 같은 형태다.
  여기서는 그것을 **판정보다 위에** 적는다.
"""

from __future__ import annotations

# Pack B 가 성립하는 최소 코퍼스. 창(상위 10문서) 대비 무작위 랭커 바닥값을 0.10 이하로
# 유지하는 값 — 근거는 nexus/docs/KOREAN_SEARCH_QUALITY.md §6.1.
PACK_B_MIN_DOCUMENTS = 100

# 이 길이 이하의 본문은 '거의 비어 있다' 로 센다. 청크 하나도 제대로 못 채우는 크기다.
THIN_DOC_MAX_CHARS = 200


async def corpus_status(con, tenant: str = "default") -> dict:
    """활성 코퍼스의 구성과, 잴 수 있을 만큼 큰지."""
    docs = await con.fetchval(
        "SELECT count(*) FROM documents WHERE tenant=$1 AND status='active'", tenant) or 0
    chunks = await con.fetchval(
        "SELECT count(*) FROM chunks WHERE tenant=$1 AND status='active'", tenant) or 0

    by_type = [dict(r) for r in await con.fetch(
        "SELECT doc_type, count(*) AS n FROM documents "
        "WHERE tenant=$1 AND status='active' GROUP BY 1 ORDER BY 2 DESC", tenant)]

    # 출처는 source_uri 접두로 가른다: Notion 미러는 `ext-notion-` 로 들어온다.
    by_origin = [dict(r) for r in await con.fetch(
        "SELECT CASE WHEN split_part(source_uri, ':', 2) LIKE 'ext-notion-%' THEN 'notion' "
        "            ELSE 'repo' END AS origin, count(*) AS n "
        "FROM documents WHERE tenant=$1 AND status='active' GROUP BY 1 ORDER BY 2 DESC", tenant)]

    thin = [dict(r) for r in await con.fetch(
        "SELECT d.source_uri, d.title, coalesce(sum(length(c.chunk_text)), 0) AS body_chars "
        "FROM documents d LEFT JOIN chunks c "
        "  ON c.doc_rid = d.rid AND c.tenant = d.tenant AND c.status='active' "
        "WHERE d.tenant=$1 AND d.status='active' "
        "GROUP BY d.source_uri, d.title HAVING coalesce(sum(length(c.chunk_text)), 0) <= $2 "
        "ORDER BY 3 ASC LIMIT 20", tenant, THIN_DOC_MAX_CHARS)]

    return {
        "tenant": tenant,
        "documents": docs,
        "chunks": chunks,
        "by_doc_type": by_type,
        "by_origin": by_origin,
        "thin_documents": {
            "threshold_chars": THIN_DOC_MAX_CHARS,
            "count": len(thin),
            "sample": thin,
            "note": ("본문이 거의 없는 문서는 검색에 사실상 안 걸린다. 그림뿐인 정책 페이지가 "
                     "여기 잡힌다 — 캡션을 살린 뒤에도 남아 있다면 그림 안의 내용이다."),
        },
        "pack_b": {
            "min_documents": PACK_B_MIN_DOCUMENTS,
            "documents": docs,
            "short_by": max(0, PACK_B_MIN_DOCUMENTS - docs),
            "ready": docs >= PACK_B_MIN_DOCUMENTS,
            "why": ("창이 상위 10문서라, 코퍼스가 그보다 크지 않으면 두 팔이 거의 무승부가 되고 "
                    "판정 규칙이 '검정력 부족' 을 돌려준다 (KOREAN_SEARCH_QUALITY.md §6.1)."),
        },
    }
