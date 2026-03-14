"""Slack App 진입점.

Slack Bolt 프레임워크를 사용하여 이벤트를 수신한다.
Socket Mode로 동작하므로 public URL이 필요 없다.

실행:
    python -m khala.slack.app

환경 변수:
    SLACK_BOT_TOKEN: xoxb-...
    SLACK_APP_TOKEN: xapp-... (Socket Mode용)
    KHALA_API_URL: http://localhost:8000
"""

from __future__ import annotations

import asyncio
import logging
import os

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def main() -> None:
    """Slack Bot 시작."""
    try:
        from slack_bolt.async_app import AsyncApp
        from slack_bolt.adapter.socket_mode.async_handler import AsyncSocketModeHandler
    except ImportError:
        logger.error(
            "slack-bolt가 설치되지 않았습니다. "
            "pip install 'slack-bolt[async]' slack-sdk 로 설치하세요."
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
    async def on_mention(event, say):
        from khala.slack.bot import handle_mention
        await handle_mention(event, say)

    @app.event("message")
    async def on_message(event, say):
        # DM만 처리 (채널 메시지는 멘션으로 처리)
        if event.get("channel_type") == "im":
            # Bot 자신의 메시지 무시
            if event.get("bot_id"):
                return
            from khala.slack.bot import handle_dm
            await handle_dm(event, say)

    # ── Socket Mode 시작 ──

    async def start():
        handler = AsyncSocketModeHandler(app, app_token)
        logger.info("Khala Slack Bot 시작 (Socket Mode)")
        await handler.start_async()

    asyncio.run(start())


if __name__ == "__main__":
    main()
