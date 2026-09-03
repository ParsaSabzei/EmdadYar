from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models import ConversationState, FieldType, Request, RequestAnswer, RequestState, ServiceField
from app.services.core import (
    BusinessRuleError,
    ValidationError,
    cancel_unfinished_request,
    get_active_services,
    get_beneficiary_requests,
    get_request_details,
    get_service_fields_ordered,
    save_request_answer,
    start_unfinished_request,
    submit_request,
)


def get_or_create_conversation_state(db: Session, chat_id: str) -> ConversationState:
    state = db.scalar(select(ConversationState).where(ConversationState.chat_id == chat_id))
    if state is None:
        state = ConversationState(chat_id=chat_id)
        db.add(state)
        db.commit()
        db.refresh(state)
    return state


def set_conversation_state(
    db: Session,
    *,
    chat_id: str,
    request_id: int | None,
    current_field_id: int | None,
) -> ConversationState:
    state = get_or_create_conversation_state(db, chat_id)
    state.request_id = request_id
    state.current_field_id = current_field_id
    db.commit()
    db.refresh(state)
    return state


def clear_conversation_state(db: Session, *, chat_id: str) -> ConversationState:
    return set_conversation_state(db, chat_id=chat_id, request_id=None, current_field_id=None)


def get_unfinished_request(db: Session, *, chat_id: str) -> Request | None:
    return db.scalar(
        select(Request).where(Request.chat_id == chat_id, Request.state == RequestState.UNFINISHED).limit(1)
    )


def start_or_get_unfinished_request(db: Session, *, chat_id: str, service_id: int) -> tuple[Request, bool]:
    existing = get_unfinished_request(db, chat_id=chat_id)
    request = start_unfinished_request(db, chat_id=chat_id, service_id=service_id)
    return request, existing is None


def _has_meaningful_answer(answer: RequestAnswer | None, field_type: FieldType) -> bool:
    if answer is None:
        return False

    if field_type == FieldType.TEXT:
        return bool(answer.value_text and answer.value_text.strip())
    if field_type == FieldType.NUMBER:
        return answer.value_number is not None
    if field_type == FieldType.FILE:
        return bool(answer.file_path and answer.file_path.strip())
    return False


def get_next_unanswered_field(db: Session, *, request_id: int) -> ServiceField | None:
    request = db.get(Request, request_id)
    if request is None:
        return None

    fields = get_service_fields_ordered(db, request.service_id)
    answers = list(db.scalars(select(RequestAnswer).where(RequestAnswer.request_id == request_id)))
    answer_by_field_id = {answer.service_field_id: answer for answer in answers}

    for field in fields:
        answer = answer_by_field_id.get(field.id)
        if not _has_meaningful_answer(answer, field.field_type):
            return field

    return None


def save_field_answer_from_text(
    db: Session,
    *,
    request_id: int,
    chat_id: str,
    field: ServiceField,
    text: str,
) -> RequestAnswer:
    if field.field_type == FieldType.TEXT:
        return save_request_answer(
            db,
            request_id=request_id,
            chat_id=chat_id,
            service_field_id=field.id,
            text_value=text,
        )

    if field.field_type == FieldType.NUMBER:
        return save_request_answer(
            db,
            request_id=request_id,
            chat_id=chat_id,
            service_field_id=field.id,
            number_value=text,
        )

    raise ValidationError("This field expects a file")


def save_field_answer_from_file_path(
    db: Session,
    *,
    request_id: int,
    chat_id: str,
    field: ServiceField,
    stored_file_path: str,
    original_filename: str | None,
) -> RequestAnswer:
    if field.field_type != FieldType.FILE:
        raise ValidationError("This field expects text or number input")

    return save_request_answer(
        db,
        request_id=request_id,
        chat_id=chat_id,
        service_field_id=field.id,
        file_path=stored_file_path,
        original_filename=original_filename,
    )


def submit_current_request_if_complete(db: Session, *, request_id: int, chat_id: str) -> Request | None:
    next_field = get_next_unanswered_field(db, request_id=request_id)
    if next_field is not None:
        return None

    return submit_request(db, request_id=request_id, chat_id=chat_id)


def cancel_current_unfinished_request(db: Session, *, chat_id: str) -> Request:
    request = get_unfinished_request(db, chat_id=chat_id)
    if request is None:
        raise BusinessRuleError("No unfinished request found")
    return cancel_unfinished_request(db, request_id=request.id, chat_id=chat_id)


def get_request_details_for_chat(db: Session, *, chat_id: str, request_id: int) -> Request:
    request = get_request_details(db, request_id=request_id)
    if request.chat_id != chat_id:
        raise BusinessRuleError("Request does not belong to this beneficiary")
    return request


def list_beneficiary_requests(db: Session, *, chat_id: str) -> list[Request]:
    return get_beneficiary_requests(db, chat_id=chat_id)


def get_conversation_context(db: Session, *, chat_id: str) -> tuple[ConversationState, Request | None, ServiceField | None]:
    state = get_or_create_conversation_state(db, chat_id)
    request = None
    field = None

    if state.request_id is not None:
        request = db.scalar(
            select(Request)
            .where(Request.id == state.request_id)
            .options(joinedload(Request.service), joinedload(Request.current_status))
        )

    if state.current_field_id is not None:
        field = db.get(ServiceField, state.current_field_id)

    return state, request, field


def list_active_services(db: Session):
    return get_active_services(db)
