"""Slack Bot — Khala 검색/답변 연동.

Slack의 @khala 멘션 또는 DM에 반응하여 /search/answer를 호출하고
Block Kit 포맷으로 응답한다.

환경 변수:
    SLACK_BOT_TOKEN: xoxb-... (Bot User OAuth Token)
    SLACK_SIGNING_SECRET: Slack App의 Signing Secret
    KHALA_API_URL: Khala API 주소 (기본: http://localhost:8000)
"""

from __future__ import annotations

import logging
import os
import re

import httpx

from khala.slack.formatter import format_answer, format_error

logger = logging.getLogger(__name__)

KHALA_API_URL = os.getenv("KHALA_API_URL", "http://localhost:8000")
SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN", "")


async def handle_mention(event: dict, say) -> None:
    """app_mention 이벤트 핸들러.

    Args:
        event: Slack 이벤트 payload
        say: Slack say 함수 (응답 전송)
    """
    text = event.get("text", "")
    query = _extract_query(text)

    if not query:
        await say(text="검색할 내용을 입력해주세요. 예: `@khala 결제 서비스 장애 원인?`")
        return

    # 처리 중 표시
    thread_ts = event.get("thread_ts") or event.get("ts")

    try:
        answer_data = await _call_khala_api(query)
        blocks = format_answer(answer_data)
        await say(blocks=blocks, thread_ts=thread_ts)
    except Exception as e:
        logger.error("khala_api_call_failed", exc_info=True)
        blocks = format_error(str(e))
        await say(blocks=blocks, thread_ts=thread_ts)


async def handle_dm(event: dict, say) -> None:
    """DM 메시지 핸들러. 멘션 없이 직접 질문."""
    text = event.get("text", "").strip()
    if not text:
        return

    thread_ts = event.get("thread_ts") or event.get("ts")

    try:
        answer_data = await _call_khala_api(text)
        blocks = format_answer(answer_data)
        await say(blocks=blocks, thread_ts=thread_ts)
    except Exception as e:
        logger.error("khala_api_call_failed", exc_info=True)
        blocks = format_error(str(e))
        await say(blocks=blocks, thread_ts=thread_ts)


def _extract_query(text: str) -> str:
    """Slack 멘션 텍스트에서 @khala를 제거하고 순수 쿼리를 추출."""
    # <@U12345> 형태의 멘션 제거
    cleaned = re.sub(r"<@[A-Z0-9]+>", "", text).strip()
    return cleaned


async def _call_khala_api(query: str) -> dict:
    """Khala /search/answer API 호출.

    Returns:
        KhalaResponse.data 필드
    """
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(
            f"{KHALA_API_URL}/search/answer",
            json={
                "query": query,
                "top_k": 10,
                "route": "auto",
                "classification_max": "INTERNAL",
                "tenant": "default",
            },
        )

    if resp.status_code == 503:
        raise ConnectionError("Khala 데이터베이스에 연결할 수 없습니다")

    data = resp.json()
    if not data.get("success"):
        raise RuntimeError(data.get("error", f"API 오류 (HTTP {resp.status_code})"))

    return data["data"]
