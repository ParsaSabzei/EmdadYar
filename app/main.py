from contextlib import asynccontextmanager

from fastapi import FastAPI
from starlette.middleware.sessions import SessionMiddleware

from app.auth import ensure_initial_admin
from app.config import get_settings
from app.database import configure_database, init_db
from app.routes.admin import router as admin_router
from app.routes.auth import router as auth_router
from app.routes.health import router as health_router


@asynccontextmanager
async def lifespan(_app: FastAPI):
    settings = get_settings()
    configure_database(settings.database_url)
    init_db()
    ensure_initial_admin()
    yield


settings = get_settings()
app = FastAPI(title=settings.app_name, debug=settings.debug, lifespan=lifespan)
app.add_middleware(SessionMiddleware, secret_key=settings.secret_key)

app.include_router(health_router)
app.include_router(auth_router)
app.include_router(admin_router)
