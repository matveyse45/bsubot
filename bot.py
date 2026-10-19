"""«Понял.Код» — Telegram-бот (aiogram 3).

Экспериментальный образовательный проект для Осенней школы абитуриентов
Института бизнеса БГУ. Не является официальным продуктом БГУ.

Что реализовано сейчас:
  * /start, /help, /about, /donate;
  * меню команд и кнопка Mini App (по WEBAPP_URL из .env);
  * понятные сообщения об ошибках;
  * точка интеграции ИИ (AITutor) — реализация подключается отдельно.

Что НЕ реализовано (и не имитируется): ИИ-ответы, оплата Telegram Stars,
поиск по учебникам.
"""

from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass
from urllib.parse import urlparse
from typing import Protocol

from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ChatType, ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    BotCommand,
    ErrorEvent,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    MenuButtonWebApp,
    Message,
    WebAppInfo,
)
from aiohttp import web
from dotenv import load_dotenv

logger = logging.getLogger("ponyal_kod")

# ---------------------------------------------------------------------------
# Конфигурация
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Settings:
    bot_token: str
    webapp_url: str | None  # None — Mini App ещё не настроено

    @classmethod
    def from_env(cls) -> "Settings":
        load_dotenv()

        token = os.getenv("BOT_TOKEN", "").strip()
        if not token:
            raise SystemExit(
                "Не задан BOT_TOKEN. Скопируйте .env.example в .env "
                "и укажите токен от @BotFather."
            )

        url = os.getenv("WEBAPP_URL", "").strip()
        if url:
            parsed = urlparse(url)
            if parsed.scheme != "https" or not parsed.netloc:
                logger.warning(
                    "WEBAPP_URL должен быть настоящим HTTPS-адресом "
                    "(Telegram не принимает другие). Кнопка Mini App отключена."
                )
                url = ""
        else:
            logger.warning("WEBAPP_URL не задан. Кнопка Mini App отключена.")

        return cls(bot_token=token, webapp_url=url or None)


# ---------------------------------------------------------------------------
# Тексты
# ---------------------------------------------------------------------------

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

WEBAPP_MISSING_NOTE = (
    "\n\n🛠 <i>Приложение пока не подключено — скоро появится.</i>"
)

HELP_TEXT = (
    "<b>Команды «Понял.Код»</b>\n\n"
    "/start — приветствие и вход в приложение\n"
    "/help — список команд\n"
    "/about — о проекте\n"
    "/donate — поддержать проект\n\n"
    "🧪 <i>Бета-версия: функции добавляются постепенно.</i>"
)

ABOUT_TEXT = (
    "<b>«Понял.Код»</b> · бета-версия\n\n"
    "Экспериментальный образовательный проект для Осенней школы "
    "абитуриентов Института бизнеса БГУ.\n\n"
    "Идея: ИИ-наставник не выдаёт готовый код для копирования, а объясняет, "
    "разбирает ошибки и помогает научиться решать задачи самостоятельно.\n\n"
    "<b>В разработке:</b>\n"
    "• ИИ-наставник\n"
    "• учебная программа и практика\n"
    "• учебники и поиск по ним\n"
    "• личный прогресс\n\n"
    "ℹ️ Проект не является официальным продуктом БГУ и не одобрен "
    "университетом."
)

DONATE_TEXT = (
    "⭐ <b>Поддержать проект</b>\n\n"
    "Добровольная поддержка через Telegram Stars находится в разработке и "
    "пока недоступна.\n\n"
    "Спасибо, что следишь за проектом! 💙"
)

AI_UNAVAILABLE_TEXT = (
    "🧪 ИИ-наставник пока в разработке и не подключён.\n\n"
    "Пока доступны команды: /help"
)

GENERIC_ERROR_TEXT = (
    "⚠️ Что-то пошло не так. Попробуй ещё раз чуть позже.\n"
    "Если ошибка повторяется — проект в тестовом режиме, это нормально."
)

BOT_COMMANDS = [
    BotCommand(command="start", description="Начать и открыть приложение"),
    BotCommand(command="help", description="Список команд"),
    BotCommand(command="about", description="О проекте"),
    BotCommand(command="donate", description="Поддержать проект"),
]

SHORT_DESCRIPTION = (
    "Экспериментальный ИИ-наставник по информатике. Бета-версия."
)
FULL_DESCRIPTION = (
    "«Понял.Код» — экспериментальный образовательный проект для Осенней "
    "школы абитуриентов Института бизнеса БГУ. ИИ помогает понимать "
    "информатику, а не просто копировать ответы. Бета-версия."
)

# ---------------------------------------------------------------------------
# Точка интеграции ИИ (OpenRouter будет подключён отдельно)
# ---------------------------------------------------------------------------
#
# Как подключить: создайте класс, реализующий AITutor.reply(), например
# OpenRouterTutor в отдельном файле ai.py, и передайте его в main()
# вместо UnavailableTutor(). Остальной код менять не нужно.


class TutorUnavailableError(Exception):
    """ИИ-наставник не подключён или временно недоступен."""


@dataclass(frozen=True)
class TutorRequest:
    user_id: int
    text: str
    language: str | None = None  # язык программирования: "cpp", "python", ...
    grade: str | None = None     # класс/уровень ученика
    # В будущем: история диалога, найденные фрагменты учебников и т.д.


class AITutor(Protocol):
    async def reply(self, request: TutorRequest) -> str:
        """Вернуть обучающий ответ на сообщение пользователя."""
        ...


class UnavailableTutor:
    """Заглушка: честно сообщает, что ИИ ещё не подключён."""

    async def reply(self, request: TutorRequest) -> str:
        raise TutorUnavailableError("ИИ-наставник не подключён")


# ---------------------------------------------------------------------------
# Клавиатуры
# ---------------------------------------------------------------------------


def webapp_keyboard(settings: Settings) -> InlineKeyboardMarkup | None:
    """Кнопка Mini App. Без настоящего HTTPS-URL кнопку не показываем."""
    if not settings.webapp_url:
        return None
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🚀 Перейти в приложение",
                    web_app=WebAppInfo(url=settings.webapp_url),
                )
            ]
        ]
    )


# ---------------------------------------------------------------------------
# Обработчики
# ---------------------------------------------------------------------------

router = Router(name="main")
router.message.filter(F.chat.type == ChatType.PRIVATE)


@router.message(CommandStart())
async def cmd_start(message: Message, settings: Settings) -> None:
    keyboard = webapp_keyboard(settings)
    text = WELCOME_TEXT if keyboard else WELCOME_TEXT + WEBAPP_MISSING_NOTE
    await message.answer(text, reply_markup=keyboard)


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(HELP_TEXT)


@router.message(Command("about"))
async def cmd_about(message: Message) -> None:
    await message.answer(ABOUT_TEXT)


@router.message(Command("donate"))
async def cmd_donate(message: Message) -> None:
    # Оплата Telegram Stars пока не реализована — кнопку оплаты не показываем.
    # Позже: bot.send_invoice(currency="XTR", provider_token="", ...)
    # + обработчики pre_checkout_query и successful_payment.
    await message.answer(DONATE_TEXT)


@router.message(F.text)
async def on_text(message: Message, tutor: AITutor) -> None:
    """Обычный текст → ИИ-наставник (когда он будет подключён)."""
    if message.from_user is None or message.text is None:
        return
    request = TutorRequest(user_id=message.from_user.id, text=message.text)
    try:
        answer = await tutor.reply(request)
    except TutorUnavailableError:
        await message.answer(AI_UNAVAILABLE_TEXT)
        return
    await message.answer(answer)


@router.message()
async def on_other(message: Message) -> None:
    await message.answer("Я пока понимаю только текст и команды. См. /help")


async def on_error(event: ErrorEvent) -> bool:
    logger.exception("Ошибка при обработке обновления", exc_info=event.exception)
    message = event.update.message
    if message is not None:
        try:
            await message.answer(GENERIC_ERROR_TEXT)
        except Exception:  # noqa: BLE001 — не даём ошибке обработчика ошибок упасть
            logger.exception("Не удалось отправить сообщение об ошибке")
    return True


# ---------------------------------------------------------------------------
# Запуск
# ---------------------------------------------------------------------------


async def setup_bot(bot: Bot, settings: Settings) -> None:
    """Меню команд, описания и кнопка меню Mini App."""
    await bot.set_my_commands(BOT_COMMANDS)
    await bot.set_my_short_description(SHORT_DESCRIPTION)
    await bot.set_my_description(FULL_DESCRIPTION)
    if settings.webapp_url:
        await bot.set_chat_menu_button(
            menu_button=MenuButtonWebApp(
                text="Понял.Код",
                web_app=WebAppInfo(url=settings.webapp_url),
            )
        )


async def start_health_server() -> web.AppRunner | None:
    """Мини-сервер для Render Web Service: он требует открытый порт (PORT).

    Если переменной PORT нет (локальный запуск или Background Worker),
    сервер не запускается.
    """
    port = os.getenv("PORT")
    if not port:
        return None

    async def health(_: web.Request) -> web.Response:
        return web.Response(text="OK")

    app = web.Application()
    app.router.add_get("/", health)
    app.router.add_get("/health", health)
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", int(port)).start()
    logger.info("Health-сервер запущен на порту %s", port)
    return runner


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    settings = Settings.from_env()

    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    # tutor и settings передаются в хендлеры по имени параметра
    dp = Dispatcher(settings=settings, tutor=UnavailableTutor())
    dp.include_router(router)
    dp.errors.register(on_error)

    health_runner = await start_health_server()
    await setup_bot(bot, settings)
    await bot.delete_webhook()  # на случай, если раньше был webhook
    logger.info("Бот запущен")
    try:
        await dp.start_polling(bot)
    finally:
        if health_runner is not None:
            await health_runner.cleanup()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
