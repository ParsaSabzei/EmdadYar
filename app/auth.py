import hashlib
import hmac
import secrets

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_session_factory
from app.models import Admin


_PBKDF2_ALGORITHM = "sha256"
_PBKDF2_ITERATIONS = 120_000
_SALT_SIZE = 16


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(_SALT_SIZE)
    password_hash = hashlib.pbkdf2_hmac(
        _PBKDF2_ALGORITHM,
        password.encode("utf-8"),
        salt,
        _PBKDF2_ITERATIONS,
    )
    return f"pbkdf2${_PBKDF2_ALGORITHM}${_PBKDF2_ITERATIONS}${salt.hex()}${password_hash.hex()}"


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        scheme, algorithm, iterations_raw, salt_hex, hash_hex = stored_hash.split("$", 4)
    except ValueError:
        return False

    if scheme != "pbkdf2":
        return False

    try:
        iterations = int(iterations_raw)
        salt = bytes.fromhex(salt_hex)
        expected_hash = bytes.fromhex(hash_hex)
    except ValueError:
        return False

    calculated_hash = hashlib.pbkdf2_hmac(
        algorithm,
        password.encode("utf-8"),
        salt,
        iterations,
    )
    return hmac.compare_digest(calculated_hash, expected_hash)


def authenticate_admin(db: Session, username: str, password: str) -> Admin | None:
    admin = db.scalar(select(Admin).where(Admin.username == username, Admin.is_active.is_(True)))
    if admin is None:
        return None

    if not verify_password(password, admin.password_hash):
        return None

    return admin


def ensure_initial_admin() -> bool:
    settings = get_settings()
    username = settings.initial_admin_username
    password = settings.initial_admin_password

    if not username or not password:
        return False

    session_factory = get_session_factory()
    with session_factory() as db:
        existing_admin = db.scalar(select(Admin).where(Admin.username == username))
        if existing_admin is not None:
            return False

        admin = Admin(username=username, password_hash=hash_password(password), is_active=True)
        db.add(admin)
        db.commit()
        return True
