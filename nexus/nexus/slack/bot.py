"""Slack Bot — Nexus 검색/답변 연동. SPEC-nexus-slack-bot §4.2·§4.3.

Slack의 @nexus 멘션 또는 DM에 반응해 /search/answer 를 호출하고 Block Kit 으로 응답한다.

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
from nexus.slack.messages import Outcome, message_for

logger = logging.getLogger(__name__)

NEXUS_API_URL = os.getenv("NEXUS_API_URL", "http://localhost:8000")
NEXUS_SLACK_TOKEN = os.getenv("NEXUS_SLACK_TOKEN", "")
_CLEARANCE = os.getenv("NEXUS_SLACK_CLEARANCE", "PUBLIC")   # 워크스페이스 전원에게 확장하는 신뢰 바닥


class NexusCallError(Exception):
    """Nexus 호출이 답을 못 냈다. outcome 이 어느 대상에게 무슨 말을 할지 정한다."""

    def __init__(self, outcome: Outcome):
        super().__init__(outcome.value)
        self.outcome = outcome


def _transport():  # pragma: no cover - 테스트가 MockTransport 로 override
    """httpx transport. 기본 None → 실제 네트워크. 테스트는 MockTransport 를 주입한다."""
    return None


async def handle_mention(event: dict, say) -> None:
    """app_mention 이벤트 핸들러."""
    query = _extract_query(event.get("text", ""))
    if not query:
        await say(text="검색할 내용을 입력해주세요. 예: `@nexus 결제 서비스 장애 원인?`")
        return
    await _answer(query, say, event)


async def handle_dm(event: dict, say) -> None:
    """DM 메시지 핸들러. 멘션 없이 직접 질문."""
    text = event.get("text", "").strip()
    if not text:
        return
    await _answer(text, say, event)


async def _answer(query: str, say, event: dict) -> None:
    thread_ts = event.get("thread_ts") or event.get("ts")
    try:
        answer_data = await _call_nexus_api(query)
        await say(blocks=format_answer(answer_data), thread_ts=thread_ts)
    except NexusCallError as e:
        # 401 은 운영자를 위해 로그로도 남긴다(사용자 메시지와 별개).
        if e.outcome is Outcome.BAD_TOKEN:
            logger.error("nexus_auth_failed_check_NEXUS_SLACK_TOKEN")
        await say(text=message_for(e.outcome), thread_ts=thread_ts)
    except Exception:
        logger.error("nexus_call_unexpected", exc_info=True)
        await say(text=message_for(Outcome.OTHER), thread_ts=thread_ts)


def _extract_query(text: str) -> str:
    """Slack 멘션(<@U12345>)을 제거하고 순수 쿼리를 추출."""
    return re.sub(r"<@[A-Z0-9]+>", "", text).strip()


def _documents_count() -> int:
    """코퍼스가 비었는지 판단용. /status 의 documents_count. 실패 시 -1(=모름)."""
    try:
        with httpx.Client(timeout=5.0, transport=_transport()) as client:
            r = client.get(f"{NEXUS_API_URL}/status",
                           headers={"Authorization": f"Bearer {NEXUS_SLACK_TOKEN}"})
        return int(r.json().get("data", {}).get("documents_count", -1))
    except Exception:  # noqa: BLE001 — 모르면 -1, EMPTY_CORPUS 로 단정하지 않는다
        return -1


async def _call_nexus_api(query: str) -> dict:
    """Nexus /search/answer 호출. 실패는 NexusCallError(outcome) 로 분류해 올린다."""
    async with httpx.AsyncClient(timeout=60.0, transport=_transport()) as client:
        resp = await client.post(
            f"{NEXUS_API_URL}/search/answer",
            headers={"Authorization": f"Bearer {NEXUS_SLACK_TOKEN}"},   # ← 봇 존재 내내 없던 것
            json={
                "query": query, "top_k": 10, "route": "auto",
                "classification_max": _CLEARANCE, "tenant": "default",
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
        logger.error("nexus_llm_generation_failed")
        raise NexusCallError(Outcome.GENERATION_FAILED)

    if not payload.get("evidence_snippets"):
        # 근거 0건의 세 가지 원인은 서로 다른 사실이고, 고칠 사람도 다르다.
        if payload.get("no_visible_documents"):
            # 등급/테넌트 설정 결함 — 사용자가 질문을 바꿔도 영원히 0건이다. 운영자 몫이라
            # 로그로도 남긴다.
            logger.error("nexus_no_visible_documents_check_NEXUS_SLACK_CLEARANCE")
            raise NexusCallError(Outcome.NO_VISIBLE_DOCS)
        raise NexusCallError(
            Outcome.EMPTY_CORPUS if _documents_count() == 0 else Outcome.EMPTY_GROUNDING)

    return payload
