from __future__ import annotations

import json
import logging
from typing import Any

from aiogram import Router, types, F
from aiogram.utils.keyboard import InlineKeyboardBuilder

from models.user import User
from models.room import Room, Video

router = Router(name="webapp")
logger = logging.getLogger(__name__)


@router.message(F.web_app_data)
async def handle_webapp_data(message: types.Message) -> None:
    try:
        data = json.loads(message.web_app_data.data)
    except json.JSONDecodeError:
        logger.warning("Invalid WebApp data: %s", message.web_app_data.data)
        return

    action = data.get("action")
    room_code = data.get("room_code")

    if not action or not room_code:
        return

    room = Room.get_by_code(room_code)
    if room is None:
        await message.answer("❌ Комната не найдена.")
        return

    if action == "add_video":
        await _handle_add_video(message, data, room)
    elif action == "play":
        await _handle_play(message, data, room)
    elif action == "pause":
        await _handle_pause(message, data, room)
    elif action == "seek":
        await _handle_seek(message, data, room)
    elif action == "chat":
        await _handle_chat(message, data, room)


async def _handle_add_video(message: types.Message, data: dict[str, Any], room: Room) -> None:
    url = data.get("url", "").strip()
    if not url:
        await message.answer("❌ Укажи ссылку на видео.")
        return

    video_id = Video.extract_video_id(url)
    if video_id is None:
        # Пока принимаем любую ссылку (может быть не YouTube)
        # TODO: добавить валидацию для других платформ
        pass

    video = Video(
        room_id=room.id,
        youtube_url=url,
        title=data.get("title", "Видео"),
        added_by=message.from_user.id,
    )
    video.save()

    if room.current_video_id is None:
        room.set_current_video(video.id)

    await message.answer(
        f"🎬 Видео добавлено: {data.get('title', url)}\n"
        f"📌 Сейчас играет для {room.member_count()} участник(а/ов)."
    )


async def _handle_play(message: types.Message, data: dict[str, Any], room: Room) -> None:
    timestamp = data.get("timestamp", 0)
    members = room.get_members()

    builder = InlineKeyboardBuilder()
    for member in members:
        if member["telegram_id"] != message.from_user.id:
            builder.button(
                text=f"▶️ Play → {member['first_name'] or member['username']}",
                callback_data=f"sync:play:{room.code}:{timestamp}",
            )

    await message.answer(
        f"▶️ {message.from_user.first_name} нажал Play (таймкод: {int(timestamp)}с)"
    )


async def _handle_pause(message: types.Message, data: dict[str, Any], room: Room) -> None:
    timestamp = data.get("timestamp", 0)
    await message.answer(
        f"⏸ {message.from_user.first_name} нажал Pause (таймкод: {int(timestamp)}с)"
    )


async def _handle_seek(message: types.Message, data: dict[str, Any], room: Room) -> None:
    timestamp = data.get("timestamp", 0)
    await message.answer(
        f"⏩ {message.from_user.first_name} перемотал на {int(timestamp)}с"
    )


async def _handle_chat(message: types.Message, data: dict[str, Any], room: Room) -> None:
    text = data.get("text", "").strip()
    if not text:
        return

    members = room.get_members()
    for member in members:
        if member["telegram_id"] != message.from_user.id:
            try:
                await message.bot.send_message(
                    chat_id=member["telegram_id"],
                    text=f"💬 {message.from_user.first_name}: {text}",
                )
            except Exception as e:
                logger.warning("Failed to send chat to %s: %s", member["telegram_id"], e)

    await message.answer(f"💬 Сообщение отправлено ({len(members) - 1} участникам)")
