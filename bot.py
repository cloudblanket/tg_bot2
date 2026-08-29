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
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from handlers.start import router as start_router
from handlers.room import router as room_router
from handlers.webapp import router as webapp_router

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
        logger.error("BOT_TOKEN environment variable is not set!")
        sys.exit(1)

    session = None
    if PROXY_URL:
        logger.info("Using proxy: %s", PROXY_URL)
        session = AiohttpSession(proxy=PROXY_URL)

    return Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
        session=session,
    )


async def main() -> None:
    bot = create_bot()
    storage = MemoryStorage()
    dp = Dispatcher(storage=storage)

    dp.include_router(start_router)
    dp.include_router(room_router)
    dp.include_router(webapp_router)

    logger.info("Bot starting...")

    me = await bot.get_me()
    logger.info("Bot connected: @%s (ID: %s)", me.username, me.id)

    await dp.start_polling(bot)


def run_bot_async() -> None:
    asyncio.run(main())


# Запуск WebSocket сервера в отдельном потоке
def run_sync_server_in_thread() -> None:
    import threading
    from services.sync import app
    import uvicorn

    port = int(os.getenv("PORT", os.getenv("SYNC_PORT", "8765")))

    def _run():
        uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    logger.info("Sync server started on port %d", port)


if __name__ == "__main__":
    import threading

    # Запускаем бота в отдельном потоке
    bot_thread = threading.Thread(target=run_bot_async, daemon=True)
    bot_thread.start()

    # Запускаем веб-сервер как основной процесс (Render требует это)
    from services.sync import app
    import uvicorn

    port = int(os.getenv("PORT", os.getenv("SYNC_PORT", "8765")))
    logger.info("Web server starting on port %d", port)
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")
