import asyncio
from pathlib import Path

from sqlalchemy import select

from app.bale import keyboards, states
from app.bale.handlers import process_message
from app.database import configure_database, drop_db, get_session_factory, init_db
from app.models import ConversationState, FieldType, Request, RequestAnswer, RequestState
from app.services.core import add_service_field, add_service_status, create_service


class FakeChat:
    def __init__(self, chat_id: str) -> None:
        self.id = chat_id


class FakeDocument:
    def __init__(self, file_id: str, file_name: str) -> None:
        self.file_id = file_id
        self.file_name = file_name


class FakeMessage:
    def __init__(self, chat_id: str, text: str | None = None, document: FakeDocument | None = None) -> None:
        self.chat = FakeChat(chat_id)
        self.text = text
        self.document = document
        self.replies: list[tuple[str, tuple]] = []

    async def reply(self, text: str, *args) -> None:
        self.replies.append((text, args))


def _setup_db(tmp_path: Path) -> None:
    db_path = tmp_path / "phase3.db"
    configure_database(f"sqlite:///{db_path}")
    drop_db()
    init_db()


def _run(coro) -> None:
    asyncio.run(coro)


def test_service_menu_generation(tmp_path: Path) -> None:
    _setup_db(tmp_path)
    session_factory = get_session_factory()
    with session_factory() as db:
        s1 = create_service(db, "Loan")
        s2 = create_service(db, "Medical Assistance")

        rows = keyboards.services_rows([s1, s2])
        assert rows[0][0].startswith("Service ")
        assert "Loan" in rows[0][0]
        assert "Medical Assistance" in rows[1][0]


def test_service_selection_starts_request_and_sets_first_field(tmp_path: Path) -> None:
    _setup_db(tmp_path)
    session_factory = get_session_factory()
    with session_factory() as db:
        service = create_service(db, "Loan")
        field1 = add_service_field(db, service.id, label="Full name", field_type=FieldType.TEXT)
        add_service_field(db, service.id, label="National ID", field_type=FieldType.NUMBER)

        msg = FakeMessage(chat_id="111", text=f"Service {service.id} - {service.name}")
        _run(process_message(db, msg))

        state = db.scalar(select(ConversationState).where(ConversationState.chat_id == "111"))
        assert state is not None
        assert state.request_id is not None
        assert state.current_field_id == field1.id
        assert "Full name" in msg.replies[-1][0]


def test_unfinished_request_detection(tmp_path: Path) -> None:
    _setup_db(tmp_path)
    session_factory = get_session_factory()
    with session_factory() as db:
        service1 = create_service(db, "Loan")
        service2 = create_service(db, "Education")
        add_service_field(db, service1.id, label="Name", field_type=FieldType.TEXT)

        _run(process_message(db, FakeMessage(chat_id="222", text=f"Service {service1.id} - {service1.name}")))
        msg2 = FakeMessage(chat_id="222", text=f"Service {service2.id} - {service2.name}")
        _run(process_message(db, msg2))

        assert "already have an unfinished request" in msg2.replies[-1][0]


def test_field_progression_and_answer_saving_and_submission(tmp_path: Path) -> None:
    _setup_db(tmp_path)
    session_factory = get_session_factory()
    with session_factory() as db:
        service = create_service(db, "Aid")
        name_field = add_service_field(db, service.id, label="Name", field_type=FieldType.TEXT)
        number_field = add_service_field(db, service.id, label="Income", field_type=FieldType.NUMBER)
        file_field = add_service_field(db, service.id, label="Document", field_type=FieldType.FILE)
        status = add_service_status(db, service.id, name="Received")

        _run(process_message(db, FakeMessage(chat_id="333", text=f"Service {service.id} - {service.name}")))

        name_msg = FakeMessage(chat_id="333", text="Parsa")
        _run(process_message(db, name_msg))
        assert "Income" in name_msg.replies[-1][0]

        number_msg = FakeMessage(chat_id="333", text="2500")
        _run(process_message(db, number_msg))
        assert "Document" in number_msg.replies[-1][0]

        file_msg = FakeMessage(chat_id="333", document=FakeDocument(file_id="f1", file_name="doc.pdf"))
        _run(process_message(db, file_msg))
        assert "Request submitted successfully" in file_msg.replies[-1][0]

        request = db.scalar(select(Request).where(Request.chat_id == "333"))
        assert request is not None
        assert request.state == RequestState.SUBMITTED
        assert request.current_status_id == status.id
        assert request.tracking_code is not None

        answers = list(db.scalars(select(RequestAnswer).where(RequestAnswer.request_id == request.id)))
        assert len(answers) == 3
        assert any(a.service_field_id == name_field.id and a.value_text == "Parsa" for a in answers)
        assert any(a.service_field_id == number_field.id and a.value_number == 2500 for a in answers)
        assert any(a.service_field_id == file_field.id and a.file_path == "bale-file://f1" for a in answers)


def test_number_validation_error(tmp_path: Path) -> None:
    _setup_db(tmp_path)
    session_factory = get_session_factory()
    with session_factory() as db:
        service = create_service(db, "Validation")
        add_service_field(db, service.id, label="National ID", field_type=FieldType.NUMBER)

        _run(process_message(db, FakeMessage(chat_id="444", text=f"Service {service.id} - {service.name}")))
        msg = FakeMessage(chat_id="444", text="abc")
        _run(process_message(db, msg))

        assert "must be numeric" in msg.replies[-1][0]


def test_cancellation_flow(tmp_path: Path) -> None:
    _setup_db(tmp_path)
    session_factory = get_session_factory()
    with session_factory() as db:
        service = create_service(db, "Cancel")
        add_service_field(db, service.id, label="Name", field_type=FieldType.TEXT)

        _run(process_message(db, FakeMessage(chat_id="555", text=f"Service {service.id} - {service.name}")))
        cancel_msg = FakeMessage(chat_id="555", text=states.MAIN_CANCEL_CURRENT)
        _run(process_message(db, cancel_msg))

        request = db.scalar(select(Request).where(Request.chat_id == "555"))
        assert request is not None
        assert request.state == RequestState.CANCELLED
        assert "cancelled" in cancel_msg.replies[-1][0].lower()


def test_my_requests_and_request_details(tmp_path: Path) -> None:
    _setup_db(tmp_path)
    session_factory = get_session_factory()
    with session_factory() as db:
        service = create_service(db, "History")
        add_service_field(db, service.id, label="Name", field_type=FieldType.TEXT)
        add_service_status(db, service.id, name="Received")

        _run(process_message(db, FakeMessage(chat_id="666", text=f"Service {service.id} - {service.name}")))
        _run(process_message(db, FakeMessage(chat_id="666", text="Ali")))

        requests_msg = FakeMessage(chat_id="666", text=states.MAIN_MY_REQUESTS)
        _run(process_message(db, requests_msg))
        assert "Your requests" in requests_msg.replies[-1][0]

        request = db.scalar(select(Request).where(Request.chat_id == "666"))
        details_msg = FakeMessage(chat_id="666", text=f"Request {request.id} - {request.tracking_code}")
        _run(process_message(db, details_msg))

        assert "Service: History" in details_msg.replies[-1][0]
        assert "Name: Ali" in details_msg.replies[-1][0]
