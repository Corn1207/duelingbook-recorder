"""
database.py

SQLite database setup and access for the duelingbook recorder app.
"""

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data" / "replays.db"


def get_connection() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with get_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS replays (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                replay_id   TEXT NOT NULL UNIQUE,
                deck1       TEXT,
                deck2       TEXT,
                label_left  TEXT DEFAULT 'DUELINGBOOK',
                label_right TEXT DEFAULT 'HIGH RATED',
                title       TEXT,
                description TEXT,
                tags        TEXT,
                notes       TEXT,
                scheduled_date TEXT,
                status      TEXT NOT NULL DEFAULT 'pending',
                video_path  TEXT,
                thumbnail_path TEXT,
                youtube_url TEXT,
                created_at  TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS deck_cards (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                deck_name TEXT NOT NULL,
                card_name TEXT NOT NULL
            )
        """)
        # Migrations: add columns that may not exist in older DBs
        existing = {row[1] for row in conn.execute("PRAGMA table_info(replays)")}
        if "label_left" not in existing:
            conn.execute("ALTER TABLE replays ADD COLUMN label_left TEXT DEFAULT 'DUELINGBOOK'")
        if "label_right" not in existing:
            conn.execute("ALTER TABLE replays ADD COLUMN label_right TEXT DEFAULT 'HIGH RATED'")
        if "publish_at" not in existing:
            conn.execute("ALTER TABLE replays ADD COLUMN publish_at TEXT")
        conn.commit()
