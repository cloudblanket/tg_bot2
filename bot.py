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
from handlers.room import router as room_router
from handlers.webapp import router as webapp_router
from handlers.subscribe import router as subscribe_router
from handlers.upload import router as upload_router

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
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


async def main() -> None:
    bot = create_bot()
    dp = Dispatcher(storage=MemoryStorage())

    @dp.error()
    async def error_handler(event):
        logger.error("Handler error: %s", event.exception, exc_info=True)

    dp.include_router(start_router)
    dp.include_router(room_router)
    dp.include_router(subscribe_router)
    dp.include_router(upload_router)
    dp.include_router(webapp_router)

    me = await bot.get_me()
    logger.info("Bot: @%s (ID: %s)", me.username, me.id)

    await dp.start_polling(bot)


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

    asyncio.run(main())
