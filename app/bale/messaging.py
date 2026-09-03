import asyncio
import inspect

from app.config import get_settings


def _run_awaitable(value):
    if not inspect.isawaitable(value):
        return value

    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    if loop.is_running():
        return value

    return loop.run_until_complete(value)


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
    _run_awaitable(client.connect())
    try:
        _run_awaitable(client.send_message(chat_id=chat_id, text=text.strip()))
    finally:
        _run_awaitable(client.disconnect())
