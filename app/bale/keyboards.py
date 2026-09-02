import asyncio
from typing import Any

from app.bale import states


def main_menu_rows() -> list[list[str]]:
    return [
        [states.MAIN_NEW_REQUEST],
        [states.MAIN_MY_REQUESTS],
        [states.MAIN_CANCEL_CURRENT],
    ]


def unfinished_request_rows() -> list[list[str]]:
    return [
        [states.CONTINUE_REQUEST],
        [states.CANCEL_REQUEST],
        [states.MAIN_MENU],
    ]


def services_rows(services: list[Any]) -> list[list[str]]:
    rows = [[f"{states.SERVICE_BUTTON_PREFIX} {service.id} - {service.name}"] for service in services]
    rows.append([states.MAIN_MY_REQUESTS])
    rows.append([states.MAIN_CANCEL_CURRENT])
    rows.append([states.MAIN_MENU])
    return rows


def requests_rows(requests: list[Any]) -> list[list[str]]:
    rows: list[list[str]] = []
    for request in requests:
        tracking = request.tracking_code or "UNFINISHED"
        rows.append([f"{states.REQUEST_BUTTON_PREFIX} {request.id} - {tracking}"])
    rows.append([states.MAIN_MENU])
    return rows


def to_reply_keyboard(rows: list[list[str]]):
    try:
        asyncio.get_event_loop()
    except RuntimeError:
        asyncio.set_event_loop(asyncio.new_event_loop())

    try:
        from balethon.objects import ReplyKeyboard
    except Exception:
        return None

    return ReplyKeyboard(*rows)
