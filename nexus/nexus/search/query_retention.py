"""질의 텍스트 보존 — 옵트인이고, 기본은 아무것도 남기지 않는다.

SPEC-nexus-query-text-retention §3.1~§3.2 (approved 2026-08-12).

평가셋이 문서에서 저술되는 한 천장이 있다: 답을 보고 낸 문제는 코퍼스가 반드시 답을 갖는다.
그 천장을 낮추는 유일한 재료가 **사람이 실제로 던진 질문**인데, `search_log` 은 해시만 남겨
946행을 쌓고도 한 문장을 못 준다. 여기서 그 텍스트를 남기되, 남기는 방식에 조건을 건다.

**키는 조인 불가능해야 한다.** `a2a_audit` 이 `principal` 과 `query_sha256` 을 같은 행에 갖는다
(실측). 보존 키가 그 해시와 같으면 텍스트↔신원이 조인 한 번으로 이어져, "principal 컬럼을 두지
않았다" 는 보호가 무의미해진다. 그래서 키는 `sha256(tenant‖\\0‖text)` — 어디에도 없는 값이다.
"""

from __future__ import annotations

import hashlib

import structlog

from nexus import db

log = structlog.get_logger(__name__)

#: 실행 중 카운터. `/status` 가 읽는다(U2) — 로그 한 줄은 아무도 안 본다.
counters: dict[str, int] = {"stored": 0, "refused_no_notice": 0,
                            "out_of_scope": 0, "failed": 0}


def retention_key(tenant: str, query_text: str) -> str:
    """`sha256(tenant‖\\0‖text)`. **`search_log.query_sha256` 과 같아지면 안 된다.**

    구분자 `\\0` 은 테넌트 경계를 붙여 읽는 것을 막는다 — `("ab","c")` 와 `("a","bc")` 가 같은
    키가 되면 테넌트 격리가 문자열 우연에 달린다.
    """
    h = hashlib.sha256()
    h.update(tenant.encode("utf-8"))
    h.update(b"\x00")
    h.update(query_text.encode("utf-8"))
    return h.hexdigest()


async def _policy(tenant: str) -> tuple[bool, str, list[str]]:
    """(고지가 있는가, 고지 참조, 보존 대상 principal 목록). 행이 없으면 (False, '', [])."""
    row = await db.fetch_one(
        "SELECT notice_shown, principals FROM query_retention WHERE tenant = $1", tenant)
    if row is None:
        return False, "", []
    notice = (row["notice_shown"] or "").strip()
    return bool(notice), notice, list(row["principals"] or [])


async def retain(tenant: str | None, query_text: str | None,
                 principal: str | None = None, *, kind: str = "user") -> str:
    """질문을 보존한다 — 켜져 있고, 고지가 있고, **그 표면이 허용목록에 있을 때만.**

    `off`         옵트인 행이 없다. **아무것도 하지 않는다** — 기존 행의 `seen_count` 도 안 건드린다.
    `no_notice`   행은 있는데 `notice_shown` 이 비었다. 거부하고 센다.
    `out_of_scope` 켜져 있지만 이 principal 은 허용목록 밖이다. 고지를 받지 않은 표면이다.
    `stored`      저장했다(신규 또는 재관측).

    `kind` 는 **사람이 친 것과 기계가 쓴 것**을 가른다(`user` / `rewritten`). 이 테이블은
    실사용 질문을 모으려고 만든 곳이고(SPEC-nexus-query-text-retention: "평가 천장을 낮추는
    유일한 재료"), 재작성문을 구분 없이 섞으면 그 코퍼스로 만든 평가셋이 **자기 재작성기를
    채점하게** 된다. 동의 범위·만료는 원문과 같다 — 같은 대화에서 나온 같은 사람의 말이다.

    **principal 은 판단에만 쓰이고 저장되지 않는다.** 저장하면 텍스트 옆에 신원이 앉아, 소금 친
    키로 막아 둔 사람-로그가 같은 행에서 부활한다.

    이 함수는 raise 하지 않는다. 동의 범위의 곁가지 기록이 답변을 못 내리게 하면 안 된다
    (§3.5). 실패는 세고 로그로 남긴다.
    """
    if not tenant or not query_text:
        return "off"
    try:
        on, _notice, allowed = await _policy(tenant)
        if on and principal not in allowed:
            # 새 표면이 조용히 포함되는 일을 막는다 — 고지는 사람 집단에게 갔고,
            # 테넌트에는 그 집단만 도달하지 않는다.
            counters["out_of_scope"] += 1
            return "out_of_scope"
        if not on:
            # 고지 없는 옵트인 행과 옵트인 자체가 없는 것을 구분해서 센다.
            if await db.fetch_val(
                    "SELECT 1 FROM query_retention WHERE tenant = $1", tenant):
                counters["refused_no_notice"] += 1
                log.warning("query_retention.refused", tenant=tenant, reason="notice_shown 없음")
                return "no_notice"
            return "off"

        # `first_seen` 은 갱신하지 않는다 — 만료가 그것을 기준으로 돌기 때문이다(§3.3).
        await db.execute(
            """
            INSERT INTO search_query_text (tenant, retention_key, query_text, kind)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (tenant, retention_key) DO UPDATE
               SET last_seen = now(), seen_count = search_query_text.seen_count + 1
            """,
            tenant, retention_key(tenant, query_text), query_text, kind)
        counters["stored"] += 1
        return "stored"
    except Exception as exc:  # noqa: BLE001 — 원인 무관하게 검색을 살린다
        counters["failed"] += 1
        log.warning("query_retention.failed", tenant=tenant, error=str(exc))
        return "failed"


async def purge(tenant: str | None = None) -> dict[str, int]:
    """만료된 텍스트를 지운다. `{tenant: 지운 행 수}`.

    **기준은 `first_seen` 이다**(§3.3). `last_seen` 을 보면 반복되는 질문이 영원히 안 지워지고,
    반복되는 질문이야말로 내보내질 가능성이 높다.

    **고아 행도 만료로 친다.** `query_retention` 행을 손으로 지우면 그 테넌트의 텍스트에는
    적용할 `retain_days` 가 없어져 purge 가 건너뛰고 영원히 남는다 — 철회가 보존으로 뒤집히는
    가장 조용한 경로다. 여기서는 나이와 무관하게 지운다.
    """
    scope = "AND t.tenant = $1" if tenant else ""
    args = (tenant,) if tenant else ()
    rows = await db.fetch_all(
        f"""
        WITH doomed AS (
            SELECT t.tenant, t.retention_key
              FROM search_query_text t
              LEFT JOIN query_retention r ON r.tenant = t.tenant
             WHERE (r.tenant IS NULL
                    OR t.first_seen < now() - make_interval(days => r.retain_days))
               {scope}
        )
        DELETE FROM search_query_text s
         USING doomed d
         WHERE s.tenant = d.tenant AND s.retention_key = d.retention_key
        RETURNING s.tenant
        """, *args)
    out: dict[str, int] = {}
    for r in rows:
        out[r["tenant"]] = out.get(r["tenant"], 0) + 1
    if out:
        log.info("query_retention.purged", deleted=out)
    return out


async def disable(tenant: str) -> int:
    """보존을 끈다 — **텍스트와 옵트인 행을 한 트랜잭션에서 함께** 지운다. 지운 텍스트 수.

    순서가 뒤집히거나 둘이 갈라지면 철회가 보존이 된다: 옵트인 행만 지우면 텍스트가 고아로
    남고(§3.4), 텍스트만 지우면 다음 검색이 다시 쌓기 시작한다.
    """
    n = await db.fetch_val(
        "SELECT count(*) FROM search_query_text WHERE tenant = $1", tenant) or 0
    await db.execute_in_transaction([
        ("DELETE FROM search_query_text WHERE tenant = $1", (tenant,)),
        ("DELETE FROM query_retention WHERE tenant = $1", (tenant,)),
    ])
    log.info("query_retention.disabled", tenant=tenant, deleted=n)
    return n


class NotMigrated(RuntimeError):
    """보존 테이블이 아직 없다 — 마이그레이션 017 전.

    "테이블이 없다" 는 **고장이 아니라 상태**다. 아직 안 켠 배포에서 현황을 물으면 트레이스백
    50줄이 아니라 한 줄이 나와야 한다. 2026-08-12 에 실제로 그 50줄을 봤다.
    """


async def status() -> list[dict]:
    """테넌트별 보존 현황 — **가장 오래된 `first_seen` 을 함께 낸다.**

    안 도는 purge 는 증상이 없다. 그 침묵을 깨는 것이 이 줄의 목적이다
    (SPEC-nexus-index-completeness 에서 배운 것: 존재하는데 아무도 안 본 숫자).

    테이블이 없으면 `NotMigrated` 를 올린다 — 빈 목록으로 돌려주면 "안 켰다" 와 "아직 만들지
    않았다" 가 같은 화면이 되고, 둘은 다른 조치를 부른다.
    """
    if not await db.fetch_val("SELECT to_regclass('public.query_retention')"):
        raise NotMigrated("query_retention 테이블이 없다 — 마이그레이션이 아직 안 돌았다")
    rows = await db.fetch_all(
        """
        SELECT r.tenant, r.retain_days, r.notice_shown <> '' AS has_notice,
               count(t.retention_key) AS stored,
               min(t.first_seen) AS oldest,
               count(t.retention_key) FILTER (
                   WHERE t.first_seen < now() - make_interval(days => r.retain_days)
               ) AS overdue
          FROM query_retention r
          LEFT JOIN search_query_text t ON t.tenant = r.tenant
         GROUP BY r.tenant, r.retain_days, r.notice_shown
         ORDER BY r.tenant
        """)
    out = [dict(r) for r in rows]
    # 옵트인 행 없이 남아 있는 텍스트 — 철회 뒤 고아. purge 가 지울 때까지 보인다.
    orphans = await db.fetch_all(
        """
        SELECT t.tenant, count(*) AS stored, min(t.first_seen) AS oldest
          FROM search_query_text t
          LEFT JOIN query_retention r ON r.tenant = t.tenant
         WHERE r.tenant IS NULL
         GROUP BY t.tenant
        """)
    out += [{**dict(r), "retain_days": None, "has_notice": False,
             "overdue": r["stored"], "orphan": True} for r in orphans]
    return out
