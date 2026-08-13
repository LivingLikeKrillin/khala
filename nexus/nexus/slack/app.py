"""Slack App 진입점.

Slack Bolt 프레임워크를 사용하여 이벤트를 수신한다.
Socket Mode로 동작하므로 public URL이 필요 없다.

실행:
    python -m nexus.slack.app

환경 변수:
    SLACK_BOT_TOKEN: xoxb-...
    SLACK_APP_TOKEN: xapp-... (Socket Mode용)
    NEXUS_SLACK_TOKEN: Nexus bearer (읽기 전용 principal) — 없으면 시동 거부
    NEXUS_API_URL: http://localhost:8000
"""

from __future__ import annotations

import asyncio
import logging
import os

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def main() -> None:
    """Slack Bot 시작."""
    # Nexus bearer 없이 시동하면 봇이 던지는 모든 질문이 401 이 된다 — 오늘의 조용한 실패.
    # slack_bolt import 보다 먼저 검사해서 그 침묵을 시동 거부로 바꾼다.
    if not os.getenv("NEXUS_SLACK_TOKEN"):
        logger.error(
            "NEXUS_SLACK_TOKEN 환경 변수가 필요합니다 — 봇은 Nexus 에 읽기 전용 principal 로 붙는다. "
            "nexus auth gen-token 으로 발급하세요."
        )
        raise SystemExit(1)

    try:
        from slack_bolt.async_app import AsyncApp
        from slack_bolt.adapter.socket_mode.async_handler import AsyncSocketModeHandler
    except ImportError as e:
        # **없는 모듈의 이름을 그대로 말한다.** 예전 문구는 무조건 "slack-bolt가 설치되지
        # 않았습니다" 였는데, 실제로 없던 것은 `aiohttp` 였다(slack_bolt.async_app 이 모듈
        # 최상단에서 그것을 import 한다). slack-bolt 는 멀쩡히 설치돼 있었으므로 그 문구는
        # 진단을 정확히 반대 방향으로 보냈다 — 있는 것을 없다고 말하는 오류 메시지는
        # 오류를 숨기는 것보다 나쁘다.
        logger.error(
            "Slack 런타임 import 실패: %s. "
            "이 이미지는 `pip install -e '.[slack]'` 로 빌드돼야 한다 "
            "(slack-bolt · slack-sdk · aiohttp).",
            e,
        )
        raise SystemExit(1)

    bot_token = os.getenv("SLACK_BOT_TOKEN")
    app_token = os.getenv("SLACK_APP_TOKEN")
    signing_secret = os.getenv("SLACK_SIGNING_SECRET", "")

    if not bot_token or not app_token:
        logger.error("SLACK_BOT_TOKEN과 SLACK_APP_TOKEN 환경 변수가 필요합니다")
        raise SystemExit(1)

    app = AsyncApp(token=bot_token, signing_secret=signing_secret)

    # ── 이벤트 핸들러 등록 ──

    @app.event("app_mention")
    async def on_mention(event, say, client):
        # `client` 는 Bolt 가 선언한 핸들러에만 넘겨준다 — 이것이 스레드 이력을 읽는 손이다.
        from nexus.slack.bot import handle_mention
        await handle_mention(event, say, client)

    @app.event("message")
    async def on_message(event, say, client):
        # DM만 처리 (채널 메시지는 멘션으로 처리)
        if event.get("channel_type") == "im":
            # Bot 자신의 메시지 무시
            if event.get("bot_id"):
                return
            from nexus.slack.bot import handle_dm
            await handle_dm(event, say, client)

    # ── Socket Mode 시작 ──

    async def start():
        handler = AsyncSocketModeHandler(app, app_token)
        logger.info("Nexus Slack Bot 시작 (Socket Mode)")
        await handler.start_async()

    asyncio.run(start())


if __name__ == "__main__":
    main()
