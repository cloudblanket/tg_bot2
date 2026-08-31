from __future__ import annotations

import logging
import os

from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder

from models.user import User
from models.subscription import Subscription, TIERS

router = Router(name="subscribe")
logger = logging.getLogger(__name__)

_admin_raw = os.getenv("ADMIN_ID")
ADMIN_ID = int(_admin_raw) if _admin_raw else None


def back_button(callback_data: str = "menu:main") -> types.InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="← Назад", callback_data=callback_data)
    return builder.as_markup()


@router.callback_query(F.data == "menu:subscribe")
async def callback_subscribe_menu(callback: types.CallbackQuery) -> None:
    sub = Subscription.get_by_telegram_id(callback.from_user.id)

    lines = [f"💳 Твой тариф: <b>{sub.tier.upper()}</b>\n"]

    for key, tier in TIERS.items():
        current = " ← текущий" if key == sub.tier else ""
        price = tier.get("price_stars", 0)
        price_str = "бесплатно" if price == 0 else f"⭐ {price}"
        lines.append(
            f"\n<b>{tier['name']}</b> — {price_str}{current}\n"
            f"  👥 До {tier['max_members']} чел.\n"
            f"  🎬 {', '.join(tier['features'])}"
        )

    builder = InlineKeyboardBuilder()

    if sub.tier != "paid":
        builder.button(text="💎 Paid — ⭐ 399", callback_data="subscribe:paid")
    if sub.tier != "vip":
        builder.button(text="👑 VIP — ⭐ 999", callback_data="subscribe:vip")
    builder.button(text="← Назад", callback_data="menu:main")
    builder.adjust(1)

    await callback.message.edit_text(
        "\n".join(lines),
        reply_markup=builder.as_markup(),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("subscribe:"))
async def callback_subscribe(callback: types.CallbackQuery) -> None:
    tier = callback.data.split(":", 1)[1]

    if tier not in TIERS or tier == "free":
        await callback.answer("Неверный тариф.", show_alert=True)
        return

    tier_info = TIERS[tier]
    price_stars = tier_info.get("price_stars", 0)

    await callback.message.bot.send_invoice(
        chat_id=callback.from_user.id,
        title=f"Подписка {tier_info['name']}",
        description=f"Доступ к функциям {tier_info['name']} на 30 дней",
        payload=f"sub:{tier}:{callback.from_user.id}",
        provider_token="",
        currency="XTR",
        prices=[types.LabeledPrice(label=f"Подписка {tier_info['name']}", amount=price_stars)],
    )
    await callback.answer()


@router.pre_checkout_query()
async def pre_checkout(query: types.PreCheckoutQuery) -> None:
    payload = query.invoice_payload
    if payload.startswith("sub:"):
        await query.answer(ok=True)
    else:
        await query.answer(ok=False, error_message="Неизвестный платёж")


@router.message(F.successful_payment)
async def successful_payment(message: types.Message) -> None:
    payment = message.successful_payment
    payload = payment.invoice_payload

    if payload.startswith("sub:"):
        parts = payload.split(":")
        if len(parts) == 3:
            tier = parts[1]
            telegram_id = int(parts[2])

            sub = Subscription.create_paid_subscription(
                telegram_id=telegram_id,
                tier=tier,
                payment_id=payment.telegram_payment_charge_id,
            )

            user = User.get_by_telegram_id(telegram_id)
            if user:
                user.set_tier(tier)

            builder = InlineKeyboardBuilder()
            builder.button(text="🎬 Меню", callback_data="menu:main")

            await message.answer(
                f"✅ Подписка <b>{TIERS[tier]['name']}</b> активирована!\n\n"
                f"👥 До {TIERS[tier]['max_members']} чел.\n"
                f"🎬 {', '.join(TIERS[tier]['features'])}\n"
                f"⏰ 30 дней",
                reply_markup=builder.as_markup(),
                parse_mode="HTML",
            )


@router.callback_query(F.data == "menu:profile")
async def callback_profile(callback: types.CallbackQuery) -> None:
    user = User.get_by_telegram_id(callback.from_user.id)
    sub = Subscription.get_by_telegram_id(callback.from_user.id)

    name = user.first_name or user.username or "Аноним"
    tier = sub.tier.upper()
    features = ", ".join(sub.features)

    builder = InlineKeyboardBuilder()
    builder.button(text="← Назад", callback_data="menu:main")

    await callback.message.edit_text(
        f"👤 <b>Профиль</b>\n\n"
        f"Имя: {name}\n"
        f"ID: <code>{callback.from_user.id}</code>\n"
        f"💳 Тариф: <b>{tier}</b>\n"
        f"🎬 Функции: {features}",
        reply_markup=builder.as_markup(),
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(Command("vip"))
async def cmd_vip(message: types.Message) -> None:
    if ADMIN_ID is None or message.from_user.id != ADMIN_ID:
        await message.answer("❌ Нет доступа.")
        return

    args = message.text.split()
    if len(args) < 2:
        telegram_id = message.from_user.id
    else:
        try:
            telegram_id = int(args[1])
        except ValueError:
            await message.answer("❌ Укажи telegram_id числом.")
            return

    sub = Subscription.get_by_telegram_id(telegram_id)
    sub.tier = "vip"
    from datetime import datetime, timedelta
    sub.started_at = datetime.now().isoformat()
    sub.expires_at = (datetime.now() + timedelta(days=3650)).isoformat()
    sub.save()

    user = User.get_by_telegram_id(telegram_id)
    if user:
        user.set_tier("vip")

    await message.answer(f"✅ VIP активирован для {telegram_id}")
