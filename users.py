"""Учёт пользователей бота: Telegram ID, имя, когда пришёл и когда был последний раз.

Хранилище выбирается автоматически:
  * заданы UPSTASH_REDIS_REST_URL и UPSTASH_REDIS_REST_TOKEN — Upstash Redis по HTTPS.
    Данные ПОСТОЯННЫЕ: переживают сон, перезапуск и редеплой Render (рекомендуется);
  * иначе — локальный SQLite (USERS_DB_PATH, по умолчанию data/users.db). На бесплатном
    Render файловая система сбрасывается при каждом сне/редеплое — подходит только для
    локальной разработки.

Для нового пользователя в лог пишется строка «Новый пользователь: …».
"""
import asyncio
import logging
import os
import sqlite3
import time
from pathlib import Path

import httpx

logger = logging.getLogger("ponyal_kod.users")

THROTTLE_SEC = 60  # не писать в базу чаще раза в минуту на пользователя (экономит лимит Upstash)
_last_touch: dict[int, float] = {}

# ---------------------------------------------------------------------------
# Upstash Redis (REST)
# ---------------------------------------------------------------------------


def _redis_cfg() -> tuple[str, str] | None:
    url = os.getenv("UPSTASH_REDIS_REST_URL", "").strip().rstrip("/")
    token = os.getenv("UPSTASH_REDIS_REST_TOKEN", "").strip()
    return (url, token) if url and token else None


def backend_name() -> str:
    return "Upstash Redis (постоянное)" if _redis_cfg() else "SQLite (временное: на Render Free сбрасывается)"


async def _redis(commands: list[list]) -> list:
    """Выполняет несколько Redis-команд одним HTTPS-запросом (pipeline)."""
    url, token = _redis_cfg()  # type: ignore[misc]
    async with httpx.AsyncClient(timeout=8.0) as client:
        r = await client.post(
            f"{url}/pipeline",
            headers={"Authorization": f"Bearer {token}"},
            json=[[str(x) for x in cmd] for cmd in commands],
        )
        r.raise_for_status()
    results = []
    for item in r.json():
        if item.get("error"):
            raise RuntimeError(f"Upstash: {item['error']}")
        results.append(item.get("result"))
    return results


async def _touch_redis(user_id: int, username: str | None, first_name: str | None) -> None:
    now = int(time.time())
    key = f"user:{user_id}"
    fields: list = ["last_seen", now]
    if username:
        fields += ["username", username]
    if first_name:
        fields += ["first_name", first_name]
    res = await _redis([
        ["ZADD", "users:first", "NX", now, user_id],  # 1, если пользователь новый
        ["ZADD", "users:seen", now, user_id],
        ["HSET", key, *fields],
        ["HINCRBY", key, "events", 1],
    ])
    if res[0] == 1:
        logger.info("Новый пользователь: id=%s username=%s name=%s", user_id, username, first_name)


async def _stats_redis() -> dict:
    now = int(time.time())
    total, active, flat = await _redis([
        ["ZCARD", "users:first"],
        ["ZCOUNT", "users:seen", now - 24 * 3600, "+inf"],
        ["ZREVRANGE", "users:first", 0, 9, "WITHSCORES"],
    ])
    pairs = [(int(flat[i]), int(float(flat[i + 1]))) for i in range(0, len(flat), 2)]
    names = await _redis([["HMGET", f"user:{uid}", "username", "first_name"] for uid, _ in pairs]) if pairs else []
    recent = [(uid, nm[0], nm[1], first) for (uid, first), nm in zip(pairs, names)]
    return {"total": total, "active_24h": active, "recent": recent}


# ---------------------------------------------------------------------------
# SQLite (локальная разработка)
# ---------------------------------------------------------------------------

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


def _touch_sqlite(user_id: int, username: str | None, first_name: str | None) -> None:
    now = int(time.time())
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


def _stats_sqlite() -> dict:
    day_ago = int(time.time()) - 24 * 3600
    with _connect() as conn:
        total = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        active = conn.execute("SELECT COUNT(*) FROM users WHERE last_seen >= ?", (day_ago,)).fetchone()[0]
        recent = conn.execute(
            "SELECT user_id, username, first_name, first_seen FROM users ORDER BY first_seen DESC LIMIT 10"
        ).fetchall()
    return {"total": total, "active_24h": active, "recent": recent}


# ---------------------------------------------------------------------------
# Публичный интерфейс
# ---------------------------------------------------------------------------


async def touch(user_id: int, username: str | None = None, first_name: str | None = None) -> None:
    """Записывает пользователя (или обновляет «последний визит»). Ошибки не ломают бота."""
    now = time.monotonic()
    if now - _last_touch.get(user_id, -1e9) < THROTTLE_SEC:
        return
    _last_touch[user_id] = now
    try:
        if _redis_cfg():
            await _touch_redis(user_id, username, first_name)
        else:
            await asyncio.to_thread(_touch_sqlite, user_id, username, first_name)
    except Exception:  # noqa: BLE001
        logger.exception("Не удалось записать пользователя %s", user_id)


async def stats() -> dict:
    """Всего пользователей, активных за 24 часа и последние 10 пришедших."""
    if _redis_cfg():
        return await _stats_redis()
    return await asyncio.to_thread(_stats_sqlite)
