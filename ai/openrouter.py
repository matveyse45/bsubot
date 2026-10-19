import logging
import os
import re

import httpx

logger = logging.getLogger(__name__)

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

# Бесплатные модели периодически пропадают из каталога OpenRouter. Список можно
# поменять переменной OPENROUTER_MODELS (через запятую) без правки кода.
# "openrouter/free" — крайний резерв: может выбрать неподходящую для диалога модель.
_DEFAULT_MODELS = [
    "z-ai/glm-5.2:free",
    "nvidia/nemotron-3-super-120b-a12b:free",
    "google/gemma-4-26b-a4b-it:free",
    "openrouter/free",
]
_REQUEST_TIMEOUT = 45.0

_THINK_TAG = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)
_INVALID_OUTPUT = re.compile(
    r"(user safety\s*:|response safety\s*:|task:\s*check if there is unsafe content"
    r"|here'?s a thinking process|internal monologue|let me think step by step"
    r"|formulate response|final output construction)",
    re.IGNORECASE,
)


class OpenRouterError(Exception):
    """Ошибка обращения к OpenRouter (нет ключа, таймаут, все модели не ответили)."""


def is_configured() -> bool:
    return bool(os.getenv("OPENROUTER_API_KEY"))


def _models() -> list[str]:
    env = os.getenv("OPENROUTER_MODELS")
    models = [m.strip() for m in env.split(",") if m.strip()] if env else []
    return models or _DEFAULT_MODELS


def _clean(raw: str) -> str:
    cleaned = _THINK_TAG.sub("", raw).strip()
    return cleaned or raw.strip()


async def ask_openrouter(
    system_prompt: str,
    messages: list[dict],
    max_tokens: int = 900,
    temperature: float = 0.5,
) -> str:
    """Отправляет диалог в OpenRouter, перебирая модели по очереди.

    Модель пропускается при ошибке, пустом ответе, выводе классификатора
    безопасности или «сыром» ходе рассуждений. OpenRouterError — только если
    не сработала ни одна модель.
    """
    key = os.getenv("OPENROUTER_API_KEY")
    if not key:
        raise OpenRouterError("OPENROUTER_API_KEY не задан")

    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "HTTP-Referer": os.getenv("OPENROUTER_SITE_URL") or os.getenv("WEBAPP_URL") or "https://openrouter.ai",
        "X-Title": os.getenv("OPENROUTER_APP_TITLE", "Ponyal.Kod"),
    }
    full = [{"role": "system", "content": system_prompt}] + messages
    last_error: Exception | None = None

    async with httpx.AsyncClient(timeout=_REQUEST_TIMEOUT) as client:
        for model in _models():
            payload = {
                "model": model,
                "messages": full,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "reasoning": {"exclude": True},
            }
            try:
                r = await client.post(f"{OPENROUTER_BASE_URL}/chat/completions", headers=headers, json=payload)
                r.raise_for_status()
                raw = (r.json()["choices"][0]["message"]["content"] or "").strip()
                if not raw:
                    logger.warning("OpenRouter: %s вернула пустой ответ", model)
                    continue
                text = _clean(raw)
                if _INVALID_OUTPUT.search(text):
                    logger.warning("OpenRouter: %s вернула служебный вывод (%r)", model, text[:100])
                    continue
                return text
            except httpx.TimeoutException as e:
                logger.warning("OpenRouter: таймаут у %s", model)
                last_error = e
            except httpx.HTTPStatusError as e:
                logger.warning("OpenRouter: %s -> %s %s", model, e.response.status_code, e.response.text[:200])
                last_error = e
            except (KeyError, IndexError, ValueError, TypeError) as e:
                logger.warning("OpenRouter: некорректный ответ от %s", model)
                last_error = e
            except httpx.HTTPError as e:
                logger.warning("OpenRouter: сетевая ошибка у %s: %s", model, e)
                last_error = e

    logger.error("OpenRouter: ни одна модель не дала пригодный ответ")
    raise OpenRouterError("all_models_failed") from last_error
