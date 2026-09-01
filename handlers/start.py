from __future__ import annotations

import os
from aiogram import Router, types, F
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from models.user import User
from models.subscription import Subscription, TIERS

router = Router(name="start")

WEBAPP_URL = os.getenv("WEBAPP_URL", "https://tg-bot2-1-wws5.onrender.com")


class CreateRoomState(StatesGroup):
    waiting_title = State()
    waiting_password = State()


class JoinState(StatesGroup):
    waiting_code = State()


class JoinPasswordState(StatesGroup):
    waiting_password = State()


def main_menu_keyboard() -> types.InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🎬 Создать комнату", callback_data="menu:create")
    builder.button(text="🔑 Войти в комнату", callback_data="menu:join")
    builder.button(text="📋 Мои комнаты", callback_data="menu:rooms")
    builder.button(text="🌐 Смотреть комнаты", callback_data="menu:public_rooms")
    builder.button(text="💳 Подписка", callback_data="menu:subscribe")
    builder.button(text="👤 Профиль", callback_data="menu:profile")
    builder.button(text="❓ Помощь", callback_data="menu:help")
    builder.adjust(1)
    return builder.as_markup()


@router.message(CommandStart())
async def cmd_start(message: types.Message) -> None:
    user = User(
        telegram_id=message.from_user.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
    )
    user.save()

    args = message.text.split(maxsplit=1)
    if len(args) > 1 and args[1].startswith("join_"):
        room_code = args[1][5:]
        from models.room import Room
        room = Room.get_by_code(room_code)
        if room and room.is_active:
            sub = Subscription.get_by_telegram_id(message.from_user.id)
            if room.password:
                builder = InlineKeyboardBuilder()
                builder.button(text="← Назад", callback_data="menu:main")
                await message.answer(
                    f"🔒 Комната <code>{room.code}</code> за паролем.\nВведи пароль:",
                    reply_markup=builder.as_markup(),
                    parse_mode="HTML",
                )
                state = FSMContext()
                await state.set_state(JoinPasswordState.waiting_password)
                await state.update_data(room_code=room.code)
                return
            if room.add_member(message.from_user.id):
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
                return
            else:
                await message.answer("⚠️ Комната заполнена.")
                return

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
async def callback_create(callback: types.CallbackQuery, state: FSMContext) -> None:
    builder = InlineKeyboardBuilder()
    builder.button(text="← Назад", callback_data="menu:main")
    await callback.message.edit_text(
        "📝 Введи название комнаты:",
        reply_markup=builder.as_markup(),
    )
    await state.set_state(CreateRoomState.waiting_title)
    await callback.answer()


@router.message(CreateRoomState.waiting_title, F.text)
async def process_room_title(message: types.Message, state: FSMContext) -> None:
    await state.update_data(title=message.text.strip()[:50])
    builder = InlineKeyboardBuilder()
    builder.button(text="Без пароля", callback_data="create:no_password")
    builder.button(text="← Назад", callback_data="menu:main")
    builder.adjust(1)
    await message.answer(
        "🔐 Введи пароль для комнаты\n(или нажми «Без пароля»):",
        reply_markup=builder.as_markup(),
    )
    await state.set_state(CreateRoomState.waiting_password)


@router.callback_query(F.data == "create:no_password")
async def callback_no_password(callback: types.CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    await state.clear()
    title = data.get("title", "Киновечер")

    from models.room import Room
    user = User(
        telegram_id=callback.from_user.id,
        username=callback.from_user.username,
        first_name=callback.from_user.first_name,
    )
    user.save()

    sub = Subscription.get_by_telegram_id(callback.from_user.id)
    room = Room.create(creator_id=callback.from_user.id, title=title, is_public=True)
    room.add_member(callback.from_user.id)

    bot_username = (await callback.bot.me()).username

    builder = InlineKeyboardBuilder()
    builder.button(
        text="🎬 Открыть киновечер",
        web_app=types.WebAppInfo(url=f"{WEBAPP_URL}?room={room.code}&tier={sub.tier}"),
    )
    builder.button(text="← Назад", callback_data="menu:main")
    builder.adjust(1)

    await callback.message.edit_text(
        f"🎉 Комната создана!\n\n"
        f"📌 Название: <b>{title}</b>\n"
        f"🔑 Код: <code>{room.code}</code>\n"
        f"🌐 Тип: Открытая\n"
        f"👥 Лимит: {sub.max_members} чел.\n\n"
        f"🔗 Пригласи друга:\nhttps://t.me/{bot_username}?start=join_{room.code}",
        reply_markup=builder.as_markup(),
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(CreateRoomState.waiting_password, F.text)
async def process_room_password(message: types.Message, state: FSMContext) -> None:
    data = await state.get_data()
    await state.clear()
    title = data.get("title", "Киновечер")
    password = message.text.strip()[:30]

    from models.room import Room
    user = User(
        telegram_id=message.from_user.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
    )
    user.save()

    sub = Subscription.get_by_telegram_id(message.from_user.id)
    room = Room.create(creator_id=message.from_user.id, title=title, password=password, is_public=False)
    room.add_member(message.from_user.id)

    bot_username = (await message.bot.me()).username

    builder = InlineKeyboardBuilder()
    builder.button(
        text="🎬 Открыть киновечер",
        web_app=types.WebAppInfo(url=f"{WEBAPP_URL}?room={room.code}&tier={sub.tier}"),
    )
    builder.button(text="← Назад", callback_data="menu:main")
    builder.adjust(1)

    await message.answer(
        f"🎉 Комната создана!\n\n"
        f"📌 Название: <b>{title}</b>\n"
        f"🔑 Код: <code>{room.code}</code>\n"
        f"🔐 Пароль: <code>{password}</code>\n"
        f"🌐 Тип: Закрытая\n"
        f"👥 Лимит: {sub.max_members} чел.\n\n"
        f"🔗 Пригласи друга:\nhttps://t.me/{bot_username}?start=join_{room.code}",
        reply_markup=builder.as_markup(),
        parse_mode="HTML",
    )


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
            lock = "🔒" if room.password else "🌐"
            builder.button(
                text=f"{lock} {room.title} — {len(members)} чел.",
                callback_data=f"room:{room.code}",
            )
        builder.button(text="← Назад", callback_data="menu:main")
        builder.adjust(1)
        await callback.message.edit_text(
            "📋 Твои комнаты:",
            reply_markup=builder.as_markup(),
        )
    await callback.answer()


@router.callback_query(F.data == "menu:public_rooms")
async def callback_public_rooms(callback: types.CallbackQuery) -> None:
    from models.room import Room

    public_rooms = Room.get_public_rooms()
    builder = InlineKeyboardBuilder()

    if not public_rooms:
        builder.button(text="← Назад", callback_data="menu:main")
        await callback.message.edit_text(
            "🌐 Пока нет открытых комнат.\nСоздай первую!",
            reply_markup=builder.as_markup(),
        )
    else:
        for room in public_rooms:
            members = room.get_members()
            builder.button(
                text=f"🚪 {room.title} — {len(members)} чел.",
                callback_data=f"pubroom:{room.code}",
            )
        builder.button(text="← Назад", callback_data="menu:main")
        builder.adjust(1)
        await callback.message.edit_text(
            "🌐 Открытые комнаты:",
            reply_markup=builder.as_markup(),
        )
    await callback.answer()


@router.callback_query(F.data.startswith("pubroom:"))
async def callback_public_room_detail(callback: types.CallbackQuery) -> None:
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
    is_member = callback.from_user.id in [m["telegram_id"] for m in members]

    builder = InlineKeyboardBuilder()
    if is_member:
        builder.button(
            text="🎬 Открыть",
            web_app=types.WebAppInfo(url=f"{WEBAPP_URL}?room={room.code}&tier={sub.tier}"),
        )
    else:
        builder.button(text="✅ Войти", callback_data=f"pubroom_join:{room.code}")
    builder.button(text="← Назад", callback_data="menu:public_rooms")
    builder.adjust(1)

    lock = "🔒 Закрытая" if room.password else "🌐 Открытая"
    await callback.message.edit_text(
        f"📌 {room.title} ({room.code})\n"
        f"🔐 Тип: {lock}\n"
        f"👥 Участники ({len(members)}): {member_names}",
        reply_markup=builder.as_markup(),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("pubroom_join:"))
async def callback_public_room_join(callback: types.CallbackQuery, state: FSMContext) -> None:
    from models.room import Room

    code = callback.data.split(":", 1)[1]
    room = Room.get_by_code(code)
    if room is None:
        await callback.answer("Комната не найдена.", show_alert=True)
        return

    if room.password:
        builder = InlineKeyboardBuilder()
        builder.button(text="← Назад", callback_data=f"pubroom:{room.code}")
        await callback.message.edit_text(
            "🔐 Введи пароль комнаты:",
            reply_markup=builder.as_markup(),
        )
        await state.set_state(JoinPasswordState.waiting_password)
        await state.update_data(room_code=room.code)
        await callback.answer()
        return

    sub = Subscription.get_by_telegram_id(callback.from_user.id)
    if room.add_member(callback.from_user.id):
        builder = InlineKeyboardBuilder()
        builder.button(
            text="🎬 Открыть киновечер",
            web_app=types.WebAppInfo(url=f"{WEBAPP_URL}?room={room.code}&tier={sub.tier}"),
        )
        builder.button(text="← Назад", callback_data="menu:public_rooms")
        builder.adjust(1)
        await callback.message.edit_text(
            f"✅ Ты в комнате <code>{room.code}</code>!\n📌 {room.title}",
            reply_markup=builder.as_markup(),
            parse_mode="HTML",
        )
    else:
        await callback.answer("⚠️ Комната заполнена.", show_alert=True)
    await callback.answer()


class JoinPasswordState(StatesGroup):
    waiting_password = State()


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

    room = Room.get_by_code(code) if code else None
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

    if room.password:
        builder = InlineKeyboardBuilder()
        builder.button(text="← Назад", callback_data="menu:main")
        await message.answer(
            "🔐 Эта комната за паролем.\nВведи пароль:",
            reply_markup=builder.as_markup(),
        )
        await state.set_state(JoinPasswordState.waiting_password)
        await state.update_data(room_code=room.code)
        return

    sub = Subscription.get_by_telegram_id(message.from_user.id)
    if not room.add_member(message.from_user.id):
        creator_sub = Subscription.get_by_telegram_id(room.creator_id)
        builder = InlineKeyboardBuilder()
        builder.button(text="💳 Подписка", callback_data="menu:subscribe")
        builder.button(text="← Назад", callback_data="menu:main")
        builder.adjust(1)
        await message.answer(
            f"⚠️ Комната заполнена (макс. {creator_sub.max_members} участников).",
            reply_markup=builder.as_markup(),
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


@router.message(JoinPasswordState.waiting_password, F.text)
async def process_join_password(message: types.Message, state: FSMContext) -> None:
    data = await state.get_data()
    await state.clear()
    room_code = data.get("room_code", "")
    password = message.text.strip()

    from models.room import Room
    room = Room.get_by_code(room_code)
    if room is None or not room.is_active:
        builder = InlineKeyboardBuilder()
        builder.button(text="← Назад", callback_data="menu:main")
        await message.answer("❌ Комната не найдена.", reply_markup=builder.as_markup())
        return

    if room.password != password:
        builder = InlineKeyboardBuilder()
        builder.button(text="← Назад", callback_data="menu:main")
        await message.answer(
            "❌ Неверный пароль.",
            reply_markup=builder.as_markup(),
        )
        return

    sub = Subscription.get_by_telegram_id(message.from_user.id)
    if not room.add_member(message.from_user.id):
        creator_sub = Subscription.get_by_telegram_id(room.creator_id)
        builder = InlineKeyboardBuilder()
        builder.button(text="💳 Подписка", callback_data="menu:subscribe")
        builder.button(text="← Назад", callback_data="menu:main")
        builder.adjust(1)
        await message.answer(
            f"⚠️ Комната заполнена (макс. {creator_sub.max_members} участников).",
            reply_markup=builder.as_markup(),
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


@router.callback_query(F.data.startswith("room:") & ~F.data.startswith("room:leave:"))
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
    if callback.from_user.id == room.creator_id:
        builder.button(
            text="🗑 Закрыть комнату",
            callback_data=f"room:close:{room.code}",
        )
    builder.button(text="← Назад", callback_data="menu:rooms")
    builder.adjust(1)

    lock = "🔒" if room.password else "🌐"
    await callback.message.edit_text(
        f"📌 {room.title} ({room.code}) {lock}\n"
        f"👥 Участники ({len(members)}): {member_names}",
        reply_markup=builder.as_markup(),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("room:close:"))
async def callback_close_room(callback: types.CallbackQuery) -> None:
    from models.room import Room

    code = callback.data.split(":", 2)[2]
    room = Room.get_by_code(code)
    if room is None:
        await callback.answer("Комната не найдена.", show_alert=True)
        return

    if callback.from_user.id != room.creator_id:
        await callback.answer("Только создатель может закрыть комнату.", show_alert=True)
        return

    room.deactivate()
    builder = InlineKeyboardBuilder()
    builder.button(text="← Назад", callback_data="menu:rooms")
    await callback.message.edit_text(
        f"🗑 Комната <code>{code}</code> закрыта.",
        reply_markup=builder.as_markup(),
        parse_mode="HTML",
    )
    await callback.answer("Комната закрыта.", show_alert=True)


@router.callback_query(F.data == "menu:help")
async def callback_help(callback: types.CallbackQuery) -> None:
    builder = InlineKeyboardBuilder()
    builder.button(text="← Назад", callback_data="menu:main")
    await callback.message.edit_text(
        "📚 <b>Как пользоваться ботом</b>\n\n"
        "1️⃣ <b>Создай комнату</b> — нажми «Создать комнату»\n"
        "2️⃣ <b>Пригласи друга</b> — отправь ему код комнаты\n"
        "3️⃣ <b>Друг заходит</b> — нажимает «Войти в комнату» и вводит код\n"
        "4️⃣ <b>Откройте приложение</b> — нажмите «Открыть киновечер»\n\n"
        "🌐 <b>Открытые комнаты</b>\n"
        "Нажми «Смотреть комнаты» чтобы найти открытые комнаты.\n\n"
        "🔒 <b>Закрытые комнаты</b>\n"
        "При создании выбери пароль — только те кто знает пароль смогут войти.\n\n"
        "🎬 <b>YouTube</b>\n"
        "Вставь ссылку на видео в поле чата в приложении.\n"
        "Пример: https://www.youtube.com/watch?v=dQw4w9WgXcQ\n\n"
        "📺 <b>Twitch</b> (VIP)\n"
        "Вставь ссылку на стрим: https://www.twitch.tv/username\n\n"
        "📤 <b>Загрузка видео</b> (Paid+)\n"
        "Отправь видео файлом боту — оно доступно для просмотра 1 раз.\n\n"
        "🎭 <b>Театрный режим</b>\n"
        "Нажми на видео → «На весь экран» для полноэкранного просмотра.\n\n"
        "💬 <b>Режим чата</b>\n"
        "Переключись на вкладку «Чат» для полноэкранного чата как на Twitch.\n\n"
        "🎨 <b>Темы</b> (VIP)\n"
        "Нажми «Тема» в приложении чтобы сменить оформление.\n\n"
        "💳 <b>Подписка</b>\n"
        "• Free: 2 участника, YouTube\n"
        "• Paid (399⭐): 5 участников, загрузка видео\n"
        "• VIP (999⭐): 30 участников, Twitch, темы",
        reply_markup=builder.as_markup(),
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(Command("stats"))
async def cmd_stats(message: types.Message) -> None:
    import os as _os
    _admin_raw = _os.getenv("ADMIN_ID")
    _admin_id = int(_admin_raw) if _admin_raw else None
    if _admin_id is None or message.from_user.id != _admin_id:
        await message.answer("❌ Нет доступа.")
        return

    from services.database import get_db
    from services.sync import room_states

    db = get_db()
    total_users = db.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    total_rooms = db.execute("SELECT COUNT(*) FROM rooms WHERE is_active = 1").fetchone()[0]
    total_subs = db.execute("SELECT COUNT(*) FROM subscriptions WHERE tier != 'free'").fetchone()[0]

    tier_stats = db.execute(
        "SELECT tier, COUNT(*) FROM subscriptions GROUP BY tier"
    ).fetchall()

    active_connections = sum(len(rs.connections) for rs in room_states.values())

    lines = [
        "📊 <b>Статистика бота</b>\n",
        f"👤 Пользователей: <b>{total_users}</b>",
        f"🚪 Активных комнат: <b>{total_rooms}</b>",
        f"🟢 WebSocket подключений: <b>{active_connections}</b>",
        f"💳 Платящих подписчиков: <b>{total_subs}</b>\n",
        "📦 <b>По тарифам:</b>",
    ]
    for tier, count in tier_stats:
        lines.append(f"  • {tier.upper()}: {count}")

    await message.answer("\n".join(lines), parse_mode="HTML")
