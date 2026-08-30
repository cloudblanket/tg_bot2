from __future__ import annotations

import os
from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from models.user import User
from models.room import Room, Video
from models.subscription import Subscription

router = Router(name="room")

WEBAPP_URL = os.getenv("WEBAPP_URL", "https://your-domain.com")


class JoinState(StatesGroup):
    waiting_code = State()


@router.message(JoinState.waiting_code, F.text)
async def process_join_code(message: types.Message, state: FSMContext) -> None:
    await state.clear()
    code = message.text.strip()

    user = User(
        telegram_id=message.from_user.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
    )
    user.save()

    room = Room.get_by_code(code)
    if room is None:
        builder = InlineKeyboardBuilder()
        builder.button(text="← Назад", callback_data="menu:main")
        await message.answer(
            "❌ Комната не найдена.",
            reply_markup=builder.as_markup(),
        )
        return

    if not room.is_active:
        builder = InlineKeyboardBuilder()
        builder.button(text="← Назад", callback_data="menu:main")
        await message.answer(
            "❌ Комната закрыта.",
            reply_markup=builder.as_markup(),
        )
        return

    sub = Subscription.get_by_telegram_id(message.from_user.id)

    if not room.add_member(message.from_user.id):
        await message.answer(
            f"⚠️ Комната заполнена (макс. {sub.max_members}). /subscribe"
        )
        return

    builder = InlineKeyboardBuilder()
    builder.button(
        text="🎬 Открыть киновечер",
        web_app=types.WebAppInfo(url=f"{WEBAPP_URL}?room={room.code}&tier={sub.tier}"),
    )
    builder.button(text="← Назад", callback_data="menu:main")
    builder.adjust(1)

    await message.answer(
        f"✅ Ты в комнате <code>{room.code}</code>!\n📌 {room.title}",
        reply_markup=builder.as_markup(),
        parse_mode="HTML",
    )


@router.callback_query(F.data == "menu:join")
async def callback_join(callback: types.CallbackQuery, state: FSMContext) -> None:
    builder = InlineKeyboardBuilder()
    builder.button(text="← Назад", callback_data="menu:main")
    await callback.message.edit_text(
        "🔑 Введи код комнаты:",
        reply_markup=builder.as_markup(),
    )
    await state.set_state(JoinState.waiting_code)
    await callback.answer()
