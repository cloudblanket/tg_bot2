from __future__ import annotations

import os
from aiogram import Router, types, F
from aiogram.filters import CommandStart
from aiogram.utils.keyboard import InlineKeyboardBuilder

from models.user import User
from models.subscription import Subscription

router = Router(name="start")

WEBAPP_URL = os.getenv("WEBAPP_URL", "https://your-domain.com")


@router.message(CommandStart())
async def cmd_start(message: types.Message) -> None:
    user = User(
        telegram_id=message.from_user.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
        is_premium=bool(message.from_user.is_premium),
    )
    user.save()

    sub = Subscription.get_by_telegram_id(message.from_user.id)

    builder = InlineKeyboardBuilder()
    builder.button(
        text="🎬 Открыть киновечер",
        web_app=types.WebAppInfo(url=WEBAPP_URL),
    )
    builder.adjust(1)

    await message.answer(
        f"👋 Привет, {message.from_user.first_name}!\n\n"
        f"Я — бот для совместного просмотра видео.\n"
        f"💳 Тариф: <b>{sub.tier.upper()}</b>\n\n"
        "🎬 Создай комнату командой /create\n"
        "🔗 Присоединись по коду /join КОД_КОМНАТЫ\n"
        "📋 Свои комнаты /rooms\n"
        "💳 Подписка /subscribe\n\n"
        "Или нажми кнопку ниже, чтобы открыть киновечер:",
        reply_markup=builder.as_markup(),
        parse_mode="HTML",
    )
