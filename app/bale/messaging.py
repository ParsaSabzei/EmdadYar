import asyncio

from app.config import get_settings


async def _send_text_message(chat_id: str, text: str) -> None:
    from balethon import Client

    settings = get_settings()
    client = Client(settings.bale_bot_token)

    await client.connect()
    try:
        await Client.send_message(
            client,
            chat_id=chat_id,
            text=text,
        )
    finally:
        await client.disconnect()


def send_text_message(chat_id: str, text: str) -> None:
    if not text.strip():
        raise ValueError("Message text cannot be empty")

    settings = get_settings()
    if not settings.bale_bot_token:
        raise RuntimeError("BALE_BOT_TOKEN is not set")

    asyncio.run(
        _send_text_message(
            chat_id,
            text.strip(),
        )
    )
