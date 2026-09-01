from __future__ import annotations

import secrets
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from services.database import get_db
from models.subscription import Subscription


@dataclass
class Room:
    code: str
    creator_id: int
    title: str = "Киновечер"
    created_at: Optional[str] = None
    is_active: bool = True
    current_video_id: Optional[int] = None
    password: Optional[str] = None
    is_public: bool = True
    id: Optional[int] = field(default=None, repr=False)

    def save(self) -> None:
        db = get_db()
        if self.created_at is None:
            self.created_at = datetime.utcnow().isoformat()
        cursor = db.execute(
            """
            INSERT INTO rooms (code, creator_id, title, created_at, is_active, current_video_id, password, is_public)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(code) DO UPDATE SET
                title = excluded.title,
                is_active = excluded.is_active,
                current_video_id = excluded.current_video_id,
                password = excluded.password,
                is_public = excluded.is_public
            """,
            (self.code, self.creator_id, self.title, self.created_at, self.is_active,
             self.current_video_id, self.password, 1 if self.is_public else 0),
        )
        db.commit()
        self.id = cursor.lastrowid

    @classmethod
    def create(cls, creator_id: int, title: str = "Киновечер",
               password: Optional[str] = None, is_public: bool = True) -> Room:
        code = secrets.token_urlsafe(6)
        room = cls(code=code, creator_id=creator_id, title=title,
                   password=password, is_public=is_public)
        room.save()
        return room

    @classmethod
    def get_by_code(cls, code: str) -> Optional[Room]:
        db = get_db()
        row = db.execute(
            "SELECT id, code, creator_id, title, created_at, is_active, current_video_id, password, is_public FROM rooms WHERE code = ?",
            (code,),
        ).fetchone()
        if row is None:
            return None
        return cls(
            id=row[0],
            code=row[1],
            creator_id=row[2],
            title=row[3],
            created_at=row[4],
            is_active=bool(row[5]),
            current_video_id=row[6],
            password=row[7],
            is_public=bool(row[8]),
        )

    @classmethod
    def get_user_rooms(cls, telegram_id: int) -> list[Room]:
        db = get_db()
        rows = db.execute(
            """
            SELECT r.id, r.code, r.creator_id, r.title, r.created_at, r.is_active, r.current_video_id, r.password, r.is_public
            FROM rooms r
            INNER JOIN room_members rm ON r.id = rm.room_id
            WHERE rm.telegram_id = ? AND r.is_active = 1
            """,
            (telegram_id,),
        ).fetchall()
        return [
            cls(
                id=row[0],
                code=row[1],
                creator_id=row[2],
                title=row[3],
                created_at=row[4],
                is_active=bool(row[5]),
                current_video_id=row[6],
                password=row[7],
                is_public=bool(row[8]),
            )
            for row in rows
        ]

    @classmethod
    def get_public_rooms(cls) -> list[Room]:
        db = get_db()
        rows = db.execute(
            "SELECT id, code, creator_id, title, created_at, is_active, current_video_id, password, is_public "
            "FROM rooms WHERE is_active = 1 AND is_public = 1 ORDER BY created_at DESC LIMIT 20"
        ).fetchall()
        return [
            cls(
                id=row[0],
                code=row[1],
                creator_id=row[2],
                title=row[3],
                created_at=row[4],
                is_active=bool(row[5]),
                current_video_id=row[6],
                password=row[7],
                is_public=bool(row[8]),
            )
            for row in rows
        ]

    def get_members(self) -> list[dict]:
        db = get_db()
        rows = db.execute(
            """
            SELECT rm.telegram_id, u.username, u.first_name, rm.joined_at
            FROM room_members rm
            LEFT JOIN users u ON rm.telegram_id = u.telegram_id
            WHERE rm.room_id = ?
            """,
            (self.id,),
        ).fetchall()
        return [
            {"telegram_id": row[0], "username": row[1], "first_name": row[2], "joined_at": row[3]}
            for row in rows
        ]

    def member_count(self) -> int:
        db = get_db()
        row = db.execute(
            "SELECT COUNT(*) FROM room_members WHERE room_id = ?", (self.id,)
        ).fetchone()
        return row[0] if row else 0

    def can_add_member(self, telegram_id: int = 0) -> bool:
        count = self.member_count()
        creator_sub = Subscription.get_by_telegram_id(self.creator_id)
        limit = creator_sub.max_members
        return count < limit

    def add_member(self, telegram_id: int) -> bool:
        if not self.can_add_member(telegram_id):
            return False
        db = get_db()
        db.execute(
            """
            INSERT OR IGNORE INTO room_members (room_id, telegram_id, joined_at)
            VALUES (?, ?, ?)
            """,
            (self.id, telegram_id, datetime.utcnow().isoformat()),
        )
        db.commit()
        return True

    def remove_member(self, telegram_id: int) -> None:
        db = get_db()
        db.execute(
            "DELETE FROM room_members WHERE room_id = ? AND telegram_id = ?",
            (self.id, telegram_id),
        )
        db.commit()

    def deactivate(self) -> None:
        db = get_db()
        db.execute("UPDATE rooms SET is_active = 0 WHERE id = ?", (self.id,))
        db.commit()
        self.is_active = False

    def set_current_video(self, video_id: int) -> None:
        db = get_db()
        db.execute("UPDATE rooms SET current_video_id = ? WHERE id = ?", (video_id, self.id))
        db.commit()
        self.current_video_id = video_id

    def get_videos(self) -> list[dict]:
        db = get_db()
        rows = db.execute(
            """
            SELECT id, youtube_url, title, added_by, added_at
            FROM videos WHERE room_id = ?
            ORDER BY added_at
            """,
            (self.id,),
        ).fetchall()
        return [
            {"id": row[0], "youtube_url": row[1], "title": row[2], "added_by": row[3], "added_at": row[4]}
            for row in rows
        ]


@dataclass
class Video:
    room_id: int
    youtube_url: str
    title: str = ""
    added_by: int = 0
    added_at: Optional[str] = None
    id: Optional[int] = field(default=None, repr=False)

    def save(self) -> None:
        db = get_db()
        if self.added_at is None:
            self.added_at = datetime.utcnow().isoformat()
        cursor = db.execute(
            """
            INSERT INTO videos (room_id, youtube_url, title, added_by, added_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (self.room_id, self.youtube_url, self.title, self.added_by, self.added_at),
        )
        db.commit()
        self.id = cursor.lastrowid

    @classmethod
    def extract_video_id(cls, url: str) -> Optional[str]:
        import re
        patterns = [
            r"(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/embed/)([a-zA-Z0-9_-]{11})",
            r"youtube\.com/v/([a-zA-Z0-9_-]{11})",
        ]
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)
        return None
