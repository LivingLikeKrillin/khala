"""best-effort 적재가 **아직 살아 있는가.**

⛔ **왜 있나 (실측 2026-09-02).** `search_log` 가 **34시간 동안 한 줄도 안 쌓였다.** 읽기 범위를
붙이며 `str` 필드에 목록을 넣어 INSERT 가 터졌는데, `record_search` 는 *절대 raise 안 함* 으로
설계돼 있어서 요청은 멀쩡했다. 검사 1,800개가 초록이었다 — 아무도 *"행이 앉는가"* 를 안 물었다.

⚠ **경고는 찍혀 있었다.** `search.signal.persist_failed` 가 그때 로그에 남았다. 침묵이 아니라
**아무도 안 읽은 것**이 문제였고, 그래서 처방이 *"실패를 더 크게 내라"* 가 아니라 **"마지막
적재 시각을 사람이 볼 수 있게 하라"** 다. 경고를 키워도 읽는 사람이 없으면 같은 일이 난다.

이 모듈은 **판정하지 않는다.** 임계를 두면 그 임계가 곧 또 하나의 안 읽는 신호가 된다.
숫자와 경과 시간을 내고, 무엇이 이상한지는 읽는 사람이 정한다.
"""

from __future__ import annotations

from dataclasses import dataclass

from nexus import db

#: 감시 대상 — `(표, 시각 칼럼, 무엇을 담나)`.
#:
#: **best-effort 적재만 넣는다.** 실패해도 요청이 사는 자리들이고, 그래서 조용히 죽는다.
#: `documents`·`chunks` 처럼 실패가 요청을 죽이는 표는 여기 없다 — 죽으면 바로 보인다.
SINKS: tuple[tuple[str, str, str], ...] = (
    ("search_log", "ts", "검색·답변 신호 (demand-pull 판단의 입력)"),
    ("search_answer_text", "created_at", "답변 원문 보존 (동의한 테넌트)"),
    ("answer_vote", "voted_at", "슬랙 👍/👎"),
    ("a2a_audit", "ts", "에이전트 호출 감사"),
)


@dataclass
class SinkHealth:
    table: str
    what: str
    rows: int
    last_write: str | None
    hours_since: float | None
    exists: bool = True


async def check() -> list[SinkHealth]:
    """표별 행 수와 마지막 적재 시각. **없는 표는 없다고 말한다** — 0행과 다른 사실이다."""
    out: list[SinkHealth] = []
    for table, col, what in SINKS:
        present = await db.fetch_val(
            "SELECT to_regclass($1) IS NOT NULL", f"public.{table}")
        if not present:
            out.append(SinkHealth(table, what, 0, None, None, exists=False))
            continue
        row = await db.fetch_one(
            f"SELECT count(*) AS n, max({col})::text AS last, "  # noqa: S608 - 표·칼럼은 상수다
            f"EXTRACT(EPOCH FROM (now() - max({col})))/3600 AS hrs FROM {table}")
        out.append(SinkHealth(
            table, what, int(row["n"] or 0), row["last"],
            float(row["hrs"]) if row["hrs"] is not None else None))
    return out


def describe(rows: list[SinkHealth]) -> str:
    """사람이 읽는 표 한 장. **판정 문구를 안 쓴다** — 숫자를 보고 사람이 정한다."""
    lines = [f"{'표':<20} {'행':>8} {'마지막 적재':>21} {'경과':>10}  무엇"]
    for r in rows:
        if not r.exists:
            lines.append(f"{r.table:<20} {'—':>8} {'표가 없다':>21} {'—':>10}  {r.what}")
            continue
        last = (r.last_write or "")[:19] or "없음"
        hrs = f"{r.hours_since:.1f}시간" if r.hours_since is not None else "—"
        lines.append(f"{r.table:<20} {r.rows:>8} {last:>21} {hrs:>10}  {r.what}")
    return "\n".join(lines)
