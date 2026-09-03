import random

from sqlalchemy import String, and_, cast, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload, selectinload

from app.models import FieldType, Request, RequestAnswer, RequestState, Service, ServiceField, ServiceStatus
from app.services.file_storage import delete_request_files


class BusinessRuleError(Exception):
    pass


class ValidationError(BusinessRuleError):
    pass


class NotFoundError(BusinessRuleError):
    pass


def _get_service_or_raise(db: Session, service_id: int) -> Service:
    service = db.get(Service, service_id)
    if service is None:
        raise NotFoundError("Service not found")
    return service


def _get_field_or_raise(db: Session, field_id: int) -> ServiceField:
    field = db.get(ServiceField, field_id)
    if field is None:
        raise NotFoundError("Service field not found")
    return field


def _get_status_or_raise(db: Session, status_id: int) -> ServiceStatus:
    status = db.get(ServiceStatus, status_id)
    if status is None:
        raise NotFoundError("Service status not found")
    return status


def _get_request_or_raise(db: Session, request_id: int) -> Request:
    request = db.get(Request, request_id)
    if request is None:
        raise NotFoundError("Request not found")
    return request


def _next_field_order(db: Session, service_id: int) -> int:
    max_order = db.scalar(select(func.max(ServiceField.display_order)).where(ServiceField.service_id == service_id))
    return int(max_order or 0) + 1


def _next_status_order(db: Session, service_id: int) -> int:
    max_order = db.scalar(select(func.max(ServiceStatus.display_order)).where(ServiceStatus.service_id == service_id))
    return int(max_order or 0) + 1


def _generate_unique_tracking_code(db: Session) -> str:
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    for _ in range(30):
        suffix = "".join(random.choices(alphabet, k=6))
        code = f"EMD-{suffix}"
        exists = db.scalar(select(Request.id).where(Request.tracking_code == code))
        if exists is None:
            return code
    raise BusinessRuleError("Could not generate unique tracking code")


def create_service(db: Session, name: str, is_active: bool = True) -> Service:
    if not name.strip():
        raise ValidationError("Service name cannot be empty")

    service = Service(name=name.strip(), is_active=is_active)
    db.add(service)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise ValidationError("Service name must be unique") from exc

    db.refresh(service)
    return service


def get_active_services(db: Session) -> list[Service]:
    statement = select(Service).where(Service.is_active.is_(True)).order_by(Service.name.asc())
    return list(db.scalars(statement))


def get_all_services(db: Session) -> list[Service]:
    statement = select(Service).order_by(Service.name.asc())
    return list(db.scalars(statement))


def update_service(db: Session, service_id: int, *, name: str | None = None, is_active: bool | None = None) -> Service:
    service = _get_service_or_raise(db, service_id)

    if name is not None:
        cleaned = name.strip()
        if not cleaned:
            raise ValidationError("Service name cannot be empty")
        service.name = cleaned

    if is_active is not None:
        service.is_active = is_active

    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise ValidationError("Service name must be unique") from exc

    db.refresh(service)
    return service


def set_service_active(db: Session, service_id: int, is_active: bool) -> Service:
    service = _get_service_or_raise(db, service_id)
    service.is_active = is_active
    db.commit()
    db.refresh(service)
    return service


def delete_service(db: Session, service_id: int) -> None:
    service = _get_service_or_raise(db, service_id)
    db.delete(service)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise BusinessRuleError("Cannot delete service with existing requests") from exc


def add_service_field(
    db: Session,
    service_id: int,
    *,
    label: str,
    field_type: FieldType,
    is_required: bool = True,
    display_order: int | None = None,
) -> ServiceField:
    _get_service_or_raise(db, service_id)

    if not label.strip():
        raise ValidationError("Field label cannot be empty")

    if not isinstance(field_type, FieldType):
        raise ValidationError("Invalid field type")

    field = ServiceField(
        service_id=service_id,
        label=label.strip(),
        field_type=field_type,
        is_required=is_required,
        display_order=display_order if display_order is not None else _next_field_order(db, service_id),
    )
    db.add(field)
    db.commit()
    db.refresh(field)
    return field


def update_service_field(
    db: Session,
    field_id: int,
    *,
    label: str | None = None,
    field_type: FieldType | None = None,
    is_required: bool | None = None,
    display_order: int | None = None,
) -> ServiceField:
    field = _get_field_or_raise(db, field_id)

    if label is not None:
        cleaned = label.strip()
        if not cleaned:
            raise ValidationError("Field label cannot be empty")
        field.label = cleaned

    if field_type is not None:
        if not isinstance(field_type, FieldType):
            raise ValidationError("Invalid field type")
        field.field_type = field_type

    if is_required is not None:
        field.is_required = is_required

    if display_order is not None:
        field.display_order = display_order

    db.commit()
    db.refresh(field)
    return field


def delete_service_field(db: Session, field_id: int) -> None:
    field = _get_field_or_raise(db, field_id)
    db.delete(field)
    db.commit()


def get_service_fields_ordered(db: Session, service_id: int) -> list[ServiceField]:
    _get_service_or_raise(db, service_id)
    statement = (
        select(ServiceField)
        .where(ServiceField.service_id == service_id)
        .order_by(ServiceField.display_order.asc(), ServiceField.id.asc())
    )
    return list(db.scalars(statement))


def reorder_service_fields(db: Session, service_id: int, ordered_field_ids: list[int]) -> list[ServiceField]:
    fields = get_service_fields_ordered(db, service_id)
    existing_ids = [field.id for field in fields]

    if sorted(existing_ids) != sorted(ordered_field_ids):
        raise ValidationError("Field IDs must exactly match service fields")

    id_to_field = {field.id: field for field in fields}
    for idx, field_id in enumerate(ordered_field_ids, start=1):
        id_to_field[field_id].display_order = idx

    db.commit()
    return get_service_fields_ordered(db, service_id)


def add_service_status(
    db: Session,
    service_id: int,
    *,
    name: str,
    display_order: int | None = None,
) -> ServiceStatus:
    _get_service_or_raise(db, service_id)

    if not name.strip():
        raise ValidationError("Status name cannot be empty")

    status = ServiceStatus(
        service_id=service_id,
        name=name.strip(),
        display_order=display_order if display_order is not None else _next_status_order(db, service_id),
    )
    db.add(status)
    db.commit()
    db.refresh(status)
    return status


def update_service_status(
    db: Session,
    status_id: int,
    *,
    name: str | None = None,
    display_order: int | None = None,
) -> ServiceStatus:
    status = _get_status_or_raise(db, status_id)

    if name is not None:
        cleaned = name.strip()
        if not cleaned:
            raise ValidationError("Status name cannot be empty")
        status.name = cleaned

    if display_order is not None:
        status.display_order = display_order

    db.commit()
    db.refresh(status)
    return status


def delete_service_status(db: Session, status_id: int) -> None:
    status = _get_status_or_raise(db, status_id)
    in_use = db.scalar(select(Request.id).where(Request.current_status_id == status.id).limit(1))
    if in_use is not None:
        raise BusinessRuleError("Cannot delete a status that is used by requests")

    db.delete(status)
    db.commit()


def get_service_statuses_ordered(db: Session, service_id: int) -> list[ServiceStatus]:
    _get_service_or_raise(db, service_id)
    statement = (
        select(ServiceStatus)
        .where(ServiceStatus.service_id == service_id)
        .order_by(ServiceStatus.display_order.asc(), ServiceStatus.id.asc())
    )
    return list(db.scalars(statement))


def reorder_service_statuses(db: Session, service_id: int, ordered_status_ids: list[int]) -> list[ServiceStatus]:
    statuses = get_service_statuses_ordered(db, service_id)
    existing_ids = [status.id for status in statuses]

    if sorted(existing_ids) != sorted(ordered_status_ids):
        raise ValidationError("Status IDs must exactly match service statuses")

    id_to_status = {status.id: status for status in statuses}
    for idx, status_id in enumerate(ordered_status_ids, start=1):
        id_to_status[status_id].display_order = idx

    db.commit()
    return get_service_statuses_ordered(db, service_id)


def start_unfinished_request(db: Session, chat_id: str, service_id: int) -> Request:
    if not chat_id.strip():
        raise ValidationError("chat_id cannot be empty")

    service = _get_service_or_raise(db, service_id)
    if not service.is_active:
        raise BusinessRuleError("Service is disabled")

    existing = db.scalar(
        select(Request).where(Request.chat_id == chat_id, Request.state == RequestState.UNFINISHED).limit(1)
    )
    if existing is not None:
        return existing

    request = Request(
        chat_id=chat_id,
        service_id=service_id,
        state=RequestState.UNFINISHED,
        current_status_id=None,
    )
    db.add(request)
    db.commit()
    db.refresh(request)
    return request


def _normalize_number(value: float | int | str | None) -> float:
    if value is None:
        raise ValidationError("NUMBER answer must be numeric")

    if isinstance(value, (int, float)):
        return float(value)

    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            raise ValidationError("NUMBER answer must be numeric")
        try:
            return float(raw)
        except ValueError as exc:
            raise ValidationError("NUMBER answer must be numeric") from exc

    raise ValidationError("NUMBER answer must be numeric")


def save_request_answer(
    db: Session,
    *,
    request_id: int,
    chat_id: str,
    service_field_id: int,
    text_value: str | None = None,
    number_value: float | int | str | None = None,
    file_path: str | None = None,
    original_filename: str | None = None,
) -> RequestAnswer:
    request = _get_request_or_raise(db, request_id)
    if request.chat_id != chat_id:
        raise BusinessRuleError("Request does not belong to this beneficiary")
    if request.state != RequestState.UNFINISHED:
        raise BusinessRuleError("Answers can only be changed for unfinished requests")

    field = _get_field_or_raise(db, service_field_id)
    if field.service_id != request.service_id:
        raise ValidationError("Field does not belong to request service")

    answer = db.scalar(
        select(RequestAnswer).where(
            RequestAnswer.request_id == request_id,
            RequestAnswer.service_field_id == service_field_id,
        )
    )
    if answer is None:
        answer = RequestAnswer(
            request_id=request_id,
            service_field_id=service_field_id,
            field_label_snapshot=field.label,
            field_type_snapshot=field.field_type,
        )
        db.add(answer)

    answer.field_label_snapshot = field.label
    answer.field_type_snapshot = field.field_type
    answer.value_text = None
    answer.value_number = None
    answer.file_path = None
    answer.original_filename = None

    if field.field_type == FieldType.TEXT:
        if text_value is None or not text_value.strip():
            raise ValidationError("TEXT answer must contain text")
        answer.value_text = text_value.strip()
    elif field.field_type == FieldType.NUMBER:
        answer.value_number = _normalize_number(number_value)
    elif field.field_type == FieldType.FILE:
        if file_path is None or not file_path.strip():
            raise ValidationError("FILE answer must include file path")
        answer.file_path = file_path.strip()
        answer.original_filename = original_filename.strip() if original_filename else None
    else:
        raise ValidationError("Unsupported field type")

    db.commit()
    db.refresh(answer)
    return answer


def _is_answer_present_for_required_field(answer: RequestAnswer | None, field_type: FieldType) -> bool:
    if answer is None:
        return False

    if field_type == FieldType.TEXT:
        return bool(answer.value_text and answer.value_text.strip())

    if field_type == FieldType.NUMBER:
        return answer.value_number is not None

    if field_type == FieldType.FILE:
        return bool(answer.file_path and answer.file_path.strip())

    return False


def submit_request(db: Session, *, request_id: int, chat_id: str) -> Request:
    request = _get_request_or_raise(db, request_id)

    if request.chat_id != chat_id:
        raise BusinessRuleError("Request does not belong to this beneficiary")
    if request.state != RequestState.UNFINISHED:
        raise BusinessRuleError("Only unfinished requests can be submitted")

    required_fields = list(
        db.scalars(
            select(ServiceField).where(
                ServiceField.service_id == request.service_id,
                ServiceField.is_required.is_(True),
            )
        )
    )

    answers = list(db.scalars(select(RequestAnswer).where(RequestAnswer.request_id == request.id)))
    answers_by_field_id = {answer.service_field_id: answer for answer in answers}

    missing_labels: list[str] = []
    for field in required_fields:
        answer = answers_by_field_id.get(field.id)
        if not _is_answer_present_for_required_field(answer, field.field_type):
            missing_labels.append(field.label)

    if missing_labels:
        raise ValidationError(f"Required fields are missing answers: {', '.join(missing_labels)}")

    request.state = RequestState.SUBMITTED

    if request.tracking_code is None:
        request.tracking_code = _generate_unique_tracking_code(db)

    first_status = db.scalar(
        select(ServiceStatus)
        .where(ServiceStatus.service_id == request.service_id)
        .order_by(ServiceStatus.display_order.asc(), ServiceStatus.id.asc())
        .limit(1)
    )
    request.current_status_id = first_status.id if first_status is not None else None

    db.commit()
    db.refresh(request)
    return request


def cancel_unfinished_request(db: Session, *, request_id: int, chat_id: str) -> Request:
    request = _get_request_or_raise(db, request_id)

    if request.chat_id != chat_id:
        raise BusinessRuleError("Request does not belong to this beneficiary")
    if request.state != RequestState.UNFINISHED:
        raise BusinessRuleError("Only unfinished requests can be cancelled")

    request.state = RequestState.CANCELLED
    db.commit()
    db.refresh(request)
    return request


def get_requests_for_admin(
    db: Session,
    *,
    service_id: int | None = None,
    status_id: int | None = None,
    search_name: str | None = None,
    search_national_id: str | None = None,
    search_tracking_code: str | None = None,
) -> list[Request]:
    statement = select(Request).distinct().options(
        joinedload(Request.service),
        joinedload(Request.current_status),
        selectinload(Request.answers),
    )

    if service_id is not None:
        statement = statement.where(Request.service_id == service_id)

    if status_id is not None:
        statement = statement.where(Request.current_status_id == status_id)

    if search_tracking_code and search_tracking_code.strip():
        pattern = f"%{search_tracking_code.strip().lower()}%"
        statement = statement.where(func.lower(Request.tracking_code).like(pattern))

    if search_name and search_name.strip():
        pattern = f"%{search_name.strip().lower()}%"
        request_ids_for_name = select(RequestAnswer.request_id).where(
            and_(
                RequestAnswer.field_type_snapshot == FieldType.TEXT,
                func.lower(RequestAnswer.value_text).like(pattern),
            )
        )
        statement = statement.where(Request.id.in_(request_ids_for_name))

    if search_national_id and search_national_id.strip():
        pattern = f"%{search_national_id.strip()}%"
        request_ids_for_nid = select(RequestAnswer.request_id).where(
            or_(
                cast(RequestAnswer.value_number, String).like(pattern),
                RequestAnswer.value_text.like(pattern),
            )
        )
        statement = statement.where(Request.id.in_(request_ids_for_nid))

    statement = statement.order_by(Request.created_at.desc(), Request.id.desc())
    return list(db.scalars(statement))


def delete_request_permanently(db: Session, *, request_id: int) -> None:
    request = _get_request_or_raise(db, request_id)

    file_paths = [answer.file_path for answer in request.answers if answer.file_path]
    delete_request_files([path for path in file_paths if path is not None])

    db.delete(request)
    db.commit()


def set_request_status(db: Session, *, request_id: int, status_id: int) -> Request:
    request = _get_request_or_raise(db, request_id)
    status = _get_status_or_raise(db, status_id)

    if status.service_id != request.service_id:
        raise ValidationError("Status does not belong to request service")

    request.current_status_id = status.id
    db.commit()
    db.refresh(request)
    return request


def get_beneficiary_requests(db: Session, *, chat_id: str) -> list[Request]:
    statement = (
        select(Request)
        .where(Request.chat_id == chat_id)
        .options(joinedload(Request.service), joinedload(Request.current_status))
        .order_by(Request.created_at.desc(), Request.id.desc())
    )
    return list(db.scalars(statement))


def get_request_details(db: Session, *, request_id: int) -> Request:
    statement = (
        select(Request)
        .where(Request.id == request_id)
        .options(
            joinedload(Request.service),
            joinedload(Request.current_status),
            selectinload(Request.answers).joinedload(RequestAnswer.service_field),
        )
    )
    request = db.scalar(statement)
    if request is None:
        raise NotFoundError("Request not found")
    return request
