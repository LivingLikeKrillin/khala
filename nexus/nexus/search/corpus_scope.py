"""이 사람이 볼 수 있는 것은 무엇인가 — 수, 신선도, 출처, 제목 표본.

**검색 모듈이 아니다.** 첫 판은 이 함수를 `hybrid.py` 안에 두었고 그것이 CI 를 40분 매달았다:
DB 없이 도는 단위 테스트 수백 개가 `hybrid_search` 를 부르는데, 거기에 DB 왕복을 얹으면 죽은
이벤트 루프에 묶인 전역 asyncpg 풀을 집는다. 그래서 호출을 API 엔드포인트로 옮겼는데, **함수는
여전히 검색 모듈에 남아 있었다** — docstring 이 "검색 경로에서 부르지 않는다" 고 말하는 함수가
검색 파일에 사는 모양이었다.

파일을 가른 것은 문서가 아니라 검사였다: `test_search_determinism_db` 는 `hybrid.py` 의 **모든**
`ORDER BY` 가 `c.rid ASC` 로 끝나는지 훑는다(검색 다리는 전순서여야 하므로). 진단용 집계의
`ORDER BY 2 DESC` 가 거기 걸렸고, 검사를 좁히는 대신 함수를 옮겼다 — 검사가 옳았다.
"""

from __future__ import annotations

from nexus import db


async def visibility_counts(tenant: str, clearance: str) -> dict:
    """**이 사람이 볼 수 있는 것**을 설명한다 — 수, 신선도, 출처, 그리고 제목 표본.

    0건의 원인 셋은 서로 다른 사실이고 고칠 사람도 다르다: 코퍼스가 빈 것(적재 담당), 질의가 안
    맞은 것(사용자), 그리고 등급/테넌트 설정이 코퍼스 전체를 가린 것(운영자). 셋째가 둘째로
    위장하던 동안 슬랙 봇은 "인덱싱된 문서에서 답을 찾지 못했습니다" 라고 답했다 — 뒤진 문서가
    하나도 없었으므로 거짓이었다 (2026-08-13).

    **수만으로는 사람의 질문에 답이 안 된다.** "코퍼스 범위가 어떻게 돼?" 를 물은 팀원이 알고
    싶은 것은 108 이라는 숫자가 아니라 *"내가 뭘 물어봐도 되냐"* 다. 그래서 출처와 제목 표본을
    함께 낸다 — 손으로 쓴 소개문이 아니라 **코퍼스 자신에서 유도한 것**이라 낡지 않는다.

    **이 함수는 검색 경로에서 부르지 않는다.** 첫 판은 `hybrid_search` 안에 두었고 그것이 CI 를
    40분 매달았다: DB 없이 도는 단위 테스트 수백 개가 그 함수를 부르는데, 거기에 DB 왕복을
    얹으면 죽은 이벤트 루프에 묶인 전역 asyncpg 풀을 집는다. 커넥션이 열린 트랜잭션째 남아
    `documents` 락을 쥐고, 뒤따르는 모든 TRUNCATE 가 줄을 선다. 진단은 자기 엔드포인트에만 산다.
    """
    visible = "classification <= $2::classification_level"
    row = await db.fetch_one(
        f"""
        SELECT count(*) AS total,
               count(*) FILTER (WHERE {visible}) AS visible,
               -- 신선도는 **보이는 것 중에서** 잰다. 전체에서 재면 못 읽는 문서의 갱신일이
               -- "최신" 으로 보고돼, 사용자가 볼 수 없는 것의 신선도를 믿게 된다.
               max(updated_at) FILTER (WHERE {visible}) AS newest_visible
          FROM documents
         WHERE tenant = $1 AND status = 'active' AND is_quarantined = false
        """, tenant, clearance)
    out = {
        "total": int((row and row["total"]) or 0),
        "visible": int((row and row["visible"]) or 0),
        "newest": row["newest_visible"] if row else None,
        "sources": {},
        "sample_titles": [],
    }
    if not out["visible"]:
        return out

    # 출처는 `source_uri` 에서 딴다. `source_kind` 는 2026-08-13 까지 노션 문서에도 'git' 이
    # 적혀 있었고(migration 022 로 고침), **고친 뒤에도 여기서는 URI 를 본다** — 유도는
    # `documents/origin.py` 한 곳에서만 한다는 규칙이 저장값과 화면이 갈라지는 것을 막는다.
    rows = await db.fetch_all(
        f"""
        SELECT CASE WHEN source_uri LIKE '%%ext-notion%%' THEN 'notion'
                    WHEN source_uri LIKE 'git://%%'       THEN 'git'
                    ELSE 'other' END AS src, count(*) AS n
          FROM documents
         WHERE tenant = $1 AND status = 'active' AND is_quarantined = false AND {visible}
         GROUP BY 1 ORDER BY 2 DESC
        """, tenant, clearance)
    out["sources"] = {r["src"]: int(r["n"]) for r in rows}

    # 제목 표본은 **가장 큰 출처에서** 뽑는다. 처음엔 전체에서 `updated_at DESC` 로 뽑았는데,
    # 문서 8건을 일괄 복구하자 그 8건이 최신이 되어 예시가 전부 그것으로 채워졌다 — 108/116 이
    # 노션 정책인 코퍼스가 "Nexus 문서 모음" 처럼 보였다. **최신은 대표가 아니다.**
    #
    # 그리고 **숫자뿐인 제목은 뺀다** — 노션 하위 페이지가 "11", "7" 같은 제목을 갖는데, 그것을
    # 예시로 보여주면 코퍼스가 무엇인지 더 모르게 된다.
    top_source = max(out["sources"], key=out["sources"].get) if out["sources"] else None
    where_src = {
        "notion": "AND source_uri LIKE '%%ext-notion%%'",
        "git": "AND source_uri LIKE 'git://%%'",
    }.get(top_source, "")
    rows = await db.fetch_all(
        f"""
        SELECT title FROM documents
         WHERE tenant = $1 AND status = 'active' AND is_quarantined = false AND {visible}
           AND char_length(btrim(title)) >= 4 AND btrim(title) !~ '^[0-9]+$'
           {where_src}
         ORDER BY updated_at DESC LIMIT 6
        """, tenant, clearance)
    out["sample_titles"] = [r["title"] for r in rows]
    return out
