"""Slack Bot — Nexus 검색/답변 연동. SPEC-nexus-slack-bot §4.2·§4.3.

Slack의 @khala 멘션 또는 DM에 반응해 /search/answer 를 호출하고 Block Kit 으로 응답한다.

인증(§4.2): 모든 호출에 Authorization: Bearer <NEXUS_SLACK_TOKEN>. 봇은 하나의 읽기 전용
서비스 principal 로 붙는다. 토큰이 없으면 app.main() 이 시동을 거부한다(여기서 401 루프가 아니라).

환경 변수:
    SLACK_BOT_TOKEN / SLACK_APP_TOKEN: Slack 앱 (Socket Mode)
    NEXUS_SLACK_TOKEN: Nexus bearer (읽기 전용 principal)
    NEXUS_API_URL: Nexus API 주소 (기본: http://localhost:8000)
"""

from __future__ import annotations

import logging
import os
import re

import httpx

from nexus.slack.formatter import format_answer
from nexus.slack import feedback as fb
from nexus.slack.commands import is_scope_command, scope_blocks
from nexus.slack.messages import Outcome, message_for
from nexus.slack.thread import read_history

logger = logging.getLogger(__name__)

NEXUS_API_URL = os.getenv("NEXUS_API_URL", "http://localhost:8000")
NEXUS_SLACK_TOKEN = os.getenv("NEXUS_SLACK_TOKEN", "")
_CLEARANCE = os.getenv("NEXUS_SLACK_CLEARANCE", "PUBLIC")   # 워크스페이스 전원에게 확장하는 신뢰 바닥


#: 서버가 분류한 실패 사유 → 사용자에게 할 말. **봇은 공급자 문구를 문자열 매칭하지 않는다** —
#: 그 문구는 공급자가 바꾸고, 그때 조용히 오분류가 시작된다. 분류는 서버가 예외를 보는 그
#: 자리에서 한 번만 한다(nexus/llm/failure.py).
#: 모르는 사유는 매핑하지 않는다 — `GENERATION_FAILED` 로 떨어지고, 그것은 "기다리면 된다"
#: 라고 말하지 않는다.
_OUTCOME_BY_REASON = {
    "quota": Outcome.LLM_QUOTA,
    "auth": Outcome.LLM_AUTH,
    "rate_limit": Outcome.LLM_BUSY,
    "unavailable": Outcome.LLM_BUSY,
}


class NexusCallError(Exception):
    """Nexus 호출이 답을 못 냈다. outcome 이 어느 대상에게 무슨 말을 할지 정한다."""

    def __init__(self, outcome: Outcome):
        super().__init__(outcome.value)
        self.outcome = outcome


def _transport():  # pragma: no cover - 테스트가 MockTransport 로 override
    """httpx transport. 기본 None → 실제 네트워크. 테스트는 MockTransport 를 주입한다."""
    return None


async def handle_mention(event: dict, say, client=None) -> None:
    """app_mention 이벤트 핸들러."""
    query = _extract_query(event.get("text", ""))
    if not query:
        await say(text="검색할 내용을 입력해주세요. 예: `@khala 결제 서비스 장애 원인?`")
        return
    await _answer(query, say, event, client)


async def handle_dm(event: dict, say, client=None) -> None:
    """DM 메시지 핸들러. 멘션 없이 직접 질문."""
    text = event.get("text", "").strip()
    if not text:
        return
    await _answer(text, say, event, client)


async def _answer(query: str, say, event: dict, client=None) -> None:
    thread_ts = event.get("thread_ts") or event.get("ts")
    # **자기 자신에 대한 질문은 검색으로 답하지 않는다.** 검색하면 "그 주제를 다루는 문서" 가
    # 뽑혀 그 산문이 시스템 상태인 것처럼 나간다 (2026-08-13 실측). 완전 일치 명령어만 —
    # 분류는 하지 않는다 (SPEC-nexus-multi-turn-narration §3.2 가 기각한 설계).
    token = token_for(event.get("channel"))
    if is_scope_command(query):
        await say(blocks=scope_blocks(_visibility(token)), thread_ts=thread_ts)
        return
    # 앞선 턴들. 못 읽으면 빈 목록이고, 그러면 오늘과 같은 단발 질의가 된다 —
    # 이력 하나 때문에 답을 못 주지 않는다 (nexus/slack/thread.py).
    history = await read_history(client, event) if client is not None else []
    try:
        answer_data = await _call_nexus_api(query, history=history, token=token)
        # 답변마다 새 키. 버튼은 이 값을 들고 나가고, 투표는 **게시된 그 메시지**에만 묶인다
        # (SPEC-nexus-answer-feedback §3.2). 키는 게시 전에 필요하고 (채널, ts) 는 게시
        # 후에야 알 수 있으므로, 제안 행은 게시 뒤에 남긴다.
        answer_key = fb.issue_key()
        posted = await say(blocks=format_answer(answer_data) + fb.feedback_blocks(answer_key),
                           thread_ts=thread_ts)
        await _record_offer(answer_key, posted, event)
    except NexusCallError as e:
        # 401 은 운영자를 위해 로그로도 남긴다(사용자 메시지와 별개).
        if e.outcome is Outcome.BAD_TOKEN:
            logger.error("nexus_auth_failed_check_NEXUS_SLACK_TOKEN")
        await say(text=message_for(e.outcome), thread_ts=thread_ts)
    except Exception:
        logger.error("nexus_call_unexpected", exc_info=True)
        await say(text=message_for(Outcome.OTHER), thread_ts=thread_ts)


async def _record_offer(answer_key: str, posted, event: dict) -> None:
    """제안 행(분모) 한 줄. **best-effort** — 여기서 예외가 나가면 피드백이 답변을 죽인다.

    `say()` 가 응답을 안 돌려주는 표면도 있다(테스트 더블 등). 그때는 결속할 (채널, ts) 가
    없으므로 **제안 행을 만들지 않는다** — 결속 없는 행은 I10 이 막으려는 무기명 자격증명을
    되살린다. 투표가 오면 `record_vote` 가 orphan 으로 받아 표시한다.
    """
    try:
        ts = (posted or {}).get("ts")
        channel = (posted or {}).get("channel") or event.get("channel")
        if not ts or not channel:
            logger.warning("feedback_offer_skipped_no_message_handle")
            return
        await fb.record_offer(answer_key=answer_key, channel_id=channel, message_ts=ts)
    except Exception:  # noqa: BLE001 — 답변은 이미 나갔다
        logger.warning("feedback_offer_failed", exc_info=True)


def _corpus_tokens() -> dict[str, str]:
    """별칭 → bearer. `NEXUS_SLACK_CORPUS_<별칭> = 토큰|테넌트[|등급]` 에서 읽는다.

    서버도 **같은 변수**에서 principal 을 만든다(`auth/config.py`) — 봇이 보내는 토큰과 서버가
    아는 토큰이 어긋나는 상태를 표현 불가능하게 두는 규율이 여기서도 그대로다.
    """
    out = {}
    for key, raw in os.environ.items():
        if key.startswith("NEXUS_SLACK_CORPUS_") and raw.strip():
            alias = key[len("NEXUS_SLACK_CORPUS_"):].strip().lower()
            token = raw.split("|")[0].strip()
            if alias and token:
                out[alias] = token
    return out


def _channel_aliases() -> dict[str, str]:
    """채널 ID → 별칭. `NEXUS_SLACK_CHANNELS = C123:design,C456:ops`."""
    out = {}
    for pair in os.getenv("NEXUS_SLACK_CHANNELS", "").split(","):
        if ":" in pair:
            channel, alias = pair.split(":", 1)
            if channel.strip() and alias.strip():
                out[channel.strip()] = alias.strip().lower()
    return out


def token_for(channel_id: str | None) -> str:
    """이 채널의 질문이 어느 코퍼스로 가는가 — **토큰이 곧 코퍼스다.**

    요청 본문의 `tenant` 는 서버가 무시한다(`auth/scope.py` — 테넌트는 principal 의 것이고
    요청은 넓힐 수 없다). 그러니 채널별로 코퍼스를 가르는 유일한 방법은 토큰을 가르는 것이다.

    매핑에 없는 채널은 기본 토큰으로 간다 — 새 채널이 생겼다고 봇이 침묵하면 안 된다.
    별칭이 매핑에 있는데 그 토큰이 없으면(오타·미설정) 역시 기본으로 간다: **조용히 다른
    코퍼스를 뒤지는 것보다 낫다** 는 판단이 아니라, 그 반대가 더 나쁘기 때문이다 — 없는 토큰으로
    401 을 내면 사용자에게는 그냥 고장으로 보인다.
    """
    alias = _channel_aliases().get(channel_id or "")
    if not alias:
        return NEXUS_SLACK_TOKEN
    return _corpus_tokens().get(alias) or NEXUS_SLACK_TOKEN


def _extract_query(text: str) -> str:
    """Slack 멘션(<@U12345>)을 제거하고 순수 쿼리를 추출."""
    return re.sub(r"<@[A-Z0-9]+>", "", text).strip()


def _documents_count(token: str | None = None) -> int:
    """코퍼스가 비었는지 판단용. /status 의 documents_count. 실패 시 -1(=모름)."""
    try:
        with httpx.Client(timeout=5.0, transport=_transport()) as client:
            r = client.get(f"{NEXUS_API_URL}/status",
                           headers={"Authorization": f"Bearer {token or NEXUS_SLACK_TOKEN}"})
        return int(r.json().get("data", {}).get("documents_count", -1))
    except Exception:  # noqa: BLE001 — 모르면 -1, EMPTY_CORPUS 로 단정하지 않는다
        return -1


def _visibility(token: str | None = None) -> dict:
    """`/visibility` 응답. 실패하면 빈 dict — 진단이 답변을 막지 않는다.

    **토큰을 받는 이유**: 이 봇은 채널마다 다른 코퍼스에 물을 수 있고, 진단이 답변과
    다른 토큰으로 나가면 *다른 코퍼스*의 상태를 보고한다. 이 리포는 계측기가 대상을
    잘못 겨눈 실패를 여러 번 겪었다.
    """
    try:
        with httpx.Client(timeout=5.0, transport=_transport()) as client:
            r = client.get(f"{NEXUS_API_URL}/visibility",
                           headers={"Authorization": f"Bearer {token or NEXUS_SLACK_TOKEN}"})
        return r.json().get("data", {}) or {}
    except Exception:  # noqa: BLE001
        return {}


def _blind(token: str | None = None) -> bool:
    """**이 봇의 등급으로** 볼 수 있는 문서가 한 건도 없는가.

    0건을 받았을 때만 묻는다 — 검색 경로에 얹으면 모든 질의가 이 왕복을 낸다. 실패하면 False:
    모르는 것을 설정 결함이라고 단정하면 멀쩡한 검색 실패가 운영자 호출이 된다.
    """
    return bool(_visibility(token).get("no_visible_documents", False))


async def _call_nexus_api(query: str, history: list[dict] | None = None,
                          token: str | None = None) -> dict:
    """Nexus /search/answer 호출. 실패는 NexusCallError(outcome) 로 분류해 올린다."""
    async with httpx.AsyncClient(timeout=60.0, transport=_transport()) as client:
        resp = await client.post(
            f"{NEXUS_API_URL}/search/answer",
            headers={"Authorization": f"Bearer {token or NEXUS_SLACK_TOKEN}"},  # 토큰이 곧 코퍼스다
            json={
                "query": query, "top_k": 10, "route": "auto",
                # `tenant` 는 보내지 않는다 — 서버가 무시한다(`auth/scope.py`). 보내면 봇이
                # 코퍼스를 고르는 것처럼 보이고, 실제로 고르는 것은 **토큰**이다.
                "classification_max": _CLEARANCE,
                # 서버는 U2 에서 이것을 받아서 버린다(상한만 건다). 자르기는 이미 했다.
                "history": history or [],
            },
        )

    if resp.status_code == 401:
        raise NexusCallError(Outcome.BAD_TOKEN)
    if resp.status_code == 503:
        raise NexusCallError(Outcome.UNAVAILABLE)
    if resp.status_code != 200:
        # 429·500·malformed 등 — 스택트레이스가 아니라 일반 메시지로.
        raise NexusCallError(Outcome.OTHER)

    data = resp.json()
    if not data.get("success"):
        raise NexusCallError(Outcome.OTHER)

    payload = data["data"]

    # **생성 실패를 답변으로 내보내지 않는다.** 서버는 LLM 이 죽으면 `answer` 자리에 근거 원문
    # 덤프를 넣는다(llm/answer.py). 근거가 있으니 아래 분기는 통과하고, 사용자는 실패를 답변으로
    # 읽는다. 2026-08-13 크레딧 소진 때 실제로 그 덤프가 슬랙으로 나갔다.
    if payload.get("llm_failed"):
        reason = payload.get("llm_failure_reason")
        logger.error("nexus_llm_generation_failed", extra={"reason": reason})
        raise NexusCallError(_OUTCOME_BY_REASON.get(reason, Outcome.GENERATION_FAILED))

    if not payload.get("evidence_snippets"):
        # 근거 0건의 세 가지 원인은 서로 다른 사실이고, 고칠 사람도 다르다. 여기서만 서버에
        # 되묻는다 — 답이 나온 질의에는 이 왕복이 붙지 않는다.
        if _documents_count(token) == 0:
            raise NexusCallError(Outcome.EMPTY_CORPUS)
        if _blind(token):
            # 등급/테넌트 설정 결함 — 사용자가 질문을 바꿔도 영원히 0건이다. 운영자 몫이라
            # 로그로도 남긴다.
            logger.error("nexus_no_visible_documents_check_NEXUS_SLACK_CLEARANCE")
            raise NexusCallError(Outcome.NO_VISIBLE_DOCS)
        raise NexusCallError(Outcome.EMPTY_GROUNDING)

    return payload
