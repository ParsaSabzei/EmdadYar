import importlib
import re
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.auth import hash_password
from app.config import clear_settings_cache
from app.database import configure_database, drop_db, get_session_factory, init_db
import app.main as main_module
from app.models import Admin, Service


def _setup_db(tmp_path: Path) -> str:
    db_path = tmp_path / "phase6.db"
    database_url = f"sqlite:///{db_path}"
    configure_database(database_url)
    drop_db()
    init_db()
    return database_url


def _prepare_env(monkeypatch, database_url: str, *, secure: bool = False, samesite: str = "lax") -> None:
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setenv("SECRET_KEY", "test-secret")
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "true" if secure else "false")
    monkeypatch.setenv("SESSION_COOKIE_SAMESITE", samesite)
    clear_settings_cache()


def _seed_admin(*, username: str = "admin", password: str = "secret", is_active: bool = True) -> None:
    session_factory = get_session_factory()
    with session_factory() as db:
        db.add(Admin(username=username, password_hash=hash_password(password), is_active=is_active))
        db.commit()


def _extract_csrf_token(html: str) -> str:
    match = re.search(r'name="csrf_token"\s+value="([^"]+)"', html)
    assert match is not None
    return match.group(1)


def _fresh_app():
    reloaded = importlib.reload(main_module)
    return reloaded.app


def _login(client: TestClient, *, username: str = "admin", password: str = "secret") -> str:
    login_page = client.get("/admin/login")
    assert login_page.status_code == 200
    csrf_token = _extract_csrf_token(login_page.text)

    response = client.post(
        "/admin/login",
        data={"username": username, "password": password, "csrf_token": csrf_token},
        follow_redirects=False,
    )
    assert response.status_code == 303
    return csrf_token


def test_admin_post_requires_valid_csrf(tmp_path: Path, monkeypatch) -> None:
    database_url = _setup_db(tmp_path)
    _prepare_env(monkeypatch, database_url)
    _seed_admin()

    with TestClient(_fresh_app()) as client:
        _login(client)

        invalid_csrf = client.post(
            "/admin/services/create",
            data={"name": "Loan", "is_active": "on", "csrf_token": "invalid-token"},
            follow_redirects=False,
        )
        assert invalid_csrf.status_code == 403

        services_page = client.get("/admin/services")
        valid_csrf_token = _extract_csrf_token(services_page.text)

        valid_csrf = client.post(
            "/admin/services/create",
            data={"name": "Loan", "is_active": "on", "csrf_token": valid_csrf_token},
            follow_redirects=False,
        )
        assert valid_csrf.status_code == 303

    session_factory = get_session_factory()
    with session_factory() as db:
        service = db.scalar(select(Service).where(Service.name == "Loan"))
        assert service is not None


def test_inactive_admin_cannot_login(tmp_path: Path, monkeypatch) -> None:
    database_url = _setup_db(tmp_path)
    _prepare_env(monkeypatch, database_url)
    _seed_admin(is_active=False)

    with TestClient(_fresh_app()) as client:
        login_page = client.get("/admin/login")
        csrf_token = _extract_csrf_token(login_page.text)

        response = client.post(
            "/admin/login",
            data={"username": "admin", "password": "secret", "csrf_token": csrf_token},
            follow_redirects=False,
        )
        assert response.status_code == 400
        assert "Invalid username or password" in response.text


def test_session_cookie_flags_are_applied(tmp_path: Path, monkeypatch) -> None:
    database_url = _setup_db(tmp_path)
    _prepare_env(monkeypatch, database_url, secure=True, samesite="strict")

    with TestClient(_fresh_app()) as client:
        response = client.get("/admin/login")
        set_cookie = response.headers.get("set-cookie", "").lower()

    assert "httponly" in set_cookie
    assert "secure" in set_cookie
    assert "samesite=strict" in set_cookie
