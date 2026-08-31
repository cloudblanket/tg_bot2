from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from typing import Optional

from services.database import get_db


@dataclass
class User:
    telegram_id: int
    username: Optional[str] = None
    first_name: Optional[str] = None
    is_premium: bool = False
    tier: str = "free"
    id: Optional[int] = field(default=None, repr=False)

    def save(self) -> None:
        db = get_db()
        existing = self.get_by_telegram_id(self.telegram_id)
        if existing:
            db.execute(
                "UPDATE users SET username = ?, first_name = ? WHERE telegram_id = ?",
                (self.username, self.first_name, self.telegram_id),
            )
        else:
            db.execute(
                "INSERT INTO users (telegram_id, username, first_name, is_premium, tier) VALUES (?, ?, ?, ?, ?)",
                (self.telegram_id, self.username, self.first_name, self.is_premium, self.tier),
            )
        db.commit()

    def set_tier(self, tier: str) -> None:
        self.tier = tier
        db = get_db()
        db.execute("UPDATE users SET tier = ? WHERE telegram_id = ?", (tier, self.telegram_id))
        db.commit()

    @classmethod
    def get_by_telegram_id(cls, telegram_id: int) -> Optional[User]:
        db = get_db()
        row = db.execute(
            "SELECT id, telegram_id, username, first_name, is_premium, tier FROM users WHERE telegram_id = ?",
            (telegram_id,),
        ).fetchone()
        if row is None:
            return None
        return cls(
            id=row[0],
            telegram_id=row[1],
            username=row[2],
            first_name=row[3],
            is_premium=bool(row[4]),
            tier=row[5] or "free",
        )
