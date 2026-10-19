from collections import defaultdict, deque

# Реплики пользователя и наставника вместе. Хранится в памяти процесса:
# при перезапуске сервиса диалоги обнуляются.
MAX_HISTORY_MESSAGES = 12

_conversations: dict[int, deque] = defaultdict(lambda: deque(maxlen=MAX_HISTORY_MESSAGES))


def get_history(user_id: int) -> list[dict]:
    return list(_conversations[user_id])


def add_exchange(user_id: int, user_text: str, assistant_text: str) -> None:
    h = _conversations[user_id]
    h.append({"role": "user", "content": user_text})
    h.append({"role": "assistant", "content": assistant_text})


def reset_history(user_id: int) -> None:
    _conversations.pop(user_id, None)
