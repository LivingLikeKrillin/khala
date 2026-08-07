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


async def _unembedded(con, tenant: str) -> dict:
    """벡터가 없는 활성 청크 — **검색에서 안 보이는데 어디에도 안 세어지던 것.**

    `index/embed.py` 는 임베딩 실패를 삼키고 `False` 를 돌려주며, `embed_health` 는
    `IS NOT NULL` 만 세므로 거부된 청크는 두 곳 어디에도 안 잡힌다. `KOREAN_SEARCH_QUALITY.md`
    §3.2 가 "아무 데도 집계되지 않는다" 로 기록하고 유예해 둔 상태다.

    2026-08-07 실물에서 발생했다: 정책 문서의 18,751자 청크를 사이드카가
    `413 max_seq_length(8192)` 로 거부했고, 그 청크는 벡터 다리에서 영구히 안 보인다. 지금은
    289분의 1이지만 **큰지 작은지 보이지 않는 것이 결함의 본질**이라, 판정보다 위에 적는다.

    컬럼은 `configured_column` 으로 정한다 — 검색 다리가 읽는 그 컬럼이어야 한다. 다른 컬럼을
    세면 세대가 바뀐 뒤 "다 임베딩됐다" 는 거짓을 보고하게 된다.
    """
    from nexus.index.vector_index import configured_column

    column = configured_column()
    # 거부 사유를 함께 낸다 — 개수만으로는 처방을 못 고른다. `413 max_seq_length` 는 청킹을
    # 고치라는 말이고, 인코딩 오류나 백엔드 다운은 각각 다른 처방이다. 기록이 없으면(옛 청크,
    # 또는 표가 생기기 전에 실패한 것) 사유는 빈 채로 나온다 — 없는 것을 지어내지 않는다.
    rows = await con.fetch(
        f"SELECT c.rid, d.title, length(c.chunk_text) AS chars, "          # noqa: S608
        f"       coalesce(r.reason, '') AS reason, r.refused_at "
        f"FROM chunks c JOIN documents d ON d.rid = c.doc_rid AND d.tenant = c.tenant "
        f"LEFT JOIN embed_refusals r ON r.chunk_rid = c.rid AND r.column_name = $2 "
        f"WHERE c.tenant = $1 AND c.status = 'active' AND c.{column} IS NULL "
        f"ORDER BY chars DESC LIMIT 20", tenant, column)
    total = await con.fetchval(
        f"SELECT count(*) FROM chunks "                                    # noqa: S608
        f"WHERE tenant = $1 AND status = 'active' AND {column} IS NULL", tenant) or 0
    return {
        "column": column,
        "count": total,
        "sample": [dict(r) for r in rows],
        "note": ("벡터가 없는 청크는 **벡터 다리에서 영구히 안 보인다**. 임베딩 실패는 삼켜지고 "
                 "embed_health 도 세지 않으므로, 여기 말고는 드러나는 곳이 없다. "
                 "가장 흔한 원인은 max_seq_length 를 넘는 긴 청크다."),
    }


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

    unembedded = await _unembedded(con, tenant)

    return {
        "tenant": tenant,
        "documents": docs,
        "chunks": chunks,
        "unembedded_chunks": unembedded,
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
