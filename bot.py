"""«Понял.Код» — Telegram-бот (aiogram 3) + сервер Mini App.

Экспериментальный образовательный проект для Осенней школы абитуриентов
Института бизнеса БГУ. Не является официальным продуктом БГУ.

Один процесс: long polling бота + aiohttp-сервер (Mini App из webapp/ и API из api.py).
"""
from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass
from urllib.parse import urlparse

from dotenv import load_dotenv

load_dotenv()

from aiohttp import web  # noqa: E402
import httpx  # noqa: E402
from aiogram import Bot, Dispatcher, F, Router  # noqa: E402
from aiogram.client.default import DefaultBotProperties  # noqa: E402
from aiogram.enums import ChatAction, ChatType, ParseMode  # noqa: E402
from aiogram.filters import Command, CommandStart  # noqa: E402
from aiogram.types import (  # noqa: E402
    BotCommand, CallbackQuery, ErrorEvent, InlineKeyboardButton, InlineKeyboardMarkup,
    MenuButtonWebApp, Message, PreCheckoutQuery, WebAppInfo,
)

import ai  # noqa: E402
import users  # noqa: E402
from api import create_app  # noqa: E402
from payments import DONATE_AMOUNTS, invoice_params  # noqa: E402

logger = logging.getLogger("ponyal_kod")


@dataclass(frozen=True)
class Settings:
    bot_token: str
    webapp_url: str | None

    @classmethod
    def from_env(cls) -> "Settings":
        token = os.getenv("BOT_TOKEN", "").strip()
        if not token:
            raise SystemExit("Не задан BOT_TOKEN. Укажите токен от @BotFather в .env или в Environment на Render.")
        url = os.getenv("WEBAPP_URL", "").strip()
        parsed = urlparse(url)
        if url and (parsed.scheme != "https" or not parsed.netloc):
            logger.warning("WEBAPP_URL должен быть HTTPS-адресом. Кнопка Mini App отключена.")
            url = ""
        elif not url:
            logger.warning("WEBAPP_URL не задан. Кнопка Mini App отключена.")
        return cls(bot_token=token, webapp_url=url or None)


WELCOME_TEXT = (
    "Привет! 👋 Добро пожаловать в <b>«Понял.Код»</b>!\n\n"
    "Это экспериментальный образовательный проект, созданный специально "
    "для Осенней школы абитуриентов Института бизнеса БГУ.\n\n"
    "Наша цель — показать, что искусственный интеллект может не просто "
    "выдавать готовые ответы, а помогать действительно понимать информатику "
    "и программирование.\n\n"
    "Изучай, экспериментируй и учись мыслить самостоятельно! 💡\n\n"
    "⚠️ <i>Проект находится в тестовом режиме. Некоторые функции могут быть "
    "недоступны или работать нестабильно.</i>"
)
WEBAPP_MISSING_NOTE = "\n\n🛠 <i>Приложение пока не подключено — скоро появится.</i>"
HELP_TEXT = (
    "<b>Команды «Понял.Код»</b>\n\n"
    "/start — приветствие и вход в приложение\n"
    "/help — список команд\n"
    "/about — о проекте\n"
    "/donate — поддержать проект\n\n"
    "💬 Можно просто написать вопрос по информатике — ответит ИИ-наставник.\n"
    "🧪 <i>Бета-версия: функции добавляются постепенно.</i>"
)
ABOUT_TEXT = (
    "<b>«Понял.Код»</b> · бета-версия\n\n"
    "Экспериментальный образовательный проект для Осенней школы "
    "абитуриентов Института бизнеса БГУ.\n\n"
    "ИИ-наставник не выдаёт готовый код для копирования, а объясняет, "
    "разбирает ошибки и помогает научиться решать задачи самостоятельно.\n\n"
    "ℹ️ Проект не является официальным продуктом БГУ и не одобрен университетом."
)
DONATE_TEXT = (
    "⭐ <b>Поддержать проект</b>\n\n"
    "Добровольный донат через Telegram Stars. Выбери сумму — Telegram откроет окно оплаты.\n"
    "Спасибо, что помогаешь проекту развиваться! 💙"
)
AI_UNAVAILABLE_TEXT = "🧪 ИИ-наставник пока не подключён (функция в разработке). Доступные команды: /help"
RATE_LIMIT_TEXT = "Лимит сообщений наставнику на этот час исчерпан. Попробуй чуть позже."
GENERIC_ERROR_TEXT = "⚠️ Что-то пошло не так. Попробуй ещё раз чуть позже."

BOT_COMMANDS = [
    BotCommand(command="start", description="Начать и открыть приложение"),
    BotCommand(command="help", description="Список команд"),
    BotCommand(command="about", description="О проекте"),
    BotCommand(command="donate", description="Поддержать проект"),
]
SHORT_DESCRIPTION = "Экспериментальный ИИ-наставник по информатике. Бета-версия."
FULL_DESCRIPTION = (
    "«Понял.Код» — экспериментальный образовательный проект для Осенней школы абитуриентов "
    "Института бизнеса БГУ. ИИ помогает понимать информатику, а не просто копировать ответы. Бета-версия."
)

router = Router(name="main")
router.message.filter(F.chat.type == ChatType.PRIVATE)


def webapp_keyboard(settings: Settings) -> InlineKeyboardMarkup | None:
    if not settings.webapp_url:
        return None
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🚀 Перейти в приложение", web_app=WebAppInfo(url=settings.webapp_url))
    ]])


def donate_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=f"⭐ {a}", callback_data=f"donate:{a}") for a in DONATE_AMOUNTS
    ]])


@router.message(CommandStart())
async def cmd_start(message: Message, settings: Settings) -> None:
    keyboard = webapp_keyboard(settings)
    await message.answer(WELCOME_TEXT if keyboard else WELCOME_TEXT + WEBAPP_MISSING_NOTE, reply_markup=keyboard)


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(HELP_TEXT)


@router.message(Command("about"))
async def cmd_about(message: Message) -> None:
    await message.answer(ABOUT_TEXT)


@router.message(Command("donate"))
async def cmd_donate(message: Message) -> None:
    await message.answer(DONATE_TEXT, reply_markup=donate_keyboard())


@router.callback_query(F.data.startswith("donate:"))
async def on_donate(cb: CallbackQuery, bot: Bot) -> None:
    try:
        amount = int((cb.data or "").split(":")[1])
    except (IndexError, ValueError):
        amount = 0
    if amount in DONATE_AMOUNTS:
        await bot.send_invoice(chat_id=cb.from_user.id, **invoice_params(amount, cb.from_user.id))
    await cb.answer()


@router.pre_checkout_query()
async def on_pre_checkout(query: PreCheckoutQuery) -> None:
    await query.answer(ok=True)


@router.message(F.successful_payment)
async def on_paid(message: Message) -> None:
    logger.info("Получен донат: %s", message.successful_payment.invoice_payload)
    await message.answer("Спасибо за поддержку! 💙")


@router.message(Command("stats"))
async def cmd_stats(message: Message) -> None:
    """Статистика пользователей — только для владельца (ADMIN_ID в .env)."""
    admin = os.getenv("ADMIN_ID", "").strip()
    if message.from_user is None or not admin.isdigit() or message.from_user.id != int(admin):
        await message.answer("Не знаю такой команды. Список команд: /help")
        return
    try:
        s = await users.stats()
    except Exception:  # noqa: BLE001
        logger.exception("Не удалось получить статистику")
        await message.answer("⚠️ Не удалось прочитать базу пользователей.")
        return
    lines = [
        f"👥 Всего пользователей: {s['total']}",
        f"🟢 Активны за 24 часа: {s['active_24h']}",
        f"💾 Хранилище: {users.backend_name()}",
    ]
    if s["recent"]:
        lines.append("\nПоследние новые:")
        for uid, username, name, first_seen in s["recent"]:
            label = f"@{username}" if username else (name or "без имени")
            lines.append(f"• {uid} — {label}")
    await message.answer("\n".join(lines), parse_mode=None)


@router.message(F.text)
async def on_text(message: Message) -> None:
    """Обычный текст → ИИ-наставник."""
    if message.from_user is None or message.text is None:
        return
    if message.text.startswith("/"):
        await message.answer("Не знаю такой команды. Список команд: /help")
        return
    if not ai.ai_enabled():
        await message.answer(AI_UNAVAILABLE_TEXT)
        return
    if not ai.check_rate_limit(message.from_user.id):
        await message.answer(RATE_LIMIT_TEXT)
        return
    await message.bot.send_chat_action(message.chat.id, ChatAction.TYPING)
    try:
        result = await ai.ask_tutor(message.from_user.id, message.text[:4000])
    except ai.OpenRouterError:
        await message.answer(ai.FALLBACK_ERROR_TEXT)
        return
    await message.answer(result["answer"], parse_mode=None)  # ответ ИИ — обычный текст, без HTML


@router.message()
async def on_other(message: Message) -> None:
    await message.answer("Я пока понимаю только текст и команды. См. /help")


async def on_error(event: ErrorEvent) -> bool:
    logger.exception("Ошибка при обработке обновления", exc_info=event.exception)
    message = event.update.message
    if message is not None:
        try:
            await message.answer(GENERIC_ERROR_TEXT)
        except Exception:  # noqa: BLE001
            logger.exception("Не удалось отправить сообщение об ошибке")
    return True


async def track_users(handler, event: Message, data: dict):
    """Записывает каждого, кто написал боту (включая /start)."""
    u = event.from_user
    if u is not None and not u.is_bot and event.chat.type == ChatType.PRIVATE:
        await users.touch(u.id, u.username, u.first_name)
    return await handler(event, data)


async def keep_alive(url: str) -> None:
    """Раз в 10 минут обращается к собственному /health: Render Free усыпляет сервис
    после 15 минут без входящих запросов. Дополняет внешний пингер (UptimeRobot)."""
    async with httpx.AsyncClient(timeout=15.0) as client:
        while True:
            await asyncio.sleep(600)
            try:
                await client.get(f"{url}/health")
            except httpx.HTTPError as e:
                logger.warning("keep-alive не удался: %s", e)


async def setup_bot(bot: Bot, settings: Settings) -> None:
    await bot.set_my_commands(BOT_COMMANDS)
    await bot.set_my_short_description(SHORT_DESCRIPTION)
    await bot.set_my_description(FULL_DESCRIPTION)
    if settings.webapp_url:
        await bot.set_chat_menu_button(
            menu_button=MenuButtonWebApp(text="Понял.Код", web_app=WebAppInfo(url=settings.webapp_url))
        )


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    settings = Settings.from_env()
    bot = Bot(token=settings.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher(settings=settings)
    dp.include_router(router)
    dp.message.outer_middleware(track_users)
    dp.errors.register(on_error)

    # Mini App + API (Render требует открытый порт PORT)
    runner = web.AppRunner(create_app(bot, settings.bot_token))
    await runner.setup()
    port = int(os.getenv("PORT", "8080"))
    await web.TCPSite(runner, "0.0.0.0", port).start()
    logger.info("Веб-сервер запущен на порту %s; ИИ %s", port, "включён" if ai.ai_enabled() else "не подключён")

    await setup_bot(bot, settings)
    await bot.delete_webhook()
    logger.info("Бот запущен")
    keep_task = None
    ka_url = os.getenv("RENDER_EXTERNAL_URL") or settings.webapp_url
    if ka_url and os.getenv("KEEP_ALIVE", "1") != "0":
        keep_task = asyncio.create_task(keep_alive(ka_url.rstrip("/")))
    try:
        await dp.start_polling(bot)
    finally:
        if keep_task:
            keep_task.cancel()
        await runner.cleanup()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
