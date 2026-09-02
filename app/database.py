from collections.abc import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings


class Base(DeclarativeBase):
    pass


_engine: Engine | None = None
_SessionLocal: sessionmaker[Session] | None = None
_current_database_url: str | None = None


def _is_sqlite_url(database_url: str) -> bool:
    return database_url.startswith("sqlite")


def configure_database(database_url: str) -> None:
    global _engine, _SessionLocal, _current_database_url

    if _engine is not None and _current_database_url == database_url:
        return

    if _engine is not None:
        _engine.dispose()

    connect_args = {"check_same_thread": False} if _is_sqlite_url(database_url) else {}
    _engine = create_engine(database_url, future=True, connect_args=connect_args)

    if _is_sqlite_url(database_url):

        @event.listens_for(_engine, "connect")
        def _set_sqlite_pragma(dbapi_connection, _connection_record) -> None:  # type: ignore[no-untyped-def]
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    _SessionLocal = sessionmaker(bind=_engine, autocommit=False, autoflush=False, expire_on_commit=False, future=True)
    _current_database_url = database_url


def get_engine() -> Engine:
    if _engine is None:
        configure_database(get_settings().database_url)

    assert _engine is not None
    return _engine


def get_session_factory() -> sessionmaker[Session]:
    if _SessionLocal is None:
        configure_database(get_settings().database_url)

    assert _SessionLocal is not None
    return _SessionLocal


def init_db() -> None:
    from app import models  # noqa: F401

    Base.metadata.create_all(bind=get_engine())


def drop_db() -> None:
    from app import models  # noqa: F401

    Base.metadata.drop_all(bind=get_engine())


def get_db() -> Generator[Session, None, None]:
    db = get_session_factory()()
    try:
        yield db
    finally:
        db.close()
