from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os
import uuid

from app.config import BASE_DIR, get_settings


MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024
ALLOWED_EXTENSIONS = {"pdf", "jpg", "jpeg", "png"}


class FileStorageError(Exception):
    pass


@dataclass
class StoredFile:
    stored_path: str
    original_filename: str | None
    extension: str
    size: int


def _safe_original_filename(name: str | None) -> str | None:
    if not name:
        return None
    cleaned = name.replace("\\", "/").split("/")[-1].strip()
    return cleaned or None


def _detect_extension_from_bytes(content: bytes) -> str | None:
    if content.startswith(b"%PDF-"):
        return "pdf"
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if content.startswith(b"\xff\xd8\xff"):
        return "jpg"
    return None


def _detect_extension_from_mime(mime_type: str | None) -> str | None:
    if not mime_type:
        return None
    normalized = mime_type.lower().strip()
    mapping = {
        "application/pdf": "pdf",
        "image/jpeg": "jpg",
        "image/jpg": "jpg",
        "image/png": "png",
    }
    return mapping.get(normalized)


def _detect_extension_from_name(filename: str | None) -> str | None:
    if not filename or "." not in filename:
        return None
    ext = filename.rsplit(".", 1)[1].lower().strip()
    return ext if ext in ALLOWED_EXTENSIONS else None


def _choose_extension(content: bytes, mime_type: str | None, filename: str | None) -> str:
    by_content = _detect_extension_from_bytes(content)
    if by_content is not None:
        return by_content

    by_mime = _detect_extension_from_mime(mime_type)
    by_name = _detect_extension_from_name(filename)

    if by_mime is not None:
        return by_mime
    if by_name is not None:
        return by_name

    raise FileStorageError("Unsupported file type. Allowed: PDF, JPG, JPEG, PNG")


def _uploads_root() -> Path:
    root_raw = os.getenv("UPLOADS_DIR") or get_settings().uploads_dir
    root = Path(root_raw)
    if not root.is_absolute():
        root = BASE_DIR / root
    return root


def validate_file(content: bytes, *, mime_type: str | None, filename: str | None, declared_size: int | None = None) -> tuple[str, int]:
    size = len(content)
    if declared_size is not None and declared_size > MAX_FILE_SIZE_BYTES:
        raise FileStorageError("File too large. Maximum size is 10 MB")
    if size > MAX_FILE_SIZE_BYTES:
        raise FileStorageError("File too large. Maximum size is 10 MB")

    ext = _choose_extension(content, mime_type, filename)
    return ext, size


def request_upload_dir(request_id: int) -> Path:
    return _uploads_root() / "requests" / str(request_id)


def is_resolved_file_in_request_dir(resolved: Path, request_id: int) -> bool:
    base = request_upload_dir(request_id).resolve()
    return resolved == base or base in resolved.parents


def store_request_file(
    *,
    request_id: int,
    content: bytes,
    filename: str | None,
    mime_type: str | None,
    declared_size: int | None = None,
) -> StoredFile:
    safe_original = _safe_original_filename(filename)
    ext, size = validate_file(content, mime_type=mime_type, filename=safe_original, declared_size=declared_size)

    request_dir = request_upload_dir(request_id)
    request_dir.mkdir(parents=True, exist_ok=True)

    generated_name = f"{uuid.uuid4().hex}.{ext}"
    file_path = request_dir / generated_name
    file_path.write_bytes(content)

    stored_path = str(file_path.relative_to(BASE_DIR)) if file_path.is_absolute() and BASE_DIR in file_path.parents else str(file_path)
    return StoredFile(stored_path=stored_path, original_filename=safe_original, extension=ext, size=size)


def resolve_stored_file_path(stored_path: str) -> Path | None:
    if not stored_path or stored_path.startswith("bale-file://"):
        return None

    root = _uploads_root().resolve()
    path = Path(stored_path)
    if not path.is_absolute():
        path = BASE_DIR / path

    resolved = path.resolve()
    if resolved != root and root not in resolved.parents:
        return None

    return resolved


def delete_request_files(file_paths: list[str], *, request_id: int) -> None:
    visited_dirs: set[Path] = set()
    for raw_path in file_paths:
        resolved = resolve_stored_file_path(raw_path)
        if resolved is None:
            continue
        try:
            if resolved.exists() and resolved.is_file() and is_resolved_file_in_request_dir(resolved, request_id):
                resolved.unlink()
                visited_dirs.add(resolved.parent)
        except OSError:
            continue

    for directory in sorted(visited_dirs, key=lambda p: len(str(p)), reverse=True):
        try:
            if directory.exists() and not any(directory.iterdir()):
                directory.rmdir()
        except OSError:
            continue
