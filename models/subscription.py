from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

from services.database import get_db

TIERS = {
    "free": {"name": "Free", "price": 0, "price_stars": 0, "max_members": 2, "features": ["YouTube"]},
    "paid": {"name": "Paid", "price": 399, "price_stars": 399, "max_members": 5, "features": ["YouTube", "Загрузка видео"]},
    "vip": {"name": "VIP", "price": 999, "price_stars": 999, "max_members": 30, "features": ["YouTube", "Twitch", "Загрузка видео", "Кастомизация"]},
}


@dataclass
class Subscription:
    telegram_id: int
    tier: str = "free"
    started_at: Optional[str] = None
    expires_at: Optional[str] = None
    payment_id: Optional[str] = None
    id: Optional[int] = None

    def save(self) -> None:
        db = get_db()
        if self.started_at is None:
            self.started_at = datetime.now(timezone.utc).isoformat()
        db.execute(
            """
            INSERT INTO subscriptions (telegram_id, tier, started_at, expires_at, payment_id)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(telegram_id) DO UPDATE SET
                tier = excluded.tier,
                started_at = excluded.started_at,
                expires_at = excluded.expires_at,
                payment_id = excluded.payment_id
            """,
            (self.telegram_id, self.tier, self.started_at, self.expires_at, self.payment_id),
        )
        db.commit()

    @classmethod
    def get_by_telegram_id(cls, telegram_id: int) -> Optional[Subscription]:
        db = get_db()
        row = db.execute(
            "SELECT id, telegram_id, tier, started_at, expires_at, payment_id FROM subscriptions WHERE telegram_id = ?",
            (telegram_id,),
        ).fetchone()
        if row is None:
            return cls(telegram_id=telegram_id, tier="free")
        sub = cls(
            id=row[0],
            telegram_id=row[1],
            tier=row[2],
            started_at=row[3],
            expires_at=row[4],
            payment_id=row[5],
        )
        if sub.expires_at and sub.tier != "free":
            try:
                exp = datetime.fromisoformat(sub.expires_at)
                if exp.tzinfo is None:
                    exp = exp.replace(tzinfo=timezone.utc)
                now = datetime.now(timezone.utc)
                if exp < now:
                    sub.tier = "free"
                    sub.expires_at = None
                    sub.save()
            except (ValueError, TypeError):
                pass
        return sub

    @property
    def max_members(self) -> int:
        return TIERS.get(self.tier, TIERS["free"])["max_members"]

    @property
    def price(self) -> int:
        return TIERS.get(self.tier, TIERS["free"])["price"]

    @property
    def features(self) -> list[str]:
        return TIERS.get(self.tier, TIERS["free"])["features"]

    def can_upload_video(self) -> bool:
        return self.tier in ("paid", "vip")

    def can_use_twitch(self) -> bool:
        return self.tier == "vip"

    def can_customize(self) -> bool:
        return self.tier == "vip"

    @staticmethod
    def create_paid_subscription(telegram_id: int, tier: str, payment_id: str) -> Subscription:
        now = datetime.now(timezone.utc)
        expires = now + timedelta(days=30)
        sub = Subscription(
            telegram_id=telegram_id,
            tier=tier,
            started_at=now.isoformat(),
            expires_at=expires.isoformat(),
            payment_id=payment_id,
        )
        sub.save()
        return sub
