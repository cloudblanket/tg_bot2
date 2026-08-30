from __future__ import annotations

import sqlite3
import os
from pathlib import Path

_DB_PATH = os.getenv("DATABASE_PATH", str(Path(__file__).parent.parent / "data" / "bot.db"))
_connection: sqlite3.Connection | None = None


def get_db() -> sqlite3.Connection:
    global _connection
    if _connection is None:
        Path(_DB_PATH).parent.mkdir(parents=True, exist_ok=True)
        _connection = sqlite3.connect(_DB_PATH, check_same_thread=False)
        _connection.row_factory = sqlite3.Row
        _connection.execute("PRAGMA journal_mode=WAL")
        _connection.execute("PRAGMA synchronous=NORMAL")
        _connection.execute("PRAGMA cache_size=-8000")
        _connection.execute("PRAGMA temp_store=MEMORY")
        _connection.execute("PRAGMA foreign_keys=ON")
        init_tables(_connection)
    return _connection


def init_tables(db: sqlite3.Connection) -> None:
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id INTEGER UNIQUE NOT NULL,
            username TEXT,
            first_name TEXT,
            is_premium INTEGER DEFAULT 0,
            tier TEXT DEFAULT 'free'
        );

        CREATE TABLE IF NOT EXISTS rooms (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT UNIQUE NOT NULL,
            creator_id INTEGER NOT NULL,
            title TEXT DEFAULT 'Киновечер',
            created_at TEXT,
            is_active INTEGER DEFAULT 1,
            current_video_id INTEGER
        );

        CREATE TABLE IF NOT EXISTS room_members (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            room_id INTEGER NOT NULL,
            telegram_id INTEGER NOT NULL,
            joined_at TEXT,
            UNIQUE(room_id, telegram_id),
            FOREIGN KEY (room_id) REFERENCES rooms(id)
        );

        CREATE TABLE IF NOT EXISTS videos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            room_id INTEGER NOT NULL,
            youtube_url TEXT NOT NULL,
            title TEXT DEFAULT '',
            added_by INTEGER,
            added_at TEXT,
            FOREIGN KEY (room_id) REFERENCES rooms(id)
        );

        CREATE TABLE IF NOT EXISTS subscriptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id INTEGER NOT NULL,
            tier TEXT NOT NULL DEFAULT 'free',
            started_at TEXT NOT NULL,
            expires_at TEXT,
            payment_id TEXT,
            UNIQUE(telegram_id)
        );

        CREATE INDEX IF NOT EXISTS idx_room_members_telegram ON room_members(telegram_id);
        CREATE INDEX IF NOT EXISTS idx_room_members_room ON room_members(room_id);
        CREATE INDEX IF NOT EXISTS idx_rooms_code ON rooms(code);
        CREATE INDEX IF NOT EXISTS idx_videos_room ON videos(room_id);
        CREATE INDEX IF NOT EXISTS idx_subscriptions_telegram ON subscriptions(telegram_id);
        """
    )

    # Миграции для существующих БД
    try:
        db.execute("ALTER TABLE users ADD COLUMN tier TEXT DEFAULT 'free'")
    except sqlite3.OperationalError:
        pass  # колонка уже есть

    db.commit()
