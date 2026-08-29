from __future__ import annotations

import os
from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from models.user import User
from models.room import Room, Video

router = Router(name="room")

WEBAPP_URL = os.getenv("WEBAPP_URL", "https://your-domain.com")


class JoinState(StatesGroup):
    waiting_code = State()


@router.message(Command("create"))
async def cmd_create(message: types.Message) -> None:
    user = User(
        telegram_id=message.from_user.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
        is_premium=bool(message.from_user.is_premium),
    )
    user.save()

    room = Room.create(creator_id=message.from_user.id)
    room.add_member(message.from_user.id)

    builder = InlineKeyboardBuilder()
    builder.button(
        text="🎬 Открыть киновечер",
        web_app=types.WebAppInfo(url=f"{WEBAPP_URL}?room={room.code}"),
    )
    builder.adjust(1)

    await message.answer(
        f"🎉 Комната создана!\n\n"
        f"📌 Код комнаты: <code>{room.code}</code>\n"
        f"🔗 Ссылка-приглашение: https://t.me/{(await message.bot.me()).username}?start=join_{room.code}\n\n"
        f"Поделись кодом или ссылкой с друзьями!",
        reply_markup=builder.as_markup(),
        parse_mode="HTML",
    )


@router.message(Command("join"))
async def cmd_join(message: types.Message, state: FSMContext) -> None:
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await state.set_state(JoinState.waiting_code)
        await message.answer("🔑 Введи код комнаты:")
        return

    code = args[1].strip()
    await _join_room(message, code, state)


@router.message(JoinState.waiting_code)
async def process_join_code(message: types.Message, state: FSMContext) -> None:
    code = message.text.strip()
    await _join_room(message, code, state)


async def _join_room(message: types.Message, code: str, state: FSMContext) -> None:
    await state.clear()

    user = User(
        telegram_id=message.from_user.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
        is_premium=bool(message.from_user.is_premium),
    )
    user.save()

    room = Room.get_by_code(code)
    if room is None:
        await message.answer("❌ Комната не найдена. Проверь код и попробуй снова.")
        return

    if not room.is_active:
        await message.answer("❌ Эта комната уже закрыта.")
        return

    if not room.add_member(message.from_user.id):
        limit = "50" if user.is_premium else "5"
        await message.answer(
            f"⚠️ Комната заполнена (макс. {limit} участников).\n"
            "Попроси кого-то выйти или обнови тариф."
        )
        return

    builder = InlineKeyboardBuilder()
    builder.button(
        text="🎬 Открыть киновечер",
        web_app=types.WebAppInfo(url=f"{WEBAPP_URL}?room={room.code}"),
    )
    builder.adjust(1)

    await message.answer(
        f"✅ Ты присоединился к комнате <code>{room.code}</code>!\n"
        f"📌 Название: {room.title}",
        reply_markup=builder.as_markup(),
        parse_mode="HTML",
    )


@router.message(Command("leave"))
async def cmd_leave(message: types.Message) -> None:
    user_rooms = Room.get_user_rooms(message.from_user.id)
    if not user_rooms:
        await message.answer("Ты не состоишь ни в одной комнате.")
        return

    builder = InlineKeyboardBuilder()
    for room in user_rooms:
        builder.button(
            text=f"🚪 Выйти из {room.title} ({room.code})",
            callback_data=f"leave:{room.code}",
        )
    builder.adjust(1)

    await message.answer("Выбери комнату, из которой хочешь выйти:", reply_markup=builder.as_markup())


@router.callback_query(F.data.startswith("leave:"))
async def callback_leave(callback: types.CallbackQuery) -> None:
    code = callback.data.split(":", 1)[1]
    room = Room.get_by_code(code)
    if room is None:
        await callback.answer("Комната не найдена.", show_alert=True)
        return

    room.remove_member(callback.from_user.id)
    await callback.answer("Ты вышел из комнаты.", show_alert=True)
    await callback.message.edit_text(f"🚪 Ты вышел из комнаты {room.title} ({room.code}).")


@router.message(Command("rooms"))
async def cmd_rooms(message: types.Message) -> None:
    user_rooms = Room.get_user_rooms(message.from_user.id)
    if not user_rooms:
        await message.answer("У тебя нет активных комнат.\nСоздай новую: /create")
        return

    lines = ["📋 Твои комнаты:\n"]
    for room in user_rooms:
        members = room.get_members()
        member_names = ", ".join(
            m["first_name"] or m["username"] or str(m["telegram_id"]) for m in members
        )
        lines.append(
            f"• {room.title} ({room.code})\n"
            f"  👥 Участники: {len(members)} — {member_names}\n"
        )

    await message.answer("\n".join(lines))
