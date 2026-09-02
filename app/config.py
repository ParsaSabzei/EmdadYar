from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
import os

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


@dataclass(frozen=True)
class Settings:
    app_name: str
    app_host: str
    app_port: int
    debug: bool
    secret_key: str
    database_url: str
    initial_admin_username: str | None
    initial_admin_password: str | None
    bale_bot_token: str | None


@lru_cache
def get_settings() -> Settings:
    return Settings(
        app_name=os.getenv("APP_NAME", "Emdadyar"),
        app_host=os.getenv("APP_HOST", "127.0.0.1"),
        app_port=int(os.getenv("APP_PORT", "8000")),
        debug=os.getenv("DEBUG", "false").lower() == "true",
        secret_key=os.getenv("SECRET_KEY", "change-me-in-production"),
        database_url=os.getenv("DATABASE_URL", "sqlite:///./emdadyar.db"),
        initial_admin_username=os.getenv("INITIAL_ADMIN_USERNAME"),
        initial_admin_password=os.getenv("INITIAL_ADMIN_PASSWORD"),
        bale_bot_token=os.getenv("BALE_BOT_TOKEN"),
    )


def clear_settings_cache() -> None:
    get_settings.cache_clear()
