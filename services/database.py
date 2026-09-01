from __future__ import annotations

import os
import threading
from pathlib import Path

DATABASE_URL = os.getenv("DATABASE_URL", "")
_use_postgres = DATABASE_URL.startswith("postgresql")


def is_postgres() -> bool:
    return _use_postgres


def placeholders(count: int) -> str:
    if _use_postgres:
        return ", ".join(["%s"] * count)
    return ", ".join(["?"] * count)


def placeholder() -> str:
    return "%s" if _use_postgres else "?"


if _use_postgres:
    import psycopg2
    import psycopg2.extras

    _connection = None
    _lock = threading.Lock()

    def get_db():
        global _connection
        if _connection is None or _connection.closed:
            _connection = psycopg2.connect(DATABASE_URL)
            _connection.autocommit = False
            init_tables_pg(_connection)
        return _connection

    def get_lock():
        return _lock

    def init_tables_pg(db):
        cur = db.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                telegram_id BIGINT UNIQUE NOT NULL,
                username TEXT,
                first_name TEXT,
                is_premium BOOLEAN DEFAULT FALSE,
                tier TEXT DEFAULT 'free'
            );
        """)
        cur.execute("""
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
            );
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS room_members (
                id SERIAL PRIMARY KEY,
                room_id INTEGER NOT NULL,
                telegram_id BIGINT NOT NULL,
                joined_at TEXT,
                UNIQUE(room_id, telegram_id),
                FOREIGN KEY (room_id) REFERENCES rooms(id)
            );
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS videos (
                id SERIAL PRIMARY KEY,
                room_id INTEGER NOT NULL,
                youtube_url TEXT NOT NULL,
                title TEXT DEFAULT '',
                added_by BIGINT,
                added_at TEXT,
                FOREIGN KEY (room_id) REFERENCES rooms(id)
            );
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS subscriptions (
                id SERIAL PRIMARY KEY,
                telegram_id BIGINT NOT NULL,
                tier TEXT NOT NULL DEFAULT 'free',
                started_at TEXT NOT NULL,
                expires_at TEXT,
                payment_id TEXT,
                UNIQUE(telegram_id)
            );
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS personalization (
                telegram_id BIGINT PRIMARY KEY,
                bg_url TEXT,
                bg_color TEXT,
                font_name TEXT,
                accent_color TEXT,
                border_radius TEXT
            );
        """)
        cur.execute("CREATE INDEX IF NOT EXISTS idx_room_members_telegram ON room_members(telegram_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_room_members_room ON room_members(room_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_rooms_code ON rooms(code)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_videos_room ON videos(room_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_subscriptions_telegram ON subscriptions(telegram_id)")
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
                tier TEXT DEFAULT 'free'
            );

            CREATE TABLE IF NOT EXISTS rooms (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT UNIQUE NOT NULL,
                creator_id INTEGER NOT NULL,
                title TEXT DEFAULT 'абсолют синема',
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

        try:
            db.execute("ALTER TABLE users ADD COLUMN tier TEXT DEFAULT 'free'")
        except sqlite3.OperationalError:
            pass

        try:
            db.execute("ALTER TABLE rooms ADD COLUMN password TEXT")
        except sqlite3.OperationalError:
            pass

        try:
            db.execute("ALTER TABLE rooms ADD COLUMN is_public INTEGER DEFAULT 1")
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
