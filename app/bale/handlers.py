from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.bale import keyboards, states
from app.database import get_session_factory
from app.models import FieldType, RequestState
from app.services.bot_flow import (
    BusinessRuleError,
    ValidationError,
    cancel_current_unfinished_request,
    clear_conversation_state,
    get_conversation_context,
    get_next_unanswered_field,
    get_request_details_for_chat,
    list_active_services,
    list_beneficiary_requests,
    save_field_answer_from_file,
    save_field_answer_from_text,
    set_conversation_state,
    start_or_get_unfinished_request,
    submit_current_request_if_complete,
)

_SERVICE_BUTTON_PATTERN = re.compile(r"^Service\s+(\d+)\s+-\s+.+$")
_REQUEST_BUTTON_PATTERN = re.compile(r"^Request\s+(\d+)\s+-\s+.+$")


def _extract_chat_id(message: Any) -> str:
    chat = getattr(message, "chat", None)
    if chat is not None and getattr(chat, "id", None) is not None:
        return str(chat.id)

    chat_id = getattr(message, "chat_id", None)
    if chat_id is not None:
        return str(chat_id)

    raise ValueError("Could not extract chat_id from message")


def _extract_text(message: Any) -> str | None:
    text = getattr(message, "text", None)
    if text is None:
        return None
    return str(text).strip()


def _extract_file_metadata(message: Any) -> tuple[str, str | None] | None:
    for attr_name in ("document", "file"):
        obj = getattr(message, attr_name, None)
        if obj is None:
            continue

        file_id = getattr(obj, "file_id", None) or getattr(obj, "id", None) or getattr(obj, "unique_id", None)
        file_name = getattr(obj, "file_name", None) or getattr(obj, "name", None)
        if file_id:
            return str(file_id), str(file_name) if file_name else None

    return None


async def _reply(message: Any, text: str, rows: list[list[str]] | None = None) -> None:
    if rows is None:
        await message.reply(text)
        return

    markup = keyboards.to_reply_keyboard(rows)
    if markup is None:
        await message.reply(text)
        return

    await message.reply(text, markup)


def _field_prompt(field) -> str:
    if field.field_type == FieldType.TEXT:
        return f"{field.label}\n(Please send text)"
    if field.field_type == FieldType.NUMBER:
        return f"{field.label}\n(Please send a number)"
    return f"{field.label}\n(Please send one file/document)"


def _format_request_row(request) -> str:
    status = request.current_status.name if request.current_status else request.state.value
    tracking = request.tracking_code or "UNFINISHED"
    created = request.created_at.strftime("%Y-%m-%d %H:%M") if isinstance(request.created_at, datetime) else str(request.created_at)
    return f"{created} | {request.service.name} | {tracking} | {status}"


def _format_request_details(request) -> str:
    status = request.current_status.name if request.current_status else request.state.value
    lines = [
        f"Service: {request.service.name}",
        f"Tracking: {request.tracking_code or 'UNFINISHED'}",
        f"Status: {status}",
        "Answers:",
    ]

    for answer in request.answers:
        if answer.field_type_snapshot == FieldType.TEXT:
            value = answer.value_text or ""
        elif answer.field_type_snapshot == FieldType.NUMBER:
            value = str(answer.value_number) if answer.value_number is not None else ""
        else:
            value = answer.original_filename or answer.file_path or ""

        lines.append(f"- {answer.field_label_snapshot}: {value}")

    return "\n".join(lines)


async def _show_start_menu(db: Session, message: Any, chat_id: str) -> None:
    services = list_active_services(db)
    if not services:
        await _reply(message, "No active services are available right now.", keyboards.main_menu_rows())
        return

    service_lines = "\n".join([f"- {service.name}" for service in services])
    text = f"Welcome. Please choose a service:\n{service_lines}"
    await _reply(message, text, keyboards.services_rows(services))


async def _show_services_menu(db: Session, message: Any) -> None:
    services = list_active_services(db)
    if not services:
        await _reply(message, "No active services are available right now.", keyboards.main_menu_rows())
        return

    await _reply(message, "Select a service:", keyboards.services_rows(services))


async def _prompt_next_field_or_submit(db: Session, message: Any, chat_id: str, request_id: int) -> None:
    next_field = get_next_unanswered_field(db, request_id=request_id)
    if next_field is None:
        submitted = submit_current_request_if_complete(db, request_id=request_id, chat_id=chat_id)
        clear_conversation_state(db, chat_id=chat_id)

        if submitted is None:
            await _reply(message, "Could not submit request.", keyboards.main_menu_rows())
            return

        status = submitted.current_status.name if submitted.current_status else submitted.state.value
        await _reply(
            message,
            f"Request submitted successfully.\nTracking code: {submitted.tracking_code}\nStatus: {status}",
            keyboards.main_menu_rows(),
        )
        return

    set_conversation_state(db, chat_id=chat_id, request_id=request_id, current_field_id=next_field.id)
    await _reply(message, _field_prompt(next_field), keyboards.unfinished_request_rows())


async def _handle_service_selection(db: Session, message: Any, chat_id: str, service_id: int) -> None:
    request, created_new = start_or_get_unfinished_request(db, chat_id=chat_id, service_id=service_id)

    if not created_new:
        set_conversation_state(db, chat_id=chat_id, request_id=request.id, current_field_id=None)
        await _reply(
            message,
            "You already have an unfinished request.",
            keyboards.unfinished_request_rows(),
        )
        return

    await _prompt_next_field_or_submit(db, message, chat_id, request.id)


async def _handle_continue_request(db: Session, message: Any, chat_id: str) -> None:
    state, request, _field = get_conversation_context(db, chat_id=chat_id)
    if request is None or request.state != RequestState.UNFINISHED:
        await _reply(message, "You do not have an unfinished request.", keyboards.main_menu_rows())
        clear_conversation_state(db, chat_id=chat_id)
        return

    await _prompt_next_field_or_submit(db, message, chat_id, request.id)


async def _handle_cancel_request(db: Session, message: Any, chat_id: str) -> None:
    try:
        cancel_current_unfinished_request(db, chat_id=chat_id)
        clear_conversation_state(db, chat_id=chat_id)
        await _reply(message, "Your unfinished request was cancelled.", keyboards.main_menu_rows())
    except BusinessRuleError:
        await _reply(message, "You do not have an unfinished request.", keyboards.main_menu_rows())


async def _handle_my_requests(db: Session, message: Any, chat_id: str) -> None:
    requests = list_beneficiary_requests(db, chat_id=chat_id)
    if not requests:
        await _reply(message, "You have no requests yet.", keyboards.main_menu_rows())
        return

    text = "Your requests:\n" + "\n".join(_format_request_row(request) for request in requests)
    await _reply(message, text, keyboards.requests_rows(requests))


async def _handle_request_details(db: Session, message: Any, chat_id: str, request_id: int) -> None:
    try:
        request = get_request_details_for_chat(db, chat_id=chat_id, request_id=request_id)
    except BusinessRuleError:
        await _reply(message, "Request not found.", keyboards.main_menu_rows())
        return

    await _reply(message, _format_request_details(request), keyboards.main_menu_rows())


async def _handle_field_answer(db: Session, message: Any, chat_id: str, text: str | None) -> None:
    _state, request, field = get_conversation_context(db, chat_id=chat_id)
    if request is None or request.state != RequestState.UNFINISHED or field is None:
        await _reply(message, "Please start a new request from the menu.", keyboards.main_menu_rows())
        return

    try:
        if field.field_type == FieldType.FILE:
            file_meta = _extract_file_metadata(message)
            if file_meta is None:
                await _reply(message, "Please send a file for this question.", keyboards.unfinished_request_rows())
                return

            file_id, original_filename = file_meta
            save_field_answer_from_file(
                db,
                request_id=request.id,
                chat_id=chat_id,
                field=field,
                file_id=file_id,
                original_filename=original_filename,
            )
        else:
            if not text:
                await _reply(message, "Please send text for this question.", keyboards.unfinished_request_rows())
                return

            save_field_answer_from_text(
                db,
                request_id=request.id,
                chat_id=chat_id,
                field=field,
                text=text,
            )

        await _prompt_next_field_or_submit(db, message, chat_id, request.id)
    except ValidationError as exc:
        await _reply(message, str(exc), keyboards.unfinished_request_rows())
    except BusinessRuleError as exc:
        clear_conversation_state(db, chat_id=chat_id)
        await _reply(message, str(exc), keyboards.main_menu_rows())


async def process_message(db: Session, message: Any) -> None:
    chat_id = _extract_chat_id(message)
    text = _extract_text(message)

    if text in {"/start", states.MAIN_MENU}:
        await _show_start_menu(db, message, chat_id)
        return

    if text == states.MAIN_NEW_REQUEST:
        await _show_services_menu(db, message)
        return

    if text == states.MAIN_MY_REQUESTS:
        await _handle_my_requests(db, message, chat_id)
        return

    if text == states.MAIN_CANCEL_CURRENT or text == states.CANCEL_REQUEST:
        await _handle_cancel_request(db, message, chat_id)
        return

    if text == states.CONTINUE_REQUEST:
        await _handle_continue_request(db, message, chat_id)
        return

    if text:
        service_match = _SERVICE_BUTTON_PATTERN.match(text)
        if service_match:
            service_id = int(service_match.group(1))
            try:
                await _handle_service_selection(db, message, chat_id, service_id)
            except BusinessRuleError as exc:
                await _reply(message, str(exc), keyboards.main_menu_rows())
            return

        request_match = _REQUEST_BUTTON_PATTERN.match(text)
        if request_match:
            request_id = int(request_match.group(1))
            await _handle_request_details(db, message, chat_id, request_id)
            return

    await _handle_field_answer(db, message, chat_id, text)


async def handle_message(message: Any) -> None:
    session_factory = get_session_factory()
    with session_factory() as db:
        await process_message(db, message)


def register_handlers(bot: Any) -> None:
    @bot.on_message()
    async def _on_message(*args, **kwargs):
        message = kwargs.get("message")
        if message is None and args:
            message = args[-1]
        if message is None:
            return

        await handle_message(message)
