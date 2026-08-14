"""답변 피드백 저장 (SPEC-nexus-answer-feedback U1, approved 2026-08-14).

**👎 한 건은 통계가 아니라 조사할 단서다.** 팀이 5명이라 만족률은 영원히 안 나오고(월 10표
남짓), 그 수로 비율을 계산하는 것은 잡음에 이름을 붙이는 짓이다. 그래서 이 층이 하는 일은
**수와 사유 코드를 정직하게 세는 것** 하나이고, 비율 산출은 SPEC §5.2 가 문턱을 넘기 전까지
금지돼 있다.

이 모듈이 **저장하지 않는 것**이 설계의 절반이다:

- **텍스트** — 질의도 답변도. 조사 아티팩트는 슬랙 스레드에 이미 있고 여기엔 포인터만 든다.
- **신원** — 투표자를 가리키는 값도, 그것에서 파생된 해시도. 초안은 답변 안 중복투표를 막으려
  `sha256(answer_key‖user_id)` 를 두려 했는데, `answer_key` 가 DB 에 평문으로 있고 팀이
  5명이라 후보 다섯을 해시해 보면 투표자가 특정된다 — 소금은 오프라인 대입을 막지 못한다.
  대가는 명시적이다: 같은 사람의 반복 투표를 못 막는다.
"""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone

import structlog

from nexus import db

log = structlog.get_logger(__name__)

#: 사용자에게 보인 고지 문구의 식별자. 문구 자체는 표시 계층의 상수이고, 여기엔 **어느 판을
#: 보여줬는지**만 남는다 — 슬랙 메시지는 편집·삭제되므로 나중에 가리킬 것이 필요하다.
NOTICE_VERSION = "fb-notice-v1"

#: 발급 후 이만큼 지나면 투표를 받지 않는다. 오래된 스레드의 버튼이 영원히 살아 있으면 그
#: 값은 만료 없는 자격증명이 된다 (§3.2).
VOTE_TTL = timedelta(days=30)

#: 포인터(채널·메시지)를 지우는 시점. **수와 사유 코드는 남는다** — 지우는 것은 질문자 추정
#: 경로이지 집계가 아니다 (§4 I12).
POINTER_TTL = timedelta(days=90)

#: 사유 코드. 스키마의 CHECK 와 **같은 목록**이어야 한다 — 두 벌이면 갈라진다.
REASONS = ("wrong_evidence", "not_my_question", "ignored_format", "not_found")

#: 실행 중 카운터. orphan 은 **원인별로** 센다 — 한 칸에 뭉치면 "수가 크면 조사" 라는
#: 처방이 발화해도 무엇을 볼지 모른다 (§3.3).
counters: dict = {
    "offers": 0,
    "offer_write_failed": 0,
    "votes": 0,
    "votes_refused": 0,
    "reason_rejected": 0,
    "orphan_votes": {"unknown_key": 0},
}


class VoteRefused(Exception):
    """이 투표를 받지 않는다. **조용히 버리지 않고 부른 쪽에 알린다** — 사용자가 눌렀는데
    아무 일도 안 일어나면 그것이 이 리포가 반복 지적한 '초록인데 동작 안 함' 이다."""


def issue_key() -> str:
    """답변 하나에 붙는 불투명 키. **질의·답변·신원 어느 것에서도 파생되지 않는다.**

    128비트 CSPRNG 다. 이 값은 (a) 투표 권한 그 자체이고 (b) 버튼 페이로드로 나가므로 보안
    파라미터다 — 열거 가능한 값이면 남의 답변에 투표할 수 있다.
    """
    return secrets.token_urlsafe(16)


async def record_offer(*, tenant: str, answer_key: str, channel_id: str | None = None,
                       message_ts: str | None = None,
                       notice_version: str = NOTICE_VERSION) -> None:
    """버튼을 붙여 답변을 내보냈다는 사실 한 줄. **분모다.**

    **best-effort** — 답변 경로에서 부르므로 여기서 예외가 나가면 피드백이 답변을 죽인다
    (§4 I6). 실패해도 투표는 살아남는다: `record_vote` 가 제안 행이 없으면 만들어 넣는다.
    """
    try:
        await db.execute(
            """
            INSERT INTO answer_offered (tenant, answer_key, notice_version,
                                        channel_id, message_ts)
            VALUES ($1, $2, $3, $4, $5)
            ON CONFLICT (tenant, answer_key) DO NOTHING
            """,
            tenant, answer_key, notice_version, channel_id, message_ts)
        counters["offers"] += 1
    except Exception as exc:  # noqa: BLE001 — 피드백이 답변 경로를 죽이면 안 된다
        counters["offer_write_failed"] += 1
        log.warning("feedback.offer_write_failed", error=str(exc))


async def record_vote(*, tenant: str, answer_key: str, verdict: str,
                      channel_id: str, message_ts: str) -> str:
    """투표 한 줄을 **추가**한다. 돌려주는 값은 사유 UPDATE 에 쓸 투표 행 id.

    **INSERT 다.** 한 답변을 여러 사람이 보므로 두 번째 투표가 첫 투표를 덮으면 분모는 남고
    분자가 조용히 유실된다 (§4 I5).

    거절 조건 둘:

    - **결속 불일치** — 페이로드의 (채널, 메시지) 가 제안 시점 값과 다르면 거절한다. 이것이
      없으면 `answer_key` 는 30일짜리 무기명 자격증명이다 (§4 I10).
    - **만료** — 발급 후 30일 (§4 I7).

    제안 행이 없으면 **`synthesized=true` 로 만들어 넣고 투표를 받는다.** 제안 쓰기는
    best-effort 인데 투표를 FK 로 막으면, 시스템이 불안정할 때 정확히 그때의 투표만 통째로
    사라진다. 그 행은 분모에서 빠지고(§5.3) 만료 판정에서도 빠진다 — `offered_at` 이 발급
    시각이 아니라 투표 시각이라 잴 기준이 없기 때문이다. 그 구멍을 숨기지 않는다.
    """
    if verdict not in ("up", "down"):
        raise ValueError(f"알 수 없는 verdict: {verdict!r}")

    offer = await db.fetch_one(
        "SELECT offered_at, channel_id, message_ts, synthesized "
        "FROM answer_offered WHERE tenant = $1 AND answer_key = $2",
        tenant, answer_key)

    if offer is None:
        counters["orphan_votes"]["unknown_key"] += 1
        log.warning("feedback.orphan_vote", reason="unknown_key")
        await db.execute(
            """
            INSERT INTO answer_offered (tenant, answer_key, notice_version, synthesized,
                                        channel_id, message_ts)
            VALUES ($1, $2, NULL, true, $3, $4)
            ON CONFLICT (tenant, answer_key) DO NOTHING
            """,
            tenant, answer_key, channel_id, message_ts)
    else:
        if offer["channel_id"] != channel_id or offer["message_ts"] != message_ts:
            counters["votes_refused"] += 1
            raise VoteRefused("결속되지 않은 메시지에서 온 투표")
        if datetime.now(timezone.utc) - offer["offered_at"] > VOTE_TTL:
            counters["votes_refused"] += 1
            raise VoteRefused("만료된 키")

    vote_id = issue_key()
    await db.execute(
        "INSERT INTO answer_vote (id, tenant, answer_key, verdict) VALUES ($1, $2, $3, $4)",
        vote_id, tenant, answer_key, verdict)
    counters["votes"] += 1
    return vote_id


async def set_reason(*, vote_id: str, reason: str) -> bool:
    """👎 의 사유를 그 투표 행에 적는다. 적었으면 True.

    **가드 셋**(`verdict='down'` · `reason IS NULL` · 1시간 이내)이 WHERE 에 들어간다.
    없으면 오래된 ephemeral 을 다시 눌러 **이 기능의 유일한 산출물이 조용히 덮어써진다.**
    가드에 걸리면 False 를 돌려주고 부른 쪽이 사용자에게 알린다 — 조용한 무시는 안 된다.
    """
    if reason not in REASONS:
        raise ValueError(f"알 수 없는 사유 코드: {reason!r} (아는 것: {', '.join(REASONS)})")

    rows = await db.fetch_all(
        """
        UPDATE answer_vote SET reason = $1
         WHERE id = $2 AND verdict = 'down' AND reason IS NULL
           AND voted_at > now() - interval '1 hour'
        RETURNING id
        """,
        reason, vote_id)
    if not rows:
        counters["reason_rejected"] += 1
        log.info("feedback.reason_rejected", vote_id=vote_id)
        return False
    return True


async def tally(*, tenant: str) -> dict:
    """§5.3 의 판정 질의. **분모와 분자가 같은 모집단**이어야 한다.

    분자는 투표 **행 수**가 아니라 `COUNT(DISTINCT answer_key)` 다 — 행으로 세면 재클릭이
    쌓여 한 사람의 망설임 한 번이 문턱을 넘긴다. 서로 다른 답변을 셀 수 있는 것은 안 B 의
    메시지 결속 덕분이다.
    """
    offered = await db.fetch_one(
        "SELECT count(*) AS n FROM answer_offered WHERE tenant = $1 AND NOT synthesized", tenant)
    synth = await db.fetch_one(
        "SELECT count(*) AS n FROM answer_offered WHERE tenant = $1 AND synthesized", tenant)
    voted = await db.fetch_one(
        """
        SELECT count(DISTINCT v.answer_key) AS n
          FROM answer_vote v
          JOIN answer_offered o USING (tenant, answer_key)
         WHERE v.tenant = $1 AND NOT o.synthesized
        """, tenant)
    return {"offered": offered["n"], "answers_with_votes": voted["n"],
            "synthesized": synth["n"]}


async def purge_pointers(*, now: datetime | None = None) -> int:
    """90일 지난 행의 **포인터만** 지운다. 수와 사유 코드는 남는다 (§4 I12).

    안 B 채택으로 `channel_id`·`message_ts` 가 질문자 추정 경로가 됐다. "저장하는 것이 수와
    사유 코드뿐이라 만료가 필요 없다" 는 안 A 시절 문장이고 지금은 거짓이다.
    """
    cutoff = (now or datetime.now(timezone.utc)) - POINTER_TTL
    rows = await db.fetch_all(
        """
        UPDATE answer_offered SET channel_id = NULL, message_ts = NULL
         WHERE offered_at < $1 AND (channel_id IS NOT NULL OR message_ts IS NOT NULL)
        RETURNING answer_key
        """, cutoff)
    if rows:
        log.info("feedback.pointers_purged", count=len(rows))
    return len(rows)
