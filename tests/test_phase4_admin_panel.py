from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.auth import hash_password
from app.config import clear_settings_cache
from app.database import configure_database, drop_db, get_session_factory, init_db
from app.main import app
from app.models import Admin, FieldType, Request, Service
from app.services.core import (
    add_service_field,
    add_service_status,
    create_service,
    save_request_answer,
    start_unfinished_request,
    submit_request,
)


def _setup_db(tmp_path: Path) -> str:
    db_path = tmp_path / "phase4.db"
    database_url = f"sqlite:///{db_path}"
    configure_database(database_url)
    drop_db()
    init_db()
    return database_url


def _login(client: TestClient, username: str = "admin", password: str = "secret") -> None:
    resp = client.post(
        "/admin/login",
        data={"username": username, "password": password},
        follow_redirects=False,
    )
    assert resp.status_code == 303


def _seed_admin() -> None:
    session_factory = get_session_factory()
    with session_factory() as db:
        db.add(Admin(username="admin", password_hash=hash_password("secret"), is_active=True))
        db.commit()


def _prepare_env(monkeypatch, database_url: str) -> None:
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setenv("SECRET_KEY", "test-secret")
    monkeypatch.setenv("BALE_BOT_TOKEN", "test-token")
    clear_settings_cache()


def test_admin_login_and_protection(tmp_path: Path, monkeypatch) -> None:
    database_url = _setup_db(tmp_path)
    _prepare_env(monkeypatch, database_url)
    _seed_admin()

    with TestClient(app) as client:
        protected = client.get("/admin", follow_redirects=False)
        assert protected.status_code == 303
        assert protected.headers["location"] == "/admin/login"

        login_page = client.get("/admin/login")
        assert login_page.status_code == 200

        _login(client)
        dashboard = client.get("/admin")
        assert dashboard.status_code == 200


def test_service_crud(tmp_path: Path, monkeypatch) -> None:
    database_url = _setup_db(tmp_path)
    _prepare_env(monkeypatch, database_url)
    _seed_admin()

    with TestClient(app) as client:
        _login(client)

        create_resp = client.post(
            "/admin/services/create",
            data={"name": "Loan", "is_active": "on"},
            follow_redirects=False,
        )
        assert create_resp.status_code == 303

        session_factory = get_session_factory()
        with session_factory() as db:
            service = db.scalar(select(Service).where(Service.name == "Loan"))
            assert service is not None
            service_id = service.id

        edit_resp = client.post(
            f"/admin/services/{service_id}/edit",
            data={"name": "Loan Updated", "is_active": "on"},
            follow_redirects=False,
        )
        assert edit_resp.status_code == 303

        with session_factory() as db:
            service = db.get(Service, service_id)
            assert service is not None
            assert service.name == "Loan Updated"

        delete_resp = client.post(f"/admin/services/{service_id}/delete", follow_redirects=False)
        assert delete_resp.status_code == 303


def test_field_crud(tmp_path: Path, monkeypatch) -> None:
    database_url = _setup_db(tmp_path)
    _prepare_env(monkeypatch, database_url)
    _seed_admin()

    session_factory = get_session_factory()
    with session_factory() as db:
        service = create_service(db, "Aid")
        service_id = service.id

    with TestClient(app) as client:
        _login(client)

        create = client.post(
            f"/admin/services/{service_id}/fields/create",
            data={"label": "Name", "field_type": "TEXT", "is_required": "on"},
            follow_redirects=False,
        )
        assert create.status_code == 303

        with session_factory() as db:
            from app.models import ServiceField

            field = db.scalar(select(ServiceField).where(ServiceField.service_id == service_id))
            assert field is not None
            field_id = field.id

        edit = client.post(
            f"/admin/services/{service_id}/fields/{field_id}/edit",
            data={"label": "Full Name", "field_type": "TEXT", "is_required": "on"},
            follow_redirects=False,
        )
        assert edit.status_code == 303

        reorder = client.post(
            f"/admin/services/{service_id}/fields/reorder",
            data={"ordered_field_ids": str(field_id)},
            follow_redirects=False,
        )
        assert reorder.status_code == 303

        delete = client.post(f"/admin/services/{service_id}/fields/{field_id}/delete", follow_redirects=False)
        assert delete.status_code == 303


def test_status_crud(tmp_path: Path, monkeypatch) -> None:
    database_url = _setup_db(tmp_path)
    _prepare_env(monkeypatch, database_url)
    _seed_admin()

    session_factory = get_session_factory()
    with session_factory() as db:
        service = create_service(db, "Medical")
        service_id = service.id

    with TestClient(app) as client:
        _login(client)

        create = client.post(
            f"/admin/services/{service_id}/statuses/create",
            data={"name": "Received"},
            follow_redirects=False,
        )
        assert create.status_code == 303

        with session_factory() as db:
            from app.models import ServiceStatus

            status = db.scalar(select(ServiceStatus).where(ServiceStatus.service_id == service_id))
            assert status is not None
            status_id = status.id

        edit = client.post(
            f"/admin/services/{service_id}/statuses/{status_id}/edit",
            data={"name": "Under review"},
            follow_redirects=False,
        )
        assert edit.status_code == 303

        reorder = client.post(
            f"/admin/services/{service_id}/statuses/reorder",
            data={"ordered_status_ids": str(status_id)},
            follow_redirects=False,
        )
        assert reorder.status_code == 303

        delete = client.post(f"/admin/services/{service_id}/statuses/{status_id}/delete", follow_redirects=False)
        assert delete.status_code == 303


def test_request_list_and_status_update(tmp_path: Path, monkeypatch) -> None:
    database_url = _setup_db(tmp_path)
    _prepare_env(monkeypatch, database_url)
    _seed_admin()

    session_factory = get_session_factory()
    with session_factory() as db:
        service = create_service(db, "Loans")
        field = add_service_field(db, service.id, label="Name", field_type=FieldType.TEXT, is_required=True)
        status1 = add_service_status(db, service.id, name="Received")
        status2 = add_service_status(db, service.id, name="Approved")

        req = start_unfinished_request(db, chat_id="12345", service_id=service.id)
        save_request_answer(db, request_id=req.id, chat_id="12345", service_field_id=field.id, text_value="Ali")
        submitted = submit_request(db, request_id=req.id, chat_id="12345")
        request_id = submitted.id

    monkeypatch.setattr("app.routes.admin.send_text_message", lambda chat_id, text: None)

    with TestClient(app) as client:
        _login(client)

        listing = client.get("/admin/requests")
        assert listing.status_code == 200
        assert "Loans" in listing.text

        filtered = client.get(f"/admin/requests?service_id={service.id}&status_id={status1.id}")
        assert filtered.status_code == 200

        details = client.get(f"/admin/requests/{request_id}")
        assert details.status_code == 200
        assert "Ali" in details.text

        update_status = client.post(
            f"/admin/requests/{request_id}/status",
            data={"status_id": str(status2.id)},
            follow_redirects=False,
        )
        assert update_status.status_code == 303

        send_message = client.post(
            f"/admin/requests/{request_id}/message",
            data={"message_text": "hello"},
            follow_redirects=False,
        )
        assert send_message.status_code == 303

        with session_factory() as db:
            refreshed = db.get(Request, request_id)
            assert refreshed is not None
            assert refreshed.current_status_id == status2.id
