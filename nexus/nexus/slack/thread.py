"""슬랙에서 대화 이력을 읽어 온다 (SPEC-nexus-multi-turn-retrieval §1.3, U2 의 남은 절반).

슬랙이 웹보다 쉬운 이유가 여기 있다: 대화 id 와 이력을 **슬랙이 이미 갖고 있어** 우리가 대화를
저장할 필요가 없다. 대신 공짜는 아니다 — 읽기 경로를 새로 만들어야 하고, history 스코프가
필요하고(앱 재설치), 후속 턴마다 API 호출이 붙는다.

**이력을 못 읽는 것은 답변 실패가 아니다.** 스코프가 없거나 레이트리밋에 걸리면 이력 없이
답한다 — 오늘과 같은 동작이다. 진단 하나 때문에 답을 못 주는 것이 더 나쁘다.

상한은 서버 정본(`nexus.search.history`)을 그대로 쓴다. 봇은 서버와 같은 파이썬이므로 웹처럼
값을 옮겨 적을 이유가 없고, 옮겨 적은 값은 반드시 갈라진다.
"""

from __future__ import annotations

import logging
import re

from nexus.search.history import MAX_BYTES, MAX_TURNS

logger = logging.getLogger(__name__)

#: 한 번에 읽어 올 슬랙 메시지 수. 상한(MAX_TURNS)보다 넉넉히 잡는다 — 빈 메시지·파일 공유·
#: 조인 알림처럼 이력이 아닌 것들이 섞여 있어서, 딱 맞춰 읽으면 걸러낸 뒤 모자란다.
_FETCH_LIMIT = 30

_MENTION = re.compile(r"<@[A-Z0-9]+>")


def _clean(text: str) -> str:
    """멘션 토큰을 뺀 본문. `<@U123> 질문` 은 사람에게도 "질문" 으로 읽힌다."""
    return _MENTION.sub("", text or "").strip()


def _role(message: dict) -> str:
    """봇이 쓴 것은 assistant, 사람이 쓴 것은 user.

    다른 봇의 메시지도 assistant 로 잡힌다. 스레드에 다른 봇이 끼는 경우는 드물고, 그것을
    가리려면 `auth.test` 로 우리 user_id 를 알아야 하는데 그 호출을 기동 경로에 넣는 값이
    이 정확도보다 크지 않다. 틀려도 이력의 역할 라벨 하나이지 답의 근거가 아니다.
    """
    return "assistant" if message.get("bot_id") or message.get("app_id") else "user"


def _usable(message: dict, *, exclude_ts: str | None) -> bool:
    """이력에 넣을 만한 메시지인가."""
    if message.get("ts") == exclude_ts:
        return False                      # 이번 질문 자체는 이력이 아니다
    if message.get("subtype"):
        return False                      # 조인·채널토픽·파일공유 등은 대화가 아니다
    return bool(_clean(message.get("text", "")))


def to_turns(messages: list[dict], *, exclude_ts: str | None = None) -> list[dict]:
    """슬랙 메시지 목록(오래된 것부터) → 서버가 받는 `history`.

    **뒤에서부터** 담아 상한을 맞춘다. 오래된 맥락보다 최근 맥락이 이번 질문을 푸는 데 쓰인다.
    자르는 판단은 여기서 명시적으로 한다 — 서버는 넘치면 자르지 않고 413 으로 거절한다.
    """
    usable = [m for m in messages if _usable(m, exclude_ts=exclude_ts)]
    out: list[dict] = []
    total = 0
    for m in reversed(usable):
        if len(out) >= MAX_TURNS:
            break
        content = _clean(m.get("text", ""))
        size = len(content.encode("utf-8"))
        if total + size > MAX_BYTES:
            break
        total += size
        out.insert(0, {"role": _role(m), "content": content})
    return out


async def read_history(client, event: dict) -> list[dict]:
    """이 이벤트가 속한 대화의 앞선 턴들. 읽을 수 없으면 빈 목록.

    두 경로가 있고, 대화가 어디에 사는지가 다르다:

    - **스레드 답장**(`thread_ts` 가 있고 이번 메시지가 그 뿌리가 아님) → `conversations.replies`.
      채널에서 멘션으로 시작한 대화가 이 모양이다.
    - **DM** → `conversations.history`. DM 에는 스레드가 없고 채널 자체가 대화다. 이것을 빼면
      DM 사용자는 영원히 단발 질의만 하게 된다 — 그리고 DM 이 가장 흔한 사용 방식이다.

    채널에서 스레드 없이 멘션한 첫 턴은 이력이 없다(맞다 — 첫 턴이다).
    """
    channel = event.get("channel")
    ts = event.get("ts")
    thread_ts = event.get("thread_ts")
    if not channel:
        return []

    try:
        if thread_ts and thread_ts != ts:
            resp = await client.conversations_replies(
                channel=channel, ts=thread_ts, limit=_FETCH_LIMIT)
        elif event.get("channel_type") == "im":
            resp = await client.conversations_history(channel=channel, limit=_FETCH_LIMIT)
        else:
            return []                     # 채널의 첫 멘션 — 앞선 턴이 없다
    except Exception as e:  # noqa: BLE001
        # missing_scope(앱 재설치 안 함)·ratelimited·네트워크. **답변을 막지 않는다** —
        # 이력 없이 답하면 오늘과 같은 동작이고, 그것이 이 기능의 degrade 경로다.
        logger.warning("slack_history_unavailable: %s — 이력 없이 답한다", e)
        return []

    messages = list(resp.get("messages") or [])
    # conversations.history 는 **최신순**으로 준다. replies 는 오래된 순이다. 뒤집는 것을
    # 잊으면 이력이 거꾸로 들어가고, 재작성기는 대화가 거꾸로 흐른다고 읽는다.
    if event.get("channel_type") == "im" and not (thread_ts and thread_ts != ts):
        messages.reverse()
    return to_turns(messages, exclude_ts=ts)
