from pathlib import Path
import re
import secrets
from typing import Any
from urllib.parse import quote_plus

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth import authenticate_admin
from app.bale.messaging import send_text_message
from app.database import get_db
from app.models import Admin, FieldType, Request as BeneficiaryRequest, RequestAnswer, RequestState, Service, ServiceStatus
from app.services import (
    BusinessRuleError,
    ValidationError,
    add_service_field,
    add_service_status,
    create_service,
    delete_request_permanently,
    delete_service,
    delete_service_field,
    delete_service_status,
    get_all_services,
    get_request_details,
    get_requests_for_admin,
    get_service_fields_ordered,
    get_service_statuses_ordered,
    reorder_service_fields,
    reorder_service_statuses,
    set_request_status,
    update_service,
    update_service_field,
    update_service_status,
)
from app.services.file_storage import is_resolved_file_in_request_dir, resolve_stored_file_path
from app.utils.jalali import format_jalali_datetime


TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
templates.env.filters["jalali"] = format_jalali_datetime

router = APIRouter(prefix="/admin", tags=["admin"])


def _redirect(url: str) -> RedirectResponse:
    return RedirectResponse(url=url, status_code=303)


def _quote_message(value: str) -> str:
    return quote_plus(value)


def _get_or_create_csrf_token(request: Request) -> str:
    token = request.session.get("csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        request.session["csrf_token"] = token
    return token


def _verify_csrf(request: Request, submitted_token: str) -> None:
    session_token = request.session.get("csrf_token")
    if not session_token or not submitted_token or not secrets.compare_digest(session_token, submitted_token):
        raise HTTPException(status_code=403, detail="Invalid CSRF token")


def _is_checked(value: str | None) -> bool:
    return value == "on"


def _require_admin(request: Request, db: Session) -> Admin | RedirectResponse:
    admin_id = request.session.get("admin_id")
    if admin_id is None:
        return _redirect("/admin/login")

    admin = db.get(Admin, admin_id)
    if admin is None or not admin.is_active:
        request.session.clear()
        return _redirect("/admin/login")

    return admin


def _admin_context(request: Request, admin: Admin, **kwargs: Any) -> dict[str, Any]:
    return {"request": request, "admin": admin, "csrf_token": _get_or_create_csrf_token(request), **kwargs}


def _beneficiary_name_from_request(request_item: BeneficiaryRequest) -> str:
    name_label_pattern = re.compile(r"(name|نام)", re.IGNORECASE)

    for answer in request_item.answers:
        if answer.field_type_snapshot == FieldType.TEXT and answer.field_label_snapshot and name_label_pattern.search(answer.field_label_snapshot):
            return answer.value_text or "-"

    for answer in request_item.answers:
        if answer.field_type_snapshot == FieldType.TEXT and answer.value_text:
            return answer.value_text

    return "-"


@router.get("/login", response_class=HTMLResponse)
def admin_login_page(request: Request, db: Session = Depends(get_db)):
    existing = _require_admin(request, db)
    if isinstance(existing, RedirectResponse):
        return templates.TemplateResponse(request, "admin/login.html", {"error": None, "csrf_token": _get_or_create_csrf_token(request)})
    return _redirect("/admin")


@router.post("/login", response_class=HTMLResponse)
def admin_login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    csrf_token: str = Form(...),
    db: Session = Depends(get_db),
):
    _verify_csrf(request, csrf_token)

    admin = authenticate_admin(db, username, password)
    if admin is None:
        return templates.TemplateResponse(
            request,
            "admin/login.html",
            {"error": "Invalid username or password", "csrf_token": _get_or_create_csrf_token(request)},
            status_code=400,
        )

    request.session["admin_id"] = admin.id
    return _redirect("/admin")


@router.post("/logout")
def admin_logout(request: Request, csrf_token: str = Form(...)):
    _verify_csrf(request, csrf_token)
    request.session.clear()
    return _redirect("/admin/login")


@router.get("", response_class=HTMLResponse)
def admin_dashboard(request: Request, db: Session = Depends(get_db)):
    admin = _require_admin(request, db)
    if isinstance(admin, RedirectResponse):
        return admin

    stats = {
        "services": db.scalar(select(func.count(Service.id))) or 0,
        "requests": db.scalar(select(func.count(BeneficiaryRequest.id))) or 0,
        "submitted": db.scalar(select(func.count(BeneficiaryRequest.id)).where(BeneficiaryRequest.state == RequestState.SUBMITTED)) or 0,
        "unfinished": db.scalar(select(func.count(BeneficiaryRequest.id)).where(BeneficiaryRequest.state == RequestState.UNFINISHED)) or 0,
        "cancelled": db.scalar(select(func.count(BeneficiaryRequest.id)).where(BeneficiaryRequest.state == RequestState.CANCELLED)) or 0,
    }

    return templates.TemplateResponse(request, "admin/dashboard.html", _admin_context(request, admin, stats=stats))


@router.get("/services", response_class=HTMLResponse)
def services_page(request: Request, db: Session = Depends(get_db), message: str | None = None, error: str | None = None):
    admin = _require_admin(request, db)
    if isinstance(admin, RedirectResponse):
        return admin

    services = get_all_services(db)
    return templates.TemplateResponse(request, "admin/services.html", _admin_context(request, admin, services=services, message=message, error=error))


@router.post("/services/create")
def create_service_route(
    request: Request,
    name: str = Form(...),
    is_active: str | None = Form(None),
    csrf_token: str = Form(...),
    db: Session = Depends(get_db),
):
    admin = _require_admin(request, db)
    if isinstance(admin, RedirectResponse):
        return admin
    _verify_csrf(request, csrf_token)

    try:
        create_service(db, name=name, is_active=_is_checked(is_active))
        return _redirect("/admin/services?message=Service+created")
    except BusinessRuleError as exc:
        return _redirect(f"/admin/services?error={_quote_message(str(exc))}")


@router.get("/services/{service_id}/edit", response_class=HTMLResponse)
def edit_service_page(request: Request, service_id: int, db: Session = Depends(get_db), error: str | None = None):
    admin = _require_admin(request, db)
    if isinstance(admin, RedirectResponse):
        return admin

    service = db.get(Service, service_id)
    if service is None:
        return _redirect("/admin/services?error=Service+not+found")

    return templates.TemplateResponse(request, "admin/service_edit.html", _admin_context(request, admin, service=service, error=error))


@router.post("/services/{service_id}/edit")
def edit_service_route(
    request: Request,
    service_id: int,
    name: str = Form(...),
    is_active: str | None = Form(None),
    csrf_token: str = Form(...),
    db: Session = Depends(get_db),
):
    admin = _require_admin(request, db)
    if isinstance(admin, RedirectResponse):
        return admin
    _verify_csrf(request, csrf_token)

    try:
        update_service(db, service_id, name=name, is_active=_is_checked(is_active))
        return _redirect("/admin/services?message=Service+updated")
    except BusinessRuleError as exc:
        return _redirect(f"/admin/services/{service_id}/edit?error={_quote_message(str(exc))}")


@router.post("/services/{service_id}/delete")
def delete_service_route(request: Request, service_id: int, csrf_token: str = Form(...), db: Session = Depends(get_db)):
    admin = _require_admin(request, db)
    if isinstance(admin, RedirectResponse):
        return admin
    _verify_csrf(request, csrf_token)

    try:
        delete_service(db, service_id)
        return _redirect("/admin/services?message=Service+deleted")
    except BusinessRuleError as exc:
        return _redirect(f"/admin/services?error={_quote_message(str(exc))}")


@router.get("/services/{service_id}/fields", response_class=HTMLResponse)
def service_fields_page(request: Request, service_id: int, db: Session = Depends(get_db), error: str | None = None):
    admin = _require_admin(request, db)
    if isinstance(admin, RedirectResponse):
        return admin

    service = db.get(Service, service_id)
    if service is None:
        return _redirect("/admin/services?error=Service+not+found")

    fields = get_service_fields_ordered(db, service_id)
    return templates.TemplateResponse(
        request,
        "admin/service_fields.html",
        _admin_context(request, admin, service=service, fields=fields, field_types=list(FieldType), error=error),
    )


@router.post("/services/{service_id}/fields/create")
def create_field_route(
    request: Request,
    service_id: int,
    label: str = Form(...),
    field_type: str = Form(...),
    is_required: str | None = Form(None),
    csrf_token: str = Form(...),
    db: Session = Depends(get_db),
):
    admin = _require_admin(request, db)
    if isinstance(admin, RedirectResponse):
        return admin
    _verify_csrf(request, csrf_token)

    try:
        add_service_field(db, service_id, label=label, field_type=FieldType(field_type), is_required=_is_checked(is_required))
        return _redirect(f"/admin/services/{service_id}/fields")
    except (ValueError, BusinessRuleError) as exc:
        return _redirect(f"/admin/services/{service_id}/fields?error={_quote_message(str(exc))}")


@router.post("/services/{service_id}/fields/{field_id}/edit")
def edit_field_route(
    request: Request,
    service_id: int,
    field_id: int,
    label: str = Form(...),
    field_type: str = Form(...),
    is_required: str | None = Form(None),
    csrf_token: str = Form(...),
    db: Session = Depends(get_db),
):
    admin = _require_admin(request, db)
    if isinstance(admin, RedirectResponse):
        return admin
    _verify_csrf(request, csrf_token)

    try:
        update_service_field(db, field_id, label=label, field_type=FieldType(field_type), is_required=_is_checked(is_required))
        return _redirect(f"/admin/services/{service_id}/fields")
    except (ValueError, BusinessRuleError) as exc:
        return _redirect(f"/admin/services/{service_id}/fields?error={_quote_message(str(exc))}")


@router.post("/services/{service_id}/fields/{field_id}/delete")
def delete_field_route(request: Request, service_id: int, field_id: int, csrf_token: str = Form(...), db: Session = Depends(get_db)):
    admin = _require_admin(request, db)
    if isinstance(admin, RedirectResponse):
        return admin
    _verify_csrf(request, csrf_token)

    try:
        delete_service_field(db, field_id)
    except BusinessRuleError as exc:
        return _redirect(f"/admin/services/{service_id}/fields?error={_quote_message(str(exc))}")

    return _redirect(f"/admin/services/{service_id}/fields")


@router.post("/services/{service_id}/fields/reorder")
def reorder_fields_route(
    request: Request,
    service_id: int,
    ordered_field_ids: str = Form(...),
    csrf_token: str = Form(...),
    db: Session = Depends(get_db),
):
    admin = _require_admin(request, db)
    if isinstance(admin, RedirectResponse):
        return admin
    _verify_csrf(request, csrf_token)

    try:
        ids = [int(x.strip()) for x in ordered_field_ids.split(",") if x.strip()]
        reorder_service_fields(db, service_id, ids)
        return _redirect(f"/admin/services/{service_id}/fields")
    except (ValueError, BusinessRuleError) as exc:
        return _redirect(f"/admin/services/{service_id}/fields?error={_quote_message(str(exc))}")


@router.get("/services/{service_id}/statuses", response_class=HTMLResponse)
def service_statuses_page(request: Request, service_id: int, db: Session = Depends(get_db), error: str | None = None):
    admin = _require_admin(request, db)
    if isinstance(admin, RedirectResponse):
        return admin

    service = db.get(Service, service_id)
    if service is None:
        return _redirect("/admin/services?error=Service+not+found")

    statuses = get_service_statuses_ordered(db, service_id)
    return templates.TemplateResponse(request, "admin/service_statuses.html", _admin_context(request, admin, service=service, statuses=statuses, error=error))


@router.post("/services/{service_id}/statuses/create")
def create_status_route(
    request: Request,
    service_id: int,
    name: str = Form(...),
    csrf_token: str = Form(...),
    db: Session = Depends(get_db),
):
    admin = _require_admin(request, db)
    if isinstance(admin, RedirectResponse):
        return admin
    _verify_csrf(request, csrf_token)

    try:
        add_service_status(db, service_id, name=name)
        return _redirect(f"/admin/services/{service_id}/statuses")
    except BusinessRuleError as exc:
        return _redirect(f"/admin/services/{service_id}/statuses?error={_quote_message(str(exc))}")


@router.post("/services/{service_id}/statuses/{status_id}/edit")
def edit_status_route(
    request: Request,
    service_id: int,
    status_id: int,
    name: str = Form(...),
    csrf_token: str = Form(...),
    db: Session = Depends(get_db),
):
    admin = _require_admin(request, db)
    if isinstance(admin, RedirectResponse):
        return admin
    _verify_csrf(request, csrf_token)

    try:
        update_service_status(db, status_id, name=name)
        return _redirect(f"/admin/services/{service_id}/statuses")
    except BusinessRuleError as exc:
        return _redirect(f"/admin/services/{service_id}/statuses?error={_quote_message(str(exc))}")


@router.post("/services/{service_id}/statuses/{status_id}/delete")
def delete_status_route(request: Request, service_id: int, status_id: int, csrf_token: str = Form(...), db: Session = Depends(get_db)):
    admin = _require_admin(request, db)
    if isinstance(admin, RedirectResponse):
        return admin
    _verify_csrf(request, csrf_token)

    try:
        delete_service_status(db, status_id)
        return _redirect(f"/admin/services/{service_id}/statuses")
    except BusinessRuleError as exc:
        return _redirect(f"/admin/services/{service_id}/statuses?error={_quote_message(str(exc))}")


@router.post("/services/{service_id}/statuses/reorder")
def reorder_statuses_route(
    request: Request,
    service_id: int,
    ordered_status_ids: str = Form(...),
    csrf_token: str = Form(...),
    db: Session = Depends(get_db),
):
    admin = _require_admin(request, db)
    if isinstance(admin, RedirectResponse):
        return admin
    _verify_csrf(request, csrf_token)

    try:
        ids = [int(x.strip()) for x in ordered_status_ids.split(",") if x.strip()]
        reorder_service_statuses(db, service_id, ids)
        return _redirect(f"/admin/services/{service_id}/statuses")
    except (ValueError, BusinessRuleError) as exc:
        return _redirect(f"/admin/services/{service_id}/statuses?error={_quote_message(str(exc))}")


@router.get("/requests", response_class=HTMLResponse)
def requests_page(
    request: Request,
    db: Session = Depends(get_db),
    service_id: str | None = None,
    status_id: str | None = None,
    search_name: str | None = None,
    search_national_id: str | None = None,
    search_tracking_code: str | None = None,
    message: str | None = None,
    error: str | None = None,
):
    admin = _require_admin(request, db)
    if isinstance(admin, RedirectResponse):
        return admin

    selected_service_id = int(service_id) if service_id and service_id.isdigit() else None
    selected_status_id = int(status_id) if status_id and status_id.isdigit() else None

    requests = get_requests_for_admin(
        db,
        service_id=selected_service_id,
        status_id=selected_status_id,
        search_name=search_name,
        search_national_id=search_national_id,
        search_tracking_code=search_tracking_code,
    )
    services = get_all_services(db)
    statuses = list(db.scalars(select(ServiceStatus).order_by(ServiceStatus.name.asc())))
    beneficiary_names = {item.id: _beneficiary_name_from_request(item) for item in requests}

    return templates.TemplateResponse(
        request,
        "admin/requests.html",
        _admin_context(
            request,
            admin,
            requests=requests,
            services=services,
            statuses=statuses,
            selected_service_id=selected_service_id,
            selected_status_id=selected_status_id,
            search_name=search_name or "",
            search_national_id=search_national_id or "",
            search_tracking_code=search_tracking_code or "",
            message=message,
            error=error,
            beneficiary_names=beneficiary_names,
        ),
    )


@router.get("/requests/{request_id}", response_class=HTMLResponse)
def request_details_page(request: Request, request_id: int, db: Session = Depends(get_db), error: str | None = None, message: str | None = None):
    admin = _require_admin(request, db)
    if isinstance(admin, RedirectResponse):
        return admin

    try:
        req = get_request_details(db, request_id=request_id)
    except BusinessRuleError:
        return _redirect("/admin/requests")

    statuses = get_service_statuses_ordered(db, req.service_id)
    return templates.TemplateResponse(request, "admin/request_details.html", _admin_context(request, admin, request_item=req, statuses=statuses, error=error, message=message))


@router.post("/requests/{request_id}/status")
def update_request_status_route(
    request: Request,
    request_id: int,
    status_id: int = Form(...),
    csrf_token: str = Form(...),
    db: Session = Depends(get_db),
):
    admin = _require_admin(request, db)
    if isinstance(admin, RedirectResponse):
        return admin
    _verify_csrf(request, csrf_token)

    try:
        set_request_status(db, request_id=request_id, status_id=status_id)
        return _redirect(f"/admin/requests/{request_id}?message=Status+updated")
    except (ValidationError, BusinessRuleError) as exc:
        return _redirect(f"/admin/requests/{request_id}?error={_quote_message(str(exc))}")


@router.post("/requests/{request_id}/delete")
def delete_request_route(request: Request, request_id: int, csrf_token: str = Form(...), db: Session = Depends(get_db)):
    admin = _require_admin(request, db)
    if isinstance(admin, RedirectResponse):
        return admin
    _verify_csrf(request, csrf_token)

    try:
        delete_request_permanently(db, request_id=request_id)
    except BusinessRuleError as exc:
        return _redirect(f"/admin/requests?error={_quote_message(str(exc))}")

    return _redirect("/admin/requests?message=Request+deleted")


@router.get("/requests/{request_id}/files/{answer_id}")
def request_file_download(request: Request, request_id: int, answer_id: int, db: Session = Depends(get_db)):
    admin = _require_admin(request, db)
    if isinstance(admin, RedirectResponse):
        return admin

    request_item = db.get(BeneficiaryRequest, request_id)
    if request_item is None:
        raise HTTPException(status_code=404, detail="Request not found")

    answer = db.get(RequestAnswer, answer_id)
    if answer is None or answer.request_id != request_id or not answer.file_path:
        raise HTTPException(status_code=404, detail="File not found")

    resolved = resolve_stored_file_path(answer.file_path)
    if resolved is None or not resolved.exists() or not resolved.is_file():
        raise HTTPException(status_code=404, detail="File not found")

    if not is_resolved_file_in_request_dir(resolved, request_id):
        raise HTTPException(status_code=404, detail="File not found")

    return FileResponse(path=resolved, filename=answer.original_filename or resolved.name)


@router.post("/requests/{request_id}/message")
def send_request_message_route(
    request: Request,
    request_id: int,
    message_text: str = Form(...),
    csrf_token: str = Form(...),
    db: Session = Depends(get_db),
):
    admin = _require_admin(request, db)
    if isinstance(admin, RedirectResponse):
        return admin
    _verify_csrf(request, csrf_token)

    try:
        req = get_request_details(db, request_id=request_id)
        send_text_message(req.chat_id, message_text)
        return _redirect(f"/admin/requests/{request_id}?message=Message+sent")
    except Exception as exc:
        return _redirect(f"/admin/requests/{request_id}?error={_quote_message(str(exc))}")
