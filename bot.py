from __future__ import annotations

import asyncio
import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / ".env")

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from handlers.start import router as start_router
from handlers.webapp import router as webapp_router
from handlers.subscribe import router as subscribe_router
from handlers.upload import router as upload_router

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
WEBAPP_URL = os.getenv("WEBAPP_URL", "")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
PROXY_URL = os.getenv("PROXY_URL", "")

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def create_bot() -> Bot:
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN not set!")
        sys.exit(1)

    session = None
    if PROXY_URL:
        from aiogram.client.session.aiohttp import AiohttpSession
        logger.info("Using proxy: %s", PROXY_URL)
        session = AiohttpSession(proxy=PROXY_URL)

    return Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
        session=session,
    )


bot = create_bot()
dp = Dispatcher(storage=MemoryStorage())

dp.include_router(start_router)
dp.include_router(subscribe_router)
dp.include_router(upload_router)
dp.include_router(webapp_router)


async def on_startup() -> None:
    from services.bot_instance import set_bot, set_dp, set_bot_username
    set_bot(bot)
    set_dp(dp)

    me = await bot.get_me()
    set_bot_username(me.username)
    logger.info("Bot: @%s (ID: %s)", me.username, me.id)

    if WEBAPP_URL:
        webhook_url = f"{WEBAPP_URL.rstrip('/')}/webhook"
        await bot.set_webhook(
            url=webhook_url,
            allowed_updates=["message", "callback_query", "web_app_data"],
        )
        logger.info("Webhook set: %s", webhook_url)
    else:
        logger.warning("WEBAPP_URL not set, webhook not configured")


async def on_shutdown() -> None:
    await bot.delete_webhook()
    logger.info("Webhook deleted")


def _run_web_server() -> None:
    from services.sync import app
    import uvicorn

    port = int(os.getenv("PORT", os.getenv("SYNC_PORT", "8765")))
    logger.info("Web server on port %d", port)
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="warning")


if __name__ == "__main__":
    import threading

    server_thread = threading.Thread(target=_run_web_server, daemon=True)
    server_thread.start()

    async def run():
        await on_startup()
        try:
            await asyncio.Event().wait()
        finally:
            await on_shutdown()

    asyncio.run(run())
