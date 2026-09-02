import asyncio

from app.config import get_settings


def send_text_message(chat_id: str, text: str) -> None:
    if not text.strip():
        raise ValueError("Message text cannot be empty")

    settings = get_settings()
    if not settings.bale_bot_token:
        raise RuntimeError("BALE_BOT_TOKEN is not set")

    try:
        asyncio.get_event_loop()
    except RuntimeError:
        asyncio.set_event_loop(asyncio.new_event_loop())

    from balethon import Client

    client = Client(settings.bale_bot_token)
    client.send_message(chat_id=chat_id, text=text.strip())
