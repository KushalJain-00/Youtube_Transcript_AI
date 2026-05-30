import sqlite3
import os

if os.environ.get("VERCEL"):
    DB_PATH = "/tmp/ytai_data.db"
else:
    DB_PATH = os.environ.get("DB_PATH", "ytai_data.db")

def get_db():
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL;")
    return db

def init_db():
    db = get_db()
    db.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS api_keys (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            provider TEXT NOT NULL,
            key_value TEXT NOT NULL,
            label TEXT,
            model TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY(user_id) REFERENCES users(id)
        );
        CREATE TABLE IF NOT EXISTS history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            type TEXT NOT NULL,
            title TEXT,
            url TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY(user_id) REFERENCES users(id)
        );
        CREATE TABLE IF NOT EXISTS video_cache (
            video_id TEXT PRIMARY KEY,
            transcript TEXT,
            ai_summary TEXT,
            ai_takeaways TEXT,
            provider TEXT,
            model TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        );

        CREATE INDEX IF NOT EXISTS idx_api_keys_user_provider ON api_keys(user_id, provider);
        CREATE INDEX IF NOT EXISTS idx_history_user_date ON history(user_id, created_at);
    """)

    # Migration: Add model column if it doesn't exist
    try:
        db.execute("ALTER TABLE api_keys ADD COLUMN model TEXT")
    except sqlite3.OperationalError:
        pass # Column already exists

    db.commit()
    db.close()
