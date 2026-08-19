"""لایه‌ی دیتابیس — SQLite ساده و بدون وابستگی خارجی."""

from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from typing import Any, Iterable

from . import config

_lock = threading.Lock()

SCHEMA = """
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS documents (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    title         TEXT NOT NULL,
    filename      TEXT NOT NULL,
    path          TEXT NOT NULL,
    audience      TEXT NOT NULL DEFAULT 'both',   -- public | internal | both
    category      TEXT DEFAULT '',
    size_bytes    INTEGER DEFAULT 0,
    pages         INTEGER DEFAULT 0,
    chunk_count   INTEGER DEFAULT 0,
    status        TEXT DEFAULT 'pending',         -- pending | indexing | ready | error
    error         TEXT DEFAULT '',
    checksum      TEXT DEFAULT '',
    embedded      INTEGER DEFAULT 0,              -- ۱ اگر بردارها ساخته شده باشند
    repaired      INTEGER DEFAULT 0,              -- تعداد صفحه‌های بازسازی‌شده با AI
    vision_pages  INTEGER DEFAULT 0,              -- تعداد صفحه‌هایی که تصویرشان خوانده شد
    ai_repair     INTEGER DEFAULT 1,              -- آیا بازسازی متن با AI انجام شود
    progress      TEXT DEFAULT '',                -- توضیح مرحله‌ی جاری پردازش
    created_at    TEXT DEFAULT (datetime('now')),
    updated_at    TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS chunks (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    doc_id     INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    page       INTEGER DEFAULT 0,
    ord        INTEGER DEFAULT 0,
    text       TEXT NOT NULL,
    norm       TEXT NOT NULL,
    embedding  BLOB
);
CREATE INDEX IF NOT EXISTS idx_chunks_doc ON chunks(doc_id);

CREATE TABLE IF NOT EXISTS conversations (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    audience   TEXT NOT NULL DEFAULT 'public',    -- public (مشتری) | internal (پشتیبان)
    title      TEXT DEFAULT '',
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_conv_session ON conversations(session_id);

CREATE TABLE IF NOT EXISTS messages (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    conv_id     INTEGER NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    role        TEXT NOT NULL,                    -- user | assistant
    content     TEXT NOT NULL,
    sources     TEXT DEFAULT '[]',
    model       TEXT DEFAULT '',
    latency_ms  INTEGER DEFAULT 0,
    grounded    INTEGER DEFAULT 1,                -- ۰ یعنی در مستندات پیدا نشد
    feedback    INTEGER DEFAULT 0,                -- ۱ مفید، -۱ غیرمفید
    created_at  TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_msg_conv ON messages(conv_id);

CREATE TABLE IF NOT EXISTS tickets (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    conv_id    INTEGER REFERENCES conversations(id) ON DELETE SET NULL,
    name       TEXT DEFAULT '',
    contact    TEXT DEFAULT '',
    subject    TEXT DEFAULT '',
    body       TEXT DEFAULT '',
    status     TEXT DEFAULT 'open',              -- open | done
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT
);
"""

DEFAULT_SETTINGS = {
    "customer_suggestions": json.dumps(
        [
            "چطور فاکتور برگشت از فروش ثبت کنم؟",
            "رمز ورود برنامه را فراموش کرده‌ام، چه کار کنم؟",
            "چگونه از اطلاعاتم پشتیبان (بکاپ) بگیرم؟",
            "چطور یک کالای جدید تعریف کنم؟",
        ],
        ensure_ascii=False,
    ),
    "agent_suggestions": json.dumps(
        [
            "خطای اتصال به SQL Server چه دلایلی دارد؟",
            "مراحل نصب کالر آی‌دی را بگو",
            "انتقال یک جدول از یک دیتابیس به دیتابیس دیگر",
            "تنظیمات پنل پیامک فروشگاهی",
        ],
        ensure_ascii=False,
    ),
    "welcome_customer": "سلام! 👋 من دستیار هوشمند {assistant} هستم. هر سوالی درباره‌ی {product} داری بپرس — از توی راهنماها برات پیدا می‌کنم.",
    "welcome_agent": "سلام همکار 👋 سوال فنی‌ات را بپرس؛ پاسخ را با ارجاع به فایل و شماره‌ی صفحه می‌دهم.",
}


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(config.DB_PATH, timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


@contextmanager
def get_conn():
    conn = _connect()
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


MIGRATIONS = [
    ("documents", "repaired", "INTEGER DEFAULT 0"),
    ("documents", "vision_pages", "INTEGER DEFAULT 0"),
    ("documents", "ai_repair", "INTEGER DEFAULT 1"),
    ("documents", "progress", "TEXT DEFAULT ''"),
]


def _migrate(conn: sqlite3.Connection) -> None:
    """ستون‌های جدید را به دیتابیس‌های قدیمی اضافه می‌کند."""
    for table, column, definition in MIGRATIONS:
        existing = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}
        if column not in existing:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def init_db() -> None:
    with _lock, get_conn() as conn:
        conn.executescript(SCHEMA)
        _migrate(conn)
        for key, value in DEFAULT_SETTINGS.items():
            conn.execute(
                "INSERT OR IGNORE INTO settings(key, value) VALUES (?, ?)", (key, value)
            )


def query(sql: str, params: Iterable[Any] = ()) -> list[sqlite3.Row]:
    with get_conn() as conn:
        return conn.execute(sql, tuple(params)).fetchall()


def query_one(sql: str, params: Iterable[Any] = ()) -> sqlite3.Row | None:
    with get_conn() as conn:
        return conn.execute(sql, tuple(params)).fetchone()


def execute(sql: str, params: Iterable[Any] = ()) -> int:
    with _lock, get_conn() as conn:
        cur = conn.execute(sql, tuple(params))
        return cur.lastrowid or cur.rowcount


def executemany(sql: str, seq: Iterable[Iterable[Any]]) -> None:
    with _lock, get_conn() as conn:
        conn.executemany(sql, [tuple(s) for s in seq])


def get_setting(key: str, default: str = "") -> str:
    row = query_one("SELECT value FROM settings WHERE key = ?", (key,))
    return row["value"] if row and row["value"] is not None else default


def set_setting(key: str, value: str) -> None:
    execute(
        "INSERT INTO settings(key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )


def get_json_setting(key: str, default: Any) -> Any:
    raw = get_setting(key, "")
    if not raw:
        return default
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return default
