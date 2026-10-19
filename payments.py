"""Донаты в Telegram Stars (валюта XTR, provider_token не нужен)."""
from aiogram.types import LabeledPrice

DONATE_AMOUNTS = (50, 100, 250)


def invoice_params(amount: int, user_id: int) -> dict:
    return dict(
        title="Поддержка «Понял.Код»",
        description="Добровольное пожертвование на развитие экспериментального проекта.",
        payload=f"donate:{user_id}:{amount}",
        currency="XTR",
        prices=[LabeledPrice(label="Поддержка проекта", amount=amount)],
    )
