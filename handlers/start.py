from __future__ import annotations

import os
from aiogram import Router, types, F
from aiogram.filters import CommandStart
from aiogram.utils.keyboard import InlineKeyboardBuilder

from models.user import User
from models.subscription import Subscription, TIERS

router = Router(name="start")

WEBAPP_URL = os.getenv("WEBAPP_URL", "https://your-domain.com")


def main_menu_keyboard() -> types.InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🎬 Создать комнату", callback_data="menu:create")
    builder.button(text="🔑 Войти в комнату", callback_data="menu:join")
    builder.button(text="📋 Мои комнаты", callback_data="menu:rooms")
    builder.button(text="💳 Подписка", callback_data="menu:subscribe")
    builder.button(text="👤 Профиль", callback_data="menu:profile")
    builder.adjust(1)
    return builder.as_markup()


def back_button(callback_data: str = "menu:main") -> types.InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="← Назад", callback_data=callback_data)
    return builder.as_markup()


@router.message(CommandStart())
async def cmd_start(message: types.Message) -> None:
    user = User(
        telegram_id=message.from_user.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
    )
    user.save()

    sub = Subscription.get_by_telegram_id(message.from_user.id)

    await message.answer(
        f"👋 Привет, {message.from_user.first_name}!\n\n"
        f"Я — бот для совместного просмотра видео.\n"
        f"💳 Тариф: <b>{sub.tier.upper()}</b>",
        reply_markup=main_menu_keyboard(),
        parse_mode="HTML",
    )


@router.callback_query(F.data == "menu:main")
async def callback_main_menu(callback: types.CallbackQuery) -> None:
    sub = Subscription.get_by_telegram_id(callback.from_user.id)
    await callback.message.edit_text(
        f"👋 Привет, {callback.from_user.first_name}!\n\n"
        f"Я — бот для совместного просмотра видео.\n"
        f"💳 Тариф: <b>{sub.tier.upper()}</b>",
        reply_markup=main_menu_keyboard(),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data == "menu:create")
async def callback_create(callback: types.CallbackQuery) -> None:
    from models.room import Room

    user = User(
        telegram_id=callback.from_user.id,
        username=callback.from_user.username,
        first_name=callback.from_user.first_name,
    )
    user.save()

    sub = Subscription.get_by_telegram_id(callback.from_user.id)
    room = Room.create(creator_id=callback.from_user.id)
    room.add_member(callback.from_user.id)

    builder = InlineKeyboardBuilder()
    builder.button(
        text="🎬 Открыть киновечер",
        web_app=types.WebAppInfo(url=f"{WEBAPP_URL}?room={room.code}&tier={sub.tier}"),
    )
    builder.button(text="← Назад", callback_data="menu:main")
    builder.adjust(1)

    bot_username = (await callback.bot.me()).username

    await callback.message.edit_text(
        f"🎉 Комната создана!\n\n"
        f"📌 Код: <code>{room.code}</code>\n"
        f"👥 Лимит: {sub.max_members} ({sub.tier.upper()})\n"
        f"🔗 Пригласи друга:\nhttps://t.me/{bot_username}?start=join_{room.code}",
        reply_markup=builder.as_markup(),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data == "menu:rooms")
async def callback_rooms(callback: types.CallbackQuery) -> None:
    from models.room import Room

    user_rooms = Room.get_user_rooms(callback.from_user.id)
    builder = InlineKeyboardBuilder()

    if not user_rooms:
        builder.button(text="← Назад", callback_data="menu:main")
        await callback.message.edit_text(
            "📋 У тебя нет активных комнат.\nСоздай новую!",
            reply_markup=builder.as_markup(),
        )
    else:
        for room in user_rooms:
            members = room.get_members()
            builder.button(
                text=f"🚪 {room.title} ({room.code}) — {len(members)} чел.",
                callback_data=f"room:{room.code}",
            )
        builder.button(text="← Назад", callback_data="menu:main")
        builder.adjust(1)
        await callback.message.edit_text(
            "📋 Твои комнаты:",
            reply_markup=builder.as_markup(),
        )
    await callback.answer()


@router.callback_query(F.data.startswith("room:leave:"))
async def callback_leave_room(callback: types.CallbackQuery) -> None:
    from models.room import Room

    code = callback.data.split(":", 2)[2]
    room = Room.get_by_code(code)
    if room:
        room.remove_member(callback.from_user.id)

    builder = InlineKeyboardBuilder()
    builder.button(text="← Назад", callback_data="menu:rooms")
    await callback.message.edit_text(
        f"🚪 Ты вышел из комнаты {code}.",
        reply_markup=builder.as_markup(),
    )
    await callback.answer("Ты вышел из комнаты.", show_alert=True)


@router.callback_query(F.data.startswith("room:"))
async def callback_room(callback: types.CallbackQuery) -> None:
    from models.room import Room

    code = callback.data.split(":", 1)[1]
    room = Room.get_by_code(code)
    if room is None:
        await callback.answer("Комната не найдена.", show_alert=True)
        return

    sub = Subscription.get_by_telegram_id(callback.from_user.id)
    members = room.get_members()
    member_names = ", ".join(
        m["first_name"] or m["username"] or str(m["telegram_id"]) for m in members
    )

    builder = InlineKeyboardBuilder()
    builder.button(
        text="🎬 Открыть",
        web_app=types.WebAppInfo(url=f"{WEBAPP_URL}?room={room.code}&tier={sub.tier}"),
    )
    builder.button(
        text="🚪 Выйти",
        callback_data=f"room:leave:{room.code}",
    )
    builder.button(text="← Назад", callback_data="menu:rooms")
    builder.adjust(1)

    await callback.message.edit_text(
        f"📌 {room.title} ({room.code})\n"
        f"👥 Участники ({len(members)}): {member_names}",
        reply_markup=builder.as_markup(),
        parse_mode="HTML",
    )
    await callback.answer()
