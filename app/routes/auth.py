from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.auth import authenticate_admin
from app.database import get_db
from app.models import Admin


router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=255)


class LoginResponse(BaseModel):
    id: int
    username: str


@router.post("/login", response_model=LoginResponse)
def login(payload: LoginRequest, request: Request, db: Session = Depends(get_db)) -> LoginResponse:
    admin = authenticate_admin(db, payload.username, payload.password)
    if admin is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid username or password")

    request.session["admin_id"] = admin.id
    return LoginResponse(id=admin.id, username=admin.username)


@router.post("/logout")
def logout(request: Request) -> dict[str, str]:
    request.session.clear()
    return {"message": "logged out"}


def get_current_admin(request: Request, db: Session = Depends(get_db)) -> Admin:
    admin_id = request.session.get("admin_id")
    if admin_id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")

    admin = db.get(Admin, admin_id)
    if admin is None or not admin.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")

    return admin


@router.get("/me", response_model=LoginResponse)
def me(current_admin: Admin = Depends(get_current_admin)) -> LoginResponse:
    return LoginResponse(id=current_admin.id, username=current_admin.username)
