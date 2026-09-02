"""best-effort 적재가 **아직 살아 있는가.**

⛔ **왜 있나 (실측 2026-09-02).** `search_log` 가 **34시간 동안 한 줄도 안 쌓였다.** 읽기 범위를
붙이며 `str` 필드에 목록을 넣어 INSERT 가 터졌는데, `record_search` 는 *절대 raise 안 함* 으로
설계돼 있어서 요청은 멀쩡했다. 검사 1,800개가 초록이었다 — 아무도 *"행이 앉는가"* 를 안 물었다.

⚠ **경고는 찍혀 있었다.** `search.signal.persist_failed` 가 그때 로그에 남았다. 침묵이 아니라
**아무도 안 읽은 것**이 문제였고, 그래서 처방이 *"실패를 더 크게 내라"* 가 아니라 **"마지막
적재 시각을 사람이 볼 수 있게 하라"** 다. 경고를 키워도 읽는 사람이 없으면 같은 일이 난다.

이 모듈은 **판정하지 않는다.** 임계를 두면 그 임계가 곧 또 하나의 안 읽는 신호가 된다.
숫자와 경과 시간을 내고, 무엇이 이상한지는 읽는 사람이 정한다.

⛔ **"안 쌓임" 은 "죽음" 과 "조용함" 을 못 가른다.** 만들자마자 내가 그 함정에 빠졌다 —
`search_answer_text` 가 62시간째 2행인 것을 보고 두 번째 결함으로 읽었는데, 그 표는 **슬랙이
답을 낼 때만** 쌓이고 62시간 동안 슬랙 질문이 없었다. 정상이다.

그래서 표마다 **무엇이 이것을 쓰게 하는가**(`driven_by`)를 같이 낸다. 경과 시간만 보면
읽는 사람이 방금 나처럼 오독한다.
"""

from __future__ import annotations

from dataclasses import dataclass

from nexus import db

#: 감시 대상 — `(표, 시각 칼럼, 무엇을 담나)`.
#:
#: **best-effort 적재만 넣는다.** 실패해도 요청이 사는 자리들이고, 그래서 조용히 죽는다.
#: `documents`·`chunks` 처럼 실패가 요청을 죽이는 표는 여기 없다 — 죽으면 바로 보인다.
SINKS: tuple[tuple[str, str, str, str], ...] = (
    ("search_log", "ts", "검색·답변 신호",
     "모든 검색·답변 — **조용할 이유가 거의 없다**"),
    ("search_answer_text", "created_at", "답변 원문 보존",
     "슬랙이 답을 낼 때만 — 질문이 없으면 안 쌓이는 게 정상"),
    ("answer_vote", "voted_at", "슬랙 👍/👎",
     "사람이 누를 때만 — 오래 비어 있는 것이 기본값"),
    ("a2a_audit", "ts", "에이전트 호출 감사",
     "A2A 호출 — 2026-06-19 결정으로 **휴면 중**"),
)


@dataclass
class SinkHealth:
    table: str
    what: str
    #: 무엇이 이 표를 쓰게 하는가. **경과 시간만으로는 죽음과 조용함을 못 가른다.**
    #: ⚠ 기본값을 주지 않는다 — dataclass 에서 기본값 있는 필드가 앞에 오면 뒤 필드가
    #: 다 깨진다. 이 파일에서 오늘 두 번 그랬다.
    driven_by: str
    rows: int
    last_write: str | None
    hours_since: float | None
    exists: bool = True


async def check() -> list[SinkHealth]:
    """표별 행 수와 마지막 적재 시각. **없는 표는 없다고 말한다** — 0행과 다른 사실이다."""
    out: list[SinkHealth] = []
    for table, col, what, driven in SINKS:
        present = await db.fetch_val(
            "SELECT to_regclass($1) IS NOT NULL", f"public.{table}")
        if not present:
            out.append(SinkHealth(table, what, driven, 0, None, None, exists=False))
            continue
        row = await db.fetch_one(
            f"SELECT count(*) AS n, max({col})::text AS last, "  # noqa: S608 - 표·칼럼은 상수다
            f"EXTRACT(EPOCH FROM (now() - max({col})))/3600 AS hrs FROM {table}")
        out.append(SinkHealth(
            table, what, driven, int(row["n"] or 0), row["last"],
            float(row["hrs"]) if row["hrs"] is not None else None))
    return out


def describe(rows) -> str:
    """사람이 읽는 목록. **판정 문구를 안 쓴다** — 숫자를 보고 사람이 정한다.

    ⛔ **무엇이 쓰게 하는가를 반드시 같이 낸다.** 첫 판은 경과 시간만 냈고, 만들자마자 내가
    `search_answer_text` 62시간을 두 번째 결함으로 읽었다. 그 표는 슬랙이 답을 낼 때만 쌓이고
    그동안 질문이 없었다 — 정상이다. 경과 시간만 보면 읽는 사람이 그렇게 오독한다.
    """
    out = ["⚠ 오래 비어 있는 것이 곧 고장은 아니다 — 무엇이 쓰게 하는가를 같이 보라.", ""]
    for r in rows:
        if not r.exists:
            out += [f"{r.table}  — 표가 없다", f"    {r.what}", ""]
            continue
        last = (r.last_write or "")[:19] or "없음"
        hrs = f"{r.hours_since:.1f}시간 전" if r.hours_since is not None else "—"
        out += [f"{r.table}  행 {r.rows}  ·  마지막 {last} ({hrs})",
                f"    {r.what} — 쓰게 하는 것: {r.driven_by}", ""]
    return "\n".join(out).rstrip()
