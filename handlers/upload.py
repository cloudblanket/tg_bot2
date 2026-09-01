from __future__ import annotations

import os
import uuid
import logging
from pathlib import Path
from typing import Optional

from aiogram import Router, types, F
from aiogram.filters import Command

from models.user import User
from models.subscription import Subscription

router = Router(name="upload")
logger = logging.getLogger(__name__)

UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", str(Path(__file__).parent.parent / "data" / "uploads")))
MAX_FILE_SIZE = 350 * 1024 * 1024  # 350MB


def ensure_upload_dir() -> None:
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


@router.message(Command("upload"))
async def cmd_upload(message: types.Message) -> None:
    user = User.get_by_telegram_id(message.from_user.id)
    if user is None:
        await message.answer("❌ Сначала нажми /start")
        return

    sub = Subscription.get_by_telegram_id(message.from_user.id)
    if not sub.can_upload_video():
        await message.answer(
            "🔒 Загрузка видео доступна только по подписке.\n"
            "Используй /subscribe чтобы оформить."
        )
        return

    await message.answer(
        "📤 Отправь видео (до 50MB).\n"
        "Видео будет доступно одному зрителю и удалится после просмотра."
    )


@router.message(F.video)
async def handle_video_upload(message: types.Message) -> None:
    user = User.get_by_telegram_id(message.from_user.id)
    if user is None:
        await message.answer("❌ Сначала нажми /start")
        return

    sub = Subscription.get_by_telegram_id(message.from_user.id)
    if not sub.can_upload_video():
        await message.answer(
            "🔒 Загрузка видео доступна только по подписке.\n"
            "Используй /subscribe чтобы оформить."
        )
        return

    video = message.video
    if video.file_size > MAX_FILE_SIZE:
        await message.answer("❌ Видео слишком большое (макс. 50MB).")
        return

    ensure_upload_dir()

    file_id = str(uuid.uuid4())[:8]
    file_name = f"{file_id}.mp4"

    file = await message.bot.get_file(video.file_id)
    await message.bot.download_file(file.file_path, str(UPLOAD_DIR / file_name))

    webapp_url = os.getenv("WEBAPP_URL", "https://tg-bot2-1-wws5.onrender.com")
    view_url = f"{webapp_url}/view/{file_name}"

    await message.answer(
        f"✅ Видео загружено!\n\n"
        f"🔗 Ссылка для просмотра (1 раз):\n<code>{view_url}</code>\n\n"
        f"⚠️ Видео удалится сразу после просмотра.",
        parse_mode="HTML",
    )
