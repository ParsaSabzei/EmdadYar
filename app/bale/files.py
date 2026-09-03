from __future__ import annotations

import asyncio
import inspect

from app.config import get_settings
from app.services.file_storage import StoredFile, store_request_file


async def _await_if_needed(value):
    if inspect.isawaitable(value):
        return await value
    return value


async def download_and_store_bale_file(
    *,
    request_id: int,
    file_id: str,
    original_filename: str | None,
    mime_type: str | None,
    declared_size: int | None,
) -> StoredFile:
    settings = get_settings()
    if not settings.bale_bot_token:
        raise RuntimeError("BALE_BOT_TOKEN is not set")

    try:
        asyncio.get_event_loop()
    except RuntimeError:
        asyncio.set_event_loop(asyncio.new_event_loop())

    from balethon import Client

    client = Client(settings.bale_bot_token)
    await _await_if_needed(client.connect())
    try:
        file_bytes = await _await_if_needed(client.download(file_id))
    finally:
        await _await_if_needed(client.disconnect())

    if not isinstance(file_bytes, (bytes, bytearray)):
        raise RuntimeError("Failed to download file from Bale")

    return store_request_file(
        request_id=request_id,
        content=bytes(file_bytes),
        filename=original_filename,
        mime_type=mime_type,
        declared_size=declared_size,
    )
