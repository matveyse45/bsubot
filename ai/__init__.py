"""ИИ-наставник «Понял.Код»: точка входа ask_tutor() для бота и Mini App."""
import os
import time
from collections import defaultdict, deque

from . import materials
from .knowledge import load_curriculum
from .memory import add_exchange, get_history, reset_history
from .openrouter import OpenRouterError, ask_openrouter, is_configured
from .prompt import MODES, build_system_prompt, clean_profile

__all__ = [
    "OpenRouterError", "FALLBACK_ERROR_TEXT", "ai_enabled", "ask_tutor",
    "check_rate_limit", "reset_history", "find_task", "materials",
]

FALLBACK_ERROR_TEXT = "Нейросеть сейчас не отвечает 😅 Попробуй ещё раз через минуту."

ai_enabled = is_configured

_rate_log: dict = defaultdict(deque)


def check_rate_limit(key, limit: int | None = None, window_sec: int = 3600) -> bool:
    """True, если можно писать дальше (попытка учитывается). Модели бесплатные — лимит нужен."""
    limit = limit or int(os.getenv("AI_RATE_LIMIT", "30"))
    now = time.monotonic()
    log = _rate_log[key]
    while log and now - log[0] > window_sec:
        log.popleft()
    if len(log) >= limit:
        return False
    log.append(now)
    return True


def find_task(task_id) -> dict | None:
    for topic in load_curriculum()["topics"]:
        for task in topic["tasks"]:
            if task["id"] == task_id:
                return task
    return None


async def ask_tutor(user_id, text, mode="mentor", profile=None, task_id=None, hint_level=1) -> dict:
    """Возвращает {"answer": str, "sources": [str]}. Бросает OpenRouterError при сбое."""
    mode = mode if mode in MODES else "mentor"
    task = find_task(task_id) if task_id else None
    try:
        hint_level = min(max(int(hint_level), 1), 3)
    except (TypeError, ValueError):
        hint_level = 1

    snippets = materials.search(f"{text} {task['title'] if task else ''}")
    system = build_system_prompt(mode, clean_profile(profile), task, snippets, hint_level)
    messages = get_history(user_id) + [{"role": "user", "content": text}]

    answer = await ask_openrouter(system, messages)
    stored = text[:1500] if mode == "mentor" else f"[{mode}] {text[:1500]}"
    add_exchange(user_id, stored, answer)
    return {"answer": answer, "sources": sorted({s["source"] for s in snippets})}
