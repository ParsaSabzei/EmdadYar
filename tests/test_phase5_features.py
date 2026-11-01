import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.auth import hash_password
from app.config import clear_settings_cache
from app.database import configure_database, drop_db, get_session_factory, init_db
from app.main import app
from app.models import Admin, FieldType, Request, RequestAnswer
from app.services.core import (
    add_service_field,
    add_service_status,
    create_service,
    save_request_answer,
    start_unfinished_request,
    submit_request,
)
from app.services.file_storage import FileStorageError, resolve_stored_file_path, store_request_file


def _setup_db(tmp_path: Path) -> str:
    db_path = tmp_path / "phase5.db"
    database_url = f"sqlite:///{db_path}"
    configure_database(database_url)
    drop_db()
    init_db()
    return database_url


def _prepare_env(monkeypatch, tmp_path: Path, database_url: str) -> Path:
    uploads_dir = tmp_path / "uploads"
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setenv("SECRET_KEY", "test-secret")
    monkeypatch.setenv("BALE_BOT_TOKEN", "test-token")
    monkeypatch.setenv("UPLOADS_DIR", str(uploads_dir))
    clear_settings_cache()
    return uploads_dir


def _seed_admin() -> None:
    session_factory = get_session_factory()
    with session_factory() as db:
        db.add(Admin(username="admin", password_hash=hash_password("secret"), is_active=True))
        db.commit()


def _extract_csrf_token(html: str) -> str:
    match = re.search(r'name="csrf_token"\s+value="([^"]+)"', html)
    assert match is not None
    return match.group(1)


def _login(client: TestClient) -> None:
    login_page = client.get("/admin/login")
    assert login_page.status_code == 200
    csrf_token = _extract_csrf_token(login_page.text)

    resp = client.post(
        "/admin/login",
        data={"username": "admin", "password": "secret", "csrf_token": csrf_token},
        follow_redirects=False,
    )
    assert resp.status_code == 303


def _create_submitted_request(db, *, service_id: int, name_field_id: int, nid_field_id: int, chat_id: str, name: str, nid: int):
    req = start_unfinished_request(db, chat_id=chat_id, service_id=service_id)
    save_request_answer(db, request_id=req.id, chat_id=chat_id, service_field_id=name_field_id, text_value=name)
    save_request_answer(db, request_id=req.id, chat_id=chat_id, service_field_id=nid_field_id, number_value=nid)
    return submit_request(db, request_id=req.id, chat_id=chat_id)


def test_admin_search_by_tracking_name_national_and_filters(tmp_path: Path, monkeypatch) -> None:
    database_url = _setup_db(tmp_path)
    _prepare_env(monkeypatch, tmp_path, database_url)
    _seed_admin()

    session_factory = get_session_factory()
    with session_factory() as db:
        service_loan = create_service(db, "Loan")
        service_medical = create_service(db, "Medical")

        name_field_loan = add_service_field(db, service_loan.id, label="Name", field_type=FieldType.TEXT, is_required=True)
        nid_field_loan = add_service_field(db, service_loan.id, label="National ID", field_type=FieldType.NUMBER, is_required=True)
        status_received_loan = add_service_status(db, service_loan.id, name="Received")

        name_field_med = add_service_field(db, service_medical.id, label="Name", field_type=FieldType.TEXT, is_required=True)
        nid_field_med = add_service_field(db, service_medical.id, label="National ID", field_type=FieldType.NUMBER, is_required=True)
        add_service_status(db, service_medical.id, name="Received")

        req1 = _create_submitted_request(
            db,
            service_id=service_loan.id,
            name_field_id=name_field_loan.id,
            nid_field_id=nid_field_loan.id,
            chat_id="101",
            name="Ali Reza",
            nid=1111111111,
        )
        _create_submitted_request(
            db,
            service_id=service_loan.id,
            name_field_id=name_field_loan.id,
            nid_field_id=nid_field_loan.id,
            chat_id="102",
            name="Sara",
            nid=2222222222,
        )
        _create_submitted_request(
            db,
            service_id=service_medical.id,
            name_field_id=name_field_med.id,
            nid_field_id=nid_field_med.id,
            chat_id="103",
            name="Mehdi",
            nid=3333333333,
        )

    with TestClient(app) as client:
        _login(client)

        by_tracking = client.get(f"/admin/requests?search_tracking_code={req1.tracking_code}")
        assert by_tracking.status_code == 200
        assert "Ali Reza" in by_tracking.text
        assert "Sara" not in by_tracking.text

        by_name = client.get("/admin/requests?search_name=ali")
        assert by_name.status_code == 200
        assert "Ali Reza" in by_name.text
        assert "Sara" not in by_name.text

        by_nid = client.get("/admin/requests?search_national_id=222222")
        assert by_nid.status_code == 200
        assert "Sara" in by_nid.text
        assert "Ali Reza" not in by_nid.text

        with_filters = client.get(
            f"/admin/requests?service_id={service_loan.id}&status_id={status_received_loan.id}&search_name=sara"
        )
        assert with_filters.status_code == 200
        assert "Sara" in with_filters.text
        assert "Mehdi" not in with_filters.text


def test_admin_delete_request_removes_db_answers_and_files_without_affecting_other_requests(tmp_path: Path, monkeypatch) -> None:
    database_url = _setup_db(tmp_path)
    uploads_dir = _prepare_env(monkeypatch, tmp_path, database_url)
    _seed_admin()

    session_factory = get_session_factory()
    with session_factory() as db:
        service = create_service(db, "Loans")
        file_field = add_service_field(db, service.id, label="Doc", field_type=FieldType.FILE, is_required=True)
        add_service_status(db, service.id, name="Received")

        req1 = start_unfinished_request(db, chat_id="201", service_id=service.id)
        stored1 = store_request_file(
            request_id=req1.id,
            content=b"%PDF-1.7 test",
            filename="a.pdf",
            mime_type="application/pdf",
            declared_size=12,
        )
        save_request_answer(
            db,
            request_id=req1.id,
            chat_id="201",
            service_field_id=file_field.id,
            file_path=stored1.stored_path,
            original_filename=stored1.original_filename,
        )
        req1 = submit_request(db, request_id=req1.id, chat_id="201")

        req2 = start_unfinished_request(db, chat_id="202", service_id=service.id)
        stored2 = store_request_file(
            request_id=req2.id,
            content=b"%PDF-1.7 test2",
            filename="b.pdf",
            mime_type="application/pdf",
            declared_size=13,
        )
        save_request_answer(
            db,
            request_id=req2.id,
            chat_id="202",
            service_field_id=file_field.id,
            file_path=stored2.stored_path,
            original_filename=stored2.original_filename,
        )
        req2 = submit_request(db, request_id=req2.id, chat_id="202")

    resolved1 = resolve_stored_file_path(stored1.stored_path)
    resolved2 = resolve_stored_file_path(stored2.stored_path)
    assert resolved1 is not None and resolved1.exists()
    assert resolved2 is not None and resolved2.exists()

    with TestClient(app) as client:
        _login(client)
        csrf_token = _extract_csrf_token(client.get(f"/admin/requests/{req1.id}").text)

        resp = client.post(
            f"/admin/requests/{req1.id}/delete",
            data={"csrf_token": csrf_token},
            follow_redirects=False,
        )
        assert resp.status_code == 303

    with session_factory() as db:
        deleted_request = db.get(Request, req1.id)
        assert deleted_request is None
        deleted_answers_count = db.scalar(select(func.count(RequestAnswer.id)).where(RequestAnswer.request_id == req1.id))
        assert deleted_answers_count == 0

        remaining_request = db.get(Request, req2.id)
        assert remaining_request is not None

    assert resolved1 is not None and not resolved1.exists()
    assert resolved2 is not None and resolved2.exists()
    assert uploads_dir.exists()


def test_file_storage_validation_and_safety(tmp_path: Path, monkeypatch) -> None:
    database_url = _setup_db(tmp_path)
    uploads_dir = _prepare_env(monkeypatch, tmp_path, database_url)

    stored_pdf = store_request_file(
        request_id=1,
        content=b"%PDF-1.4 valid",
        filename="safe.pdf",
        mime_type="application/pdf",
        declared_size=14,
    )
    assert stored_pdf.original_filename == "safe.pdf"
    assert "/requests/1/" in stored_pdf.stored_path

    stored_jpg = store_request_file(
        request_id=1,
        content=b"\xff\xd8\xff\xe0\x00\x10JFIF",
        filename="photo.jpg",
        mime_type="image/jpeg",
        declared_size=11,
    )
    assert stored_jpg.extension == "jpg"

    stored_jpeg = store_request_file(
        request_id=1,
        content=b"\xff\xd8\xff\xe0\x00\x10JFIF",
        filename="photo.jpeg",
        mime_type="image/jpeg",
        declared_size=11,
    )
    assert stored_jpeg.extension in {"jpg", "jpeg"}

    stored_png = store_request_file(
        request_id=1,
        content=b"\x89PNG\r\n\x1a\ncontent",
        filename="image.png",
        mime_type="image/png",
        declared_size=15,
    )
    assert stored_png.extension == "png"

    with pytest.raises(FileStorageError):
        store_request_file(
            request_id=1,
            content=b"not-a-supported-file",
            filename="evil.exe",
            mime_type="application/octet-stream",
            declared_size=20,
        )

    with pytest.raises(FileStorageError):
        store_request_file(
            request_id=1,
            content=b"%PDF-1.7" + (b"a" * (10 * 1024 * 1024)),
            filename="big.pdf",
            mime_type="application/pdf",
            declared_size=10 * 1024 * 1024 + 1,
        )

    unsafe = store_request_file(
        request_id=2,
        content=b"%PDF-1.7 test",
        filename="../../secret.pdf",
        mime_type="application/pdf",
        declared_size=12,
    )
    assert unsafe.original_filename == "secret.pdf"
    resolved = resolve_stored_file_path(unsafe.stored_path)
    assert resolved is not None
    assert uploads_dir.resolve() in resolved.parents


def test_protected_file_access(tmp_path: Path, monkeypatch) -> None:
    database_url = _setup_db(tmp_path)
    _prepare_env(monkeypatch, tmp_path, database_url)
    _seed_admin()

    session_factory = get_session_factory()
    with session_factory() as db:
        service = create_service(db, "Service")
        file_field = add_service_field(db, service.id, label="Doc", field_type=FieldType.FILE, is_required=True)
        add_service_status(db, service.id, name="Received")

        req1 = start_unfinished_request(db, chat_id="301", service_id=service.id)
        file1 = store_request_file(
            request_id=req1.id,
            content=b"%PDF-1.7 test",
            filename="doc1.pdf",
            mime_type="application/pdf",
            declared_size=12,
        )
        ans1 = save_request_answer(
            db,
            request_id=req1.id,
            chat_id="301",
            service_field_id=file_field.id,
            file_path=file1.stored_path,
            original_filename=file1.original_filename,
        )
        req1 = submit_request(db, request_id=req1.id, chat_id="301")

        req2 = start_unfinished_request(db, chat_id="302", service_id=service.id)
        file2 = store_request_file(
            request_id=req2.id,
            content=b"%PDF-1.7 test2",
            filename="doc2.pdf",
            mime_type="application/pdf",
            declared_size=13,
        )
        ans2 = save_request_answer(
            db,
            request_id=req2.id,
            chat_id="302",
            service_field_id=file_field.id,
            file_path=file2.stored_path,
            original_filename=file2.original_filename,
        )
        req2 = submit_request(db, request_id=req2.id, chat_id="302")

    with TestClient(app) as client:
        no_auth = client.get(f"/admin/requests/{req1.id}/files/{ans1.id}", follow_redirects=False)
        assert no_auth.status_code == 303

        _login(client)

        ok = client.get(f"/admin/requests/{req1.id}/files/{ans1.id}")
        assert ok.status_code == 200
        assert ok.content.startswith(b"%PDF-")

        mismatch = client.get(f"/admin/requests/{req1.id}/files/{ans2.id}")
        assert mismatch.status_code == 404

        missing = client.get(f"/admin/requests/{req2.id}/files/999999")
        assert missing.status_code == 404


def test_admin_messaging_uses_correct_chat_id_and_text_and_handles_errors(tmp_path: Path, monkeypatch) -> None:
    database_url = _setup_db(tmp_path)
    _prepare_env(monkeypatch, tmp_path, database_url)
    _seed_admin()

    session_factory = get_session_factory()
    with session_factory() as db:
        service = create_service(db, "Message")
        field = add_service_field(db, service.id, label="Name", field_type=FieldType.TEXT, is_required=True)
        add_service_status(db, service.id, name="Received")

        req = start_unfinished_request(db, chat_id="777777", service_id=service.id)
        save_request_answer(db, request_id=req.id, chat_id="777777", service_field_id=field.id, text_value="User")
        req = submit_request(db, request_id=req.id, chat_id="777777")
        request_id = req.id

    captured: dict[str, str] = {}

    def fake_send(chat_id: str, text: str) -> None:
        captured["chat_id"] = chat_id
        captured["text"] = text

    monkeypatch.setattr("app.routes.admin.send_text_message", fake_send)

    with TestClient(app) as client:
        _login(client)
        csrf_token = _extract_csrf_token(client.get(f"/admin/requests/{request_id}").text)

        resp = client.post(
            f"/admin/requests/{request_id}/message",
            data={"message_text": "مدارک شما ناقص است. لطفاً درخواست جدیدی ثبت کنید.", "csrf_token": csrf_token},
            follow_redirects=False,
        )
        assert resp.status_code == 303
        assert captured["chat_id"] == "777777"
        assert "مدارک" in captured["text"]

    def fake_send_error(chat_id: str, text: str) -> None:
        raise RuntimeError("bale error")

    monkeypatch.setattr("app.routes.admin.send_text_message", fake_send_error)

    with TestClient(app) as client:
        _login(client)
        csrf_token = _extract_csrf_token(client.get(f"/admin/requests/{request_id}").text)
        resp = client.post(
            f"/admin/requests/{request_id}/message",
            data={"message_text": "hello", "csrf_token": csrf_token},
            follow_redirects=False,
        )
        assert resp.status_code == 303
        assert "error=" in resp.headers.get("location", "")
