from pathlib import Path

import pytest

from app.database import configure_database, drop_db, get_session_factory, init_db
from app.models import FieldType, RequestState
from app.services import (
    BusinessRuleError,
    ValidationError,
    add_service_field,
    add_service_status,
    cancel_unfinished_request,
    create_service,
    get_beneficiary_requests,
    get_request_details,
    get_service_fields_ordered,
    reorder_service_fields,
    reorder_service_statuses,
    save_request_answer,
    start_unfinished_request,
    submit_request,
)


def _setup_db(tmp_path: Path) -> None:
    db_path = tmp_path / "phase2.db"
    configure_database(f"sqlite:///{db_path}")
    drop_db()
    init_db()


@pytest.fixture
def db(tmp_path: Path):
    _setup_db(tmp_path)
    session_factory = get_session_factory()
    with session_factory() as session:
        yield session


def test_create_service(db) -> None:
    service = create_service(db, "Loan")
    assert service.id is not None
    assert service.name == "Loan"
    assert service.is_active is True


def test_add_fields_and_reorder(db) -> None:
    service = create_service(db, "Aid")

    f1 = add_service_field(db, service.id, label="Full name", field_type=FieldType.TEXT, is_required=True)
    f2 = add_service_field(db, service.id, label="National ID", field_type=FieldType.NUMBER, is_required=True)
    f3 = add_service_field(db, service.id, label="Document", field_type=FieldType.FILE, is_required=False)

    ordered = get_service_fields_ordered(db, service.id)
    assert [f.id for f in ordered] == [f1.id, f2.id, f3.id]

    reordered = reorder_service_fields(db, service.id, [f3.id, f1.id, f2.id])
    assert [f.id for f in reordered] == [f3.id, f1.id, f2.id]


def test_add_statuses_and_reorder(db) -> None:
    service = create_service(db, "Registration")

    s1 = add_service_status(db, service.id, name="Received")
    s2 = add_service_status(db, service.id, name="Under review")

    reordered = reorder_service_statuses(db, service.id, [s2.id, s1.id])
    assert [s.id for s in reordered] == [s2.id, s1.id]


def test_start_unfinished_request_and_prevent_duplicate(db) -> None:
    service = create_service(db, "Scholarship")

    req1 = start_unfinished_request(db, chat_id="1001", service_id=service.id)
    req2 = start_unfinished_request(db, chat_id="1001", service_id=service.id)

    assert req1.id == req2.id
    assert req1.state == RequestState.UNFINISHED


def test_add_answers_text_number_file(db) -> None:
    service = create_service(db, "Loan")
    text_field = add_service_field(db, service.id, label="Full name", field_type=FieldType.TEXT)
    number_field = add_service_field(db, service.id, label="Income", field_type=FieldType.NUMBER)
    file_field = add_service_field(db, service.id, label="ID file", field_type=FieldType.FILE, is_required=False)

    request = start_unfinished_request(db, chat_id="2002", service_id=service.id)

    text_answer = save_request_answer(
        db,
        request_id=request.id,
        chat_id="2002",
        service_field_id=text_field.id,
        text_value="Parsa",
    )
    num_answer = save_request_answer(
        db,
        request_id=request.id,
        chat_id="2002",
        service_field_id=number_field.id,
        number_value="1200.5",
    )
    file_answer = save_request_answer(
        db,
        request_id=request.id,
        chat_id="2002",
        service_field_id=file_field.id,
        file_path="uploads/a.pdf",
        original_filename="id.pdf",
    )

    assert text_answer.value_text == "Parsa"
    assert num_answer.value_number == 1200.5
    assert file_answer.file_path == "uploads/a.pdf"


def test_submit_request_success_sets_status_and_tracking_code(db) -> None:
    service = create_service(db, "Financial Assistance")
    text_field = add_service_field(db, service.id, label="Full name", field_type=FieldType.TEXT, is_required=True)
    number_field = add_service_field(db, service.id, label="National ID", field_type=FieldType.NUMBER, is_required=True)
    first_status = add_service_status(db, service.id, name="Received")
    add_service_status(db, service.id, name="Under review")

    request = start_unfinished_request(db, chat_id="3003", service_id=service.id)
    save_request_answer(db, request_id=request.id, chat_id="3003", service_field_id=text_field.id, text_value="User")
    save_request_answer(db, request_id=request.id, chat_id="3003", service_field_id=number_field.id, number_value=123456)

    submitted = submit_request(db, request_id=request.id, chat_id="3003")

    assert submitted.state == RequestState.SUBMITTED
    assert submitted.current_status_id == first_status.id
    assert submitted.tracking_code is not None
    assert submitted.tracking_code.startswith("EMD-")
    assert len(submitted.tracking_code) == 10


def test_submit_fails_when_required_field_missing(db) -> None:
    service = create_service(db, "Support")
    add_service_field(db, service.id, label="Full name", field_type=FieldType.TEXT, is_required=True)

    request = start_unfinished_request(db, chat_id="4004", service_id=service.id)

    with pytest.raises(ValidationError):
        submit_request(db, request_id=request.id, chat_id="4004")


def test_cancel_unfinished_request(db) -> None:
    service = create_service(db, "Program")
    request = start_unfinished_request(db, chat_id="5005", service_id=service.id)

    cancelled = cancel_unfinished_request(db, request_id=request.id, chat_id="5005")
    assert cancelled.state == RequestState.CANCELLED


def test_cancelled_request_allows_new_unfinished_request(db) -> None:
    service = create_service(db, "Program-2")
    request = start_unfinished_request(db, chat_id="6006", service_id=service.id)
    cancel_unfinished_request(db, request_id=request.id, chat_id="6006")

    new_request = start_unfinished_request(db, chat_id="6006", service_id=service.id)
    assert new_request.id != request.id
    assert new_request.state == RequestState.UNFINISHED


def test_tracking_codes_are_unique(db) -> None:
    service = create_service(db, "Unique test")
    field = add_service_field(db, service.id, label="Name", field_type=FieldType.TEXT, is_required=True)

    request1 = start_unfinished_request(db, chat_id="7001", service_id=service.id)
    save_request_answer(db, request_id=request1.id, chat_id="7001", service_field_id=field.id, text_value="A")
    request1 = submit_request(db, request_id=request1.id, chat_id="7001")

    request2 = start_unfinished_request(db, chat_id="7002", service_id=service.id)
    save_request_answer(db, request_id=request2.id, chat_id="7002", service_field_id=field.id, text_value="B")
    request2 = submit_request(db, request_id=request2.id, chat_id="7002")

    assert request1.tracking_code != request2.tracking_code


def test_beneficiary_queries(db) -> None:
    service = create_service(db, "History")
    field = add_service_field(db, service.id, label="Name", field_type=FieldType.TEXT, is_required=True)
    add_service_status(db, service.id, name="Received")

    request = start_unfinished_request(db, chat_id="8008", service_id=service.id)
    save_request_answer(db, request_id=request.id, chat_id="8008", service_field_id=field.id, text_value="Name")
    submitted = submit_request(db, request_id=request.id, chat_id="8008")

    beneficiary_requests = get_beneficiary_requests(db, chat_id="8008")
    assert len(beneficiary_requests) == 1
    assert beneficiary_requests[0].service.name == "History"

    details = get_request_details(db, request_id=submitted.id)
    assert details.id == submitted.id
    assert details.current_status is not None
    assert len(details.answers) == 1


def test_cannot_cancel_submitted_request(db) -> None:
    service = create_service(db, "Cancel check")
    field = add_service_field(db, service.id, label="Name", field_type=FieldType.TEXT, is_required=True)
    add_service_status(db, service.id, name="Received")

    request = start_unfinished_request(db, chat_id="9009", service_id=service.id)
    save_request_answer(db, request_id=request.id, chat_id="9009", service_field_id=field.id, text_value="User")
    submitted = submit_request(db, request_id=request.id, chat_id="9009")

    with pytest.raises(BusinessRuleError):
        cancel_unfinished_request(db, request_id=submitted.id, chat_id="9009")
