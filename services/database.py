from __future__ import annotations

import os
import threading
from pathlib import Path
from typing import Any, Optional

DATABASE_URL = os.getenv("DATABASE_URL", "")
_use_postgres = DATABASE_URL.startswith("postgresql")


def is_postgres() -> bool:
    return _use_postgres


def placeholder() -> str:
    return "%s" if _use_postgres else "?"


def placeholders(count: int) -> str:
    return ", ".join([placeholder()] * count)


if _use_postgres:
    import psycopg2

    _lock = threading.Lock()
    _conn = None

    class PgWrapper:
        def __init__(self, conn):
            self._conn = conn

        def execute(self, sql: str, params: Any = None):
            cur = self._conn.cursor()
            if params is not None:
                cur.execute(sql, params)
            else:
                cur.execute(sql)
            return cur

        def commit(self):
            self._conn.commit()

        def close(self):
            self._conn.close()

        @property
        def closed(self):
            return self._conn.closed

        @property
        def autocommit(self):
            return self._conn.autocommit

        @autocommit.setter
        def autocommit(self, value):
            self._conn.autocommit = value

        def cursor(self):
            return self._conn.cursor()

    def get_db():
        global _conn
        if _conn is None or _conn.closed:
            raw = psycopg2.connect(DATABASE_URL)
            raw.autocommit = False
            _conn = PgWrapper(raw)
            init_tables_pg(_conn)
        return _conn

    def get_lock():
        return _lock

    def init_tables_pg(db):
        db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                telegram_id BIGINT UNIQUE NOT NULL,
                username TEXT,
                first_name TEXT,
                is_premium BOOLEAN DEFAULT FALSE,
                tier TEXT DEFAULT 'free',
                referral_code TEXT UNIQUE,
                referred_by BIGINT DEFAULT 0,
                referrals_count INTEGER DEFAULT 0
            )
        """)
        db.execute("""
            CREATE TABLE IF NOT EXISTS rooms (
                id SERIAL PRIMARY KEY,
                code TEXT UNIQUE NOT NULL,
                creator_id BIGINT NOT NULL,
                title TEXT DEFAULT 'абсолют синема',
                created_at TEXT,
                is_active BOOLEAN DEFAULT TRUE,
                current_video_id INTEGER,
                password TEXT,
                is_public BOOLEAN DEFAULT TRUE
            )
        """)
        db.execute("""
            CREATE TABLE IF NOT EXISTS room_members (
                id SERIAL PRIMARY KEY,
                room_id INTEGER NOT NULL,
                telegram_id BIGINT NOT NULL,
                joined_at TEXT,
                UNIQUE(room_id, telegram_id),
                FOREIGN KEY (room_id) REFERENCES rooms(id)
            )
        """)
        db.execute("""
            CREATE TABLE IF NOT EXISTS videos (
                id SERIAL PRIMARY KEY,
                room_id INTEGER NOT NULL,
                youtube_url TEXT NOT NULL,
                title TEXT DEFAULT '',
                added_by BIGINT,
                added_at TEXT,
                FOREIGN KEY (room_id) REFERENCES rooms(id)
            )
        """)
        db.execute("""
            CREATE TABLE IF NOT EXISTS subscriptions (
                id SERIAL PRIMARY KEY,
                telegram_id BIGINT NOT NULL,
                tier TEXT NOT NULL DEFAULT 'free',
                started_at TEXT NOT NULL,
                expires_at TEXT,
                payment_id TEXT,
                UNIQUE(telegram_id)
            )
        """)
        db.execute("""
            CREATE TABLE IF NOT EXISTS personalization (
                telegram_id BIGINT PRIMARY KEY,
                bg_url TEXT,
                bg_color TEXT,
                font_name TEXT,
                accent_color TEXT,
                border_radius TEXT
            )
        """)
        db.execute("CREATE INDEX IF NOT EXISTS idx_room_members_telegram ON room_members(telegram_id)")
        db.execute("CREATE INDEX IF NOT EXISTS idx_room_members_room ON room_members(room_id)")
        db.execute("CREATE INDEX IF NOT EXISTS idx_rooms_code ON rooms(code)")
        db.execute("CREATE INDEX IF NOT EXISTS idx_videos_room ON videos(room_id)")
        db.execute("CREATE INDEX IF NOT EXISTS idx_subscriptions_telegram ON subscriptions(telegram_id)")
        db.commit()

else:
    import sqlite3

    _DB_PATH = os.getenv("DATABASE_PATH", str(Path(__file__).parent.parent / "data" / "bot.db"))
    _connection = None
    _lock = threading.Lock()

    def get_db():
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

    def get_lock():
        return _lock

    def init_tables(db):
        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER UNIQUE NOT NULL,
                username TEXT,
                first_name TEXT,
                is_premium INTEGER DEFAULT 0,
                tier TEXT DEFAULT 'free',
                referral_code TEXT UNIQUE,
                referred_by INTEGER DEFAULT 0,
                referrals_count INTEGER DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS rooms (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT UNIQUE NOT NULL,
                creator_id INTEGER NOT NULL,
                title TEXT DEFAULT 'абсолют синема',
                created_at TEXT,
                is_active INTEGER DEFAULT 1,
                current_video_id INTEGER,
                password TEXT,
                is_public INTEGER DEFAULT 1
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

        for col in ['referral_code TEXT UNIQUE', 'referred_by INTEGER DEFAULT 0', 'referrals_count INTEGER DEFAULT 0']:
            try:
                db.execute(f"ALTER TABLE users ADD COLUMN {col}")
            except sqlite3.OperationalError:
                pass

        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS personalization (
                telegram_id INTEGER PRIMARY KEY,
                bg_url TEXT,
                bg_color TEXT,
                font_name TEXT,
                accent_color TEXT,
                border_radius TEXT
            );
            """
        )

        db.commit()
