from pathlib import Path

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.auth import hash_password
from app.database import configure_database, drop_db, get_session_factory, init_db
from app.models import Admin, FieldType, Request, RequestAnswer, RequestState, Service, ServiceField, ServiceStatus


def _setup_db(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    configure_database(f"sqlite:///{db_path}")
    drop_db()
    init_db()


def test_core_models_can_be_persisted(tmp_path: Path) -> None:
    _setup_db(tmp_path)

    session_factory = get_session_factory()
    with session_factory() as db:
        admin = Admin(username="admin", password_hash=hash_password("secret"))
        service = Service(name="Loan")
        db.add_all([admin, service])
        db.flush()

        field = ServiceField(
            service_id=service.id,
            label="National ID",
            field_type=FieldType.TEXT,
            is_required=True,
            display_order=1,
        )
        status = ServiceStatus(service_id=service.id, name="Received", display_order=1)
        db.add_all([field, status])
        db.flush()

        request = Request(
            tracking_code="TRK-1001",
            chat_id="123456",
            service_id=service.id,
            state=RequestState.SUBMITTED,
            current_status_id=status.id,
        )
        db.add(request)
        db.flush()

        answer = RequestAnswer(
            request_id=request.id,
            service_field_id=field.id,
            field_label_snapshot=field.label,
            field_type_snapshot=field.field_type,
            value_text="0012345678",
        )
        db.add(answer)
        db.commit()

    with session_factory() as db:
        persisted_request = db.scalar(select(Request).where(Request.tracking_code == "TRK-1001"))
        assert persisted_request is not None
        assert persisted_request.chat_id == "123456"
        assert persisted_request.current_status is not None
        assert persisted_request.current_status.name == "Received"


def test_only_one_unfinished_request_per_chat_id(tmp_path: Path) -> None:
    _setup_db(tmp_path)

    session_factory = get_session_factory()
    with session_factory() as db:
        service = Service(name="Financial Assistance")
        db.add(service)
        db.flush()
        service_id = service.id

        first_request = Request(
            chat_id="999999",
            service_id=service_id,
            state=RequestState.UNFINISHED,
        )
        db.add(first_request)
        db.commit()

    with session_factory() as db:
        second_request = Request(
            chat_id="999999",
            service_id=service_id,
            state=RequestState.UNFINISHED,
        )
        db.add(second_request)

        try:
            db.commit()
            assert False, "Expected IntegrityError for duplicate unfinished request"
        except IntegrityError:
            db.rollback()
