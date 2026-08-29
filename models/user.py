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
    id: Optional[int] = field(default=None, repr=False)

    def save(self) -> None:
        db = get_db()
        cursor = db.execute(
            """
            INSERT INTO users (telegram_id, username, first_name, is_premium)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(telegram_id) DO UPDATE SET
                username = excluded.username,
                first_name = excluded.first_name,
                is_premium = excluded.is_premium
            """,
            (self.telegram_id, self.username, self.first_name, self.is_premium),
        )
        db.commit()
        self.id = cursor.lastrowid

    @classmethod
    def get_by_telegram_id(cls, telegram_id: int) -> Optional[User]:
        db = get_db()
        row = db.execute(
            "SELECT id, telegram_id, username, first_name, is_premium FROM users WHERE telegram_id = ?",
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
        )
