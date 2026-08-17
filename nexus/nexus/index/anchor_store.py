"""심볼 인덱스와 앵커의 영속 계층 (SPEC-nexus-doc-code-anchors §3.1, §3.3, §3.6).

⚠ **대상 저장소의 소스 본문은 어떤 컬럼에도 들어가지 않는다.** 이름·경로·줄번호·해시뿐이다.
   스니펫 컬럼을 더하고 싶어지면 그때가 이 표가 그 저장소의 코드를 담기 시작하는 순간이다.
"""

from __future__ import annotations

from dataclasses import dataclass

import structlog

from nexus import db
from nexus.index.symbols import ScanResult

logger = structlog.get_logger(__name__)


async def replace_scan(tenant: str, repo: str, result: ScanResult, commit: str) -> None:
    """스캔 결과로 (tenant, repo) 를 **대체**한다. 누적하지 않는다.

    누적하면 사라진 심볼이 표에 남아 `orphaned` 가 계산 불가능해진다 — 그게 이 표의 존재
    이유인데. 한 트랜잭션 안에서 지우고 넣는다.
    """
    rows = [
        (tenant, repo, s.file_path, s.symbol_kind, s.symbol_name,
         s.start_line, s.end_line, s.span_hash, commit)
        for s in result.symbols
    ]

    pool = await db.get_pool()
    async with pool.acquire() as conn, conn.transaction():
        await conn.execute(
            "DELETE FROM code_symbols WHERE tenant = $1 AND repo = $2", tenant, repo)
        if rows:
            await conn.executemany(
                """
                INSERT INTO code_symbols
                    (tenant, repo, file_path, symbol_kind, symbol_name,
                     start_line, end_line, span_hash, scan_commit)
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9)
                ON CONFLICT DO NOTHING
                """,
                rows,
            )
        await conn.execute(
            """
            INSERT INTO code_scans (tenant, repo, scan_commit, symbol_count, unparsed_files)
            VALUES ($1,$2,$3,$4,$5)
            ON CONFLICT (tenant, repo) DO UPDATE
               SET scan_commit = EXCLUDED.scan_commit,
                   symbol_count = EXCLUDED.symbol_count,
                   unparsed_files = EXCLUDED.unparsed_files,
                   scanned_at = now()
            """,
            tenant, repo, commit, len(rows), result.unparsed_files,
        )

    logger.info("code_scan_stored", tenant=tenant, repo=repo,
                symbols=len(rows), unparsed=result.unparsed_files)


async def replace_deletions(tenant: str, repo: str, verdicts, commit: str) -> int:
    """지워진 이름들의 판정으로 (tenant, repo) 를 **대체**한다 (마이그레이션 029).

    누적하지 않는 이유는 `replace_scan` 과 같다: 되살아난 이름이 영원히 "삭제됨" 으로 남는다.

    `verdicts` 는 `index/history.py:classify` 가 낸 것 중 `DELETED` 인 것들이다 — 그 함수가
    외부 타입을 먼저 걸러 내므로, 프레임워크가 주는 이름이 여기 섞이지 않는다.
    """
    rows = [
        (tenant, repo, v.name, v.deletion.commit, v.deletion.date,
         v.deletion.subject, v.deletion.path, commit)
        for v in verdicts if v.deletion is not None
    ]

    pool = await db.get_pool()
    async with pool.acquire() as conn, conn.transaction():
        await conn.execute(
            "DELETE FROM code_deleted_symbols WHERE tenant = $1 AND repo = $2", tenant, repo)
        if rows:
            await conn.executemany(
                """
                INSERT INTO code_deleted_symbols
                    (tenant, repo, symbol_name, deleted_commit, deleted_date,
                     subject, file_path, scan_commit)
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8)
                ON CONFLICT DO NOTHING
                """,
                rows,
            )

    logger.info("code_deletions_stored", tenant=tenant, repo=repo, names=len(rows))
    return len(rows)


@dataclass(frozen=True)
class ScanRecord:
    scan_commit: str
    symbol_count: int
    unparsed_files: int


async def last_scan(tenant: str, repo: str) -> ScanRecord | None:
    row = await db.fetch_one(
        "SELECT scan_commit, symbol_count, unparsed_files "
        "FROM code_scans WHERE tenant = $1 AND repo = $2", tenant, repo)
    if row is None:
        return None
    return ScanRecord(row["scan_commit"], row["symbol_count"], row["unparsed_files"])


async def resolve_symbol(tenant: str, repo: str, name: str) -> list[tuple[str, str, str]]:
    """이름으로 해소. 해소 키는 `symbol_name` 단독이다 (§3.3).

    반환은 `bind`/`recheck` 가 기대하는 (symbol_name, file_path, span_hash) 목록.
    """
    rows = await db.fetch_all(
        "SELECT symbol_name, file_path, span_hash FROM code_symbols "
        "WHERE tenant = $1 AND repo = $2 AND symbol_name = $3",
        tenant, repo, name)
    return [(r["symbol_name"], r["file_path"], r["span_hash"]) for r in rows]


async def save_bindings(tenant: str, repo: str, chunk_rid: str,
                        anchors, refusals, commit: str) -> None:
    """한 청크의 바인딩 결과. 재적재 시 그 청크의 이전 결과를 대체한다."""
    pool = await db.get_pool()
    async with pool.acquire() as conn, conn.transaction():
        await conn.execute(
            "DELETE FROM doc_code_anchors WHERE chunk_rid = $1", chunk_rid)
        await conn.execute(
            "DELETE FROM doc_code_refusals WHERE chunk_rid = $1", chunk_rid)

        if anchors:
            await conn.executemany(
                """
                INSERT INTO doc_code_anchors
                    (chunk_rid, tenant, repo, candidate, edge_type,
                     symbol_name, file_path, span_hash, scan_commit)
                VALUES ($1,$2,$3,$4,'mentions',$5,$6,$7,$8)
                """,
                [(chunk_rid, tenant, repo, a.candidate, a.symbol_name,
                  a.file_path, a.span_hash, commit) for a in anchors],
            )
        if refusals:
            await conn.executemany(
                """
                INSERT INTO doc_code_refusals
                    (chunk_rid, tenant, repo, candidate, reason, match_count)
                VALUES ($1,$2,$3,$4,$5,$6)
                """,
                [(chunk_rid, tenant, repo, r.candidate, r.reason, r.match_count)
                 for r in refusals],
            )


async def iter_chunk_texts(tenant: str) -> list[tuple[str, str]]:
    """앵커를 붙일 대상 청크. 적재 시점 바인딩만으로는 **기존 코퍼스가 영원히 어둡다** —
    이미 들어와 있는 청크는 재적재하지 않는 한 후보 추출조차 되지 않기 때문이다.

    정책 필터를 그대로 건다: 격리·비활성 문서에 앵커를 달 이유가 없다.
    """
    rows = await db.fetch_all(
        """
        SELECT c.rid, c.chunk_text
          FROM chunks c
          JOIN documents d ON d.rid = c.doc_rid
         WHERE c.tenant = $1
           AND c.is_quarantined = false
           AND d.is_quarantined = false
           AND d.status = 'active'
         ORDER BY c.rid
        """,
        tenant)
    return [(r["rid"], r["chunk_text"]) for r in rows]


async def unresolved_refusals(tenant: str, repo: str) -> list[tuple[str, str]]:
    """재바인딩 대상 (§3.6). `ambiguous` 는 재시도하지 않는다 — 모호함이 저절로 풀리는
    경우보다 새로 생기는 경우가 흔하고, 풀렸다면 다음 적재가 잡는다."""
    rows = await db.fetch_all(
        "SELECT chunk_rid, candidate FROM doc_code_refusals "
        "WHERE tenant = $1 AND repo = $2 AND reason = 'unresolved'",
        tenant, repo)
    return [(r["chunk_rid"], r["candidate"]) for r in rows]


async def promote_refusal(tenant: str, repo: str, chunk_rid: str,
                          candidate: str, match, commit: str) -> None:
    """재바인딩 성공 — 거부 행을 앵커로 옮긴다."""
    name, path, digest = match
    pool = await db.get_pool()
    async with pool.acquire() as conn, conn.transaction():
        await conn.execute(
            "DELETE FROM doc_code_refusals WHERE chunk_rid = $1 AND candidate = $2",
            chunk_rid, candidate)
        await conn.execute(
            """
            INSERT INTO doc_code_anchors
                (chunk_rid, tenant, repo, candidate, edge_type,
                 symbol_name, file_path, span_hash, scan_commit)
            VALUES ($1,$2,$3,$4,'mentions',$5,$6,$7,$8)
            ON CONFLICT (chunk_rid, candidate) DO NOTHING
            """,
            chunk_rid, tenant, repo, candidate, name, path, digest, commit)


async def all_anchors(tenant: str, repo: str) -> list[dict]:
    rows = await db.fetch_all(
        "SELECT chunk_rid, candidate, symbol_name, file_path, span_hash "
        "FROM doc_code_anchors WHERE tenant = $1 AND repo = $2 "
        "ORDER BY symbol_name, chunk_rid",
        tenant, repo)
    return [dict(r) for r in rows]


async def refusal_counts(tenant: str, repo: str) -> dict[str, int]:
    rows = await db.fetch_all(
        "SELECT reason, count(*) AS n FROM doc_code_refusals "
        "WHERE tenant = $1 AND repo = $2 GROUP BY reason", tenant, repo)
    return {r["reason"]: r["n"] for r in rows}
