"""HTTP-слой: отдаёт Mini App (webapp/) и API для него.

Все методы, которые тратят ресурсы (ИИ, материалы, донаты), требуют подпись Telegram
initData — запросы не из Telegram отклоняются.
"""
import hashlib
import hmac
import json
import logging
import time
from pathlib import Path
from urllib.parse import parse_qsl

from aiohttp import web

import ai
import users
from ai.knowledge import load_curriculum
from payments import DONATE_AMOUNTS, invoice_params

logger = logging.getLogger("ponyal_kod.api")
WEBAPP_DIR = Path(__file__).resolve().parent / "webapp"
MAX_AUTH_AGE = 24 * 3600


class ApiError(Exception):
    def __init__(self, status: int, message: str):
        self.status, self.message = status, message


def verify_init_data(init_data: str, bot_token: str) -> dict | None:
    """Проверка подписи Telegram WebApp initData. Возвращает данные пользователя или None."""
    try:
        pairs = dict(parse_qsl(init_data, keep_blank_values=True, strict_parsing=True))
    except ValueError:
        return None
    received = pairs.pop("hash", None)
    if not received:
        return None
    check = "\n".join(f"{k}={v}" for k, v in sorted(pairs.items()))
    secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    expected = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, received):
        return None
    try:
        if time.time() - int(pairs.get("auth_date", "0")) > MAX_AUTH_AGE:
            return None
        user = json.loads(pairs["user"])
        return user if isinstance(user.get("id"), int) else None
    except (KeyError, ValueError, AttributeError):
        return None


async def _read(request: web.Request) -> tuple[dict, dict]:
    try:
        body = await request.json()
    except ValueError:
        body = None
    if not isinstance(body, dict):
        raise ApiError(400, "Некорректный запрос.")
    user = verify_init_data(str(body.get("initData", "")), request.app["bot_token"])
    if not user:
        raise ApiError(401, "Открой приложение внутри Telegram.")
    await users.touch(user["id"], user.get("username"), user.get("first_name"))
    return body, user


@web.middleware
async def errors_middleware(request, handler):
    try:
        return await handler(request)
    except ApiError as e:
        return web.json_response({"error": e.message}, status=e.status)
    except web.HTTPException:
        raise
    except Exception:
        logger.exception("Ошибка API")
        return web.json_response({"error": "Внутренняя ошибка сервера."}, status=500)


async def index(_):
    return web.FileResponse(WEBAPP_DIR / "index.html", headers={"Cache-Control": "no-cache"})


async def health(_):
    return web.Response(text="OK")


async def curriculum(_):
    return web.json_response(load_curriculum())


async def chat(request):
    body, user = await _read(request)
    if not ai.ai_enabled():
        raise ApiError(503, "ИИ-наставник ещё не подключён (функция в разработке).")
    text = str(body.get("message", "")).strip()[:4000]
    if not text:
        raise ApiError(400, "Пустое сообщение.")
    if not ai.check_rate_limit(user["id"]):
        raise ApiError(429, "Лимит сообщений наставнику на этот час исчерпан. Попробуй позже.")
    try:
        result = await ai.ask_tutor(
            user["id"], text, str(body.get("mode", "mentor")), body.get("profile"),
            body.get("taskId"), body.get("hintLevel", 1),
        )
    except ai.OpenRouterError:
        raise ApiError(502, ai.FALLBACK_ERROR_TEXT)
    return web.json_response(result)


async def reset(request):
    _, user = await _read(request)
    ai.reset_history(user["id"])
    return web.json_response({"ok": True})


async def materials(request):
    body, _ = await _read(request)
    query = str(body.get("query", "")).strip()[:200]
    return web.json_response({
        "files": ai.materials.sources(),
        "results": ai.materials.search(query, k=5) if query else [],
    })


async def donate(request):
    body, user = await _read(request)
    try:
        amount = int(body.get("amount", 0))
    except (TypeError, ValueError):
        amount = 0
    if amount not in DONATE_AMOUNTS:
        raise ApiError(400, "Недопустимая сумма.")
    link = await request.app["bot"].create_invoice_link(**invoice_params(amount, user["id"]))
    return web.json_response({"url": link})


def create_app(bot, bot_token: str) -> web.Application:
    app = web.Application(middlewares=[errors_middleware])
    app["bot"], app["bot_token"] = bot, bot_token
    app.router.add_get("/", index)
    app.router.add_get("/health", health)
    app.router.add_get("/api/curriculum", curriculum)
    app.router.add_post("/api/chat", chat)
    app.router.add_post("/api/reset", reset)
    app.router.add_post("/api/materials", materials)
    app.router.add_post("/api/donate", donate)
    app.router.add_static("/", WEBAPP_DIR)
    return app
