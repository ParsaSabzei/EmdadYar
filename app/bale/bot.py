import asyncio

from app.auth import ensure_initial_admin
from app.config import get_settings
from app.database import configure_database, init_db


def create_bot():
    try:
        asyncio.get_event_loop()
    except RuntimeError:
        asyncio.set_event_loop(asyncio.new_event_loop())

    try:
        from balethon import Client
    except ModuleNotFoundError as exc:  # pragma: no cover
        raise RuntimeError("Balethon is not installed. Install requirements first.") from exc
    except Exception as exc:  # pragma: no cover
        raise RuntimeError(f"Failed to initialize Balethon: {exc}") from exc

    settings = get_settings()
    if not settings.bale_bot_token:
        raise RuntimeError("BALE_BOT_TOKEN is not set")

    bot = Client(settings.bale_bot_token)

    from app.bale.handlers import register_handlers

    register_handlers(bot)
    return bot


def run_bot() -> None:
    settings = get_settings()
    configure_database(settings.database_url)
    init_db()
    ensure_initial_admin()

    bot = create_bot()
    if hasattr(bot, "run_polling"):
        bot.run_polling()
    else:
        bot.run()
