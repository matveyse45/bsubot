"""Учёт пользователей бота: Telegram ID, имя, когда пришёл и когда был последний раз.

Хранится в SQLite (стандартная библиотека). Путь к файлу — переменная USERS_DB_PATH
(по умолчанию data/users.db). Внимание: на бесплатном Render файловая система сбрасывается
при каждом деплое/перезапуске, поэтому о каждом НОВОМ пользователе дополнительно пишется
строка в лог («Новый пользователь: …») — она остаётся в логах Render.
"""
import logging
import os
import sqlite3
import time
from pathlib import Path

logger = logging.getLogger("ponyal_kod.users")

_DB_PATH = Path(os.getenv("USERS_DB_PATH") or Path(__file__).resolve().parent / "data" / "users.db")
_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    user_id    INTEGER PRIMARY KEY,
    username   TEXT,
    first_name TEXT,
    first_seen INTEGER NOT NULL,
    last_seen  INTEGER NOT NULL,
    events     INTEGER NOT NULL DEFAULT 1
)
"""


def _connect() -> sqlite3.Connection:
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(_DB_PATH)
    conn.execute(_SCHEMA)
    return conn


def touch(user_id: int, username: str | None = None, first_name: str | None = None) -> None:
    """Записывает пользователя (или обновляет «последний визит»). Ошибки не ломают бота."""
    now = int(time.time())
    try:
        with _connect() as conn:
            row = conn.execute("SELECT 1 FROM users WHERE user_id = ?", (user_id,)).fetchone()
            if row is None:
                conn.execute(
                    "INSERT INTO users (user_id, username, first_name, first_seen, last_seen) VALUES (?, ?, ?, ?, ?)",
                    (user_id, username, first_name, now, now),
                )
                logger.info("Новый пользователь: id=%s username=%s name=%s", user_id, username, first_name)
            else:
                conn.execute(
                    "UPDATE users SET last_seen = ?, events = events + 1,"
                    " username = COALESCE(?, username), first_name = COALESCE(?, first_name) WHERE user_id = ?",
                    (now, username, first_name, user_id),
                )
    except sqlite3.Error:
        logger.exception("Не удалось записать пользователя %s", user_id)


def stats() -> dict:
    """Всего пользователей, активных за 24 часа и последние 10 пришедших."""
    day_ago = int(time.time()) - 24 * 3600
    with _connect() as conn:
        total = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        active = conn.execute("SELECT COUNT(*) FROM users WHERE last_seen >= ?", (day_ago,)).fetchone()[0]
        recent = conn.execute(
            "SELECT user_id, username, first_name, first_seen FROM users ORDER BY first_seen DESC LIMIT 10"
        ).fetchall()
    return {"total": total, "active_24h": active, "recent": recent}
