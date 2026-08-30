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

PAYMENT_TOKEN = os.getenv("PAYMENT_TOKEN", "")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))


@router.message(Command("subscribe"))
async def cmd_subscribe(message: types.Message) -> None:
    user = User.get_by_telegram_id(message.from_user.id)
    if user is None:
        user = User(
            telegram_id=message.from_user.id,
            username=message.from_user.username,
            first_name=message.from_user.first_name,
        )
        user.save()

    sub = Subscription.get_by_telegram_id(message.from_user.id)

    lines = [f"💳 Твой текущий тариф: <b>{sub.tier.upper()}</b>\n"]

    for key, tier in TIERS.items():
        current = " ← текущий" if key == sub.tier else ""
        lines.append(
            f"\n<b>{tier['name']}</b> — {'бесплатно' if tier['price'] == 0 else f'{tier['price']}₽/мес'}{current}\n"
            f"  👥 До {tier['max_members']} человек\n"
            f"  🎬 Источники: {', '.join(tier['features'])}"
        )

    builder = InlineKeyboardBuilder()

    if sub.tier != "paid" and PAYMENT_TOKEN:
        builder.button(
            text="💎 Paid — 300₽/мес",
            callback_data="subscribe:paid",
        )
    if sub.tier != "vip" and PAYMENT_TOKEN:
        builder.button(
            text="👑 VIP — 1000₽/мес",
            callback_data="subscribe:vip",
        )
    builder.adjust(1)

    await message.answer("\n".join(lines), reply_markup=builder.as_markup(), parse_mode="HTML")


@router.callback_query(F.data.startswith("subscribe:"))
async def callback_subscribe(callback: types.CallbackQuery) -> None:
    tier = callback.data.split(":", 1)[1]

    if tier not in TIERS or tier == "free":
        await callback.answer("Неверный тариф.", show_alert=True)
        return

    if not PAYMENT_TOKEN:
        await callback.answer("Оплата пока недоступна.", show_alert=True)
        return

    tier_info = TIERS[tier]

    await callback.message.bot.send_invoice(
        chat_id=callback.from_user.id,
        title=f"Подписка {tier_info['name']}",
        description=f"Доступ к функциям {tier_info['name']} на 30 дней",
        payload=f"sub:{tier}:{callback.from_user.id}",
        provider_token=PAYMENT_TOKEN,
        currency="RUB",
        prices=[types.LabeledPrice(label=f"Подписка {tier_info['name']}", amount=tier_info["price"] * 100)],
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
                user.tier = tier
                user.save()

            await message.answer(
                f"✅ Подписка <b>{TIERS[tier]['name']}</b> активирована!\n\n"
                f"👥 До {TIERS[tier]['max_members']} человек\n"
                f"🎬 {', '.join(TIERS[tier]['features'])}\n"
                f"⏰ Действует 30 дней",
                parse_mode="HTML",
            )


@router.message(Command("vip"))
async def cmd_vip(message: types.Message) -> None:
    if ADMIN_ID and message.from_user.id != ADMIN_ID:
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
        user.tier = "vip"
        user.save()

    await message.answer(f"✅ VIP активирован для {telegram_id}")
