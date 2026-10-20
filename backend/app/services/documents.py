import hashlib
import secrets
from dataclasses import dataclass

from app.core.config import settings


class DocumentValidationError(Exception):
    pass


@dataclass(frozen=True)
class ValidatedDocument:
    content_type: str
    size_bytes: int
    sha256: str
    storage_name: str


MAGIC_SIGNATURES = {
    "application/pdf": (b"%PDF-",),
    "image/jpeg": (b"\xff\xd8\xff",),
    "image/png": (b"\x89PNG\r\n\x1a\n",),
}


def allowed_types() -> set[str]:
    configured_types = settings.allowed_upload_types.split(",")
    return {
        item.strip()
        for item in configured_types
        if item.strip() in MAGIC_SIGNATURES
    }


def detect_content_type(head: bytes) -> str | None:
    for content_type, signatures in MAGIC_SIGNATURES.items():
        for signature in signatures:
            if head.startswith(signature):
                return content_type
    return None


def new_storage_name() -> str:
    return secrets.token_hex(32)


def validate_upload(data: bytes, declared_content_type: str | None) -> ValidatedDocument:
    # This function receives bytes already read, so the route enforces the size limit while streaming before the full body is read.
    if len(data) == 0:
        raise DocumentValidationError("File is empty")
    if len(data) > settings.max_upload_bytes:
        raise DocumentValidationError("File exceeds the size limit")

    detected = detect_content_type(data[:16])
    if detected is None:
        raise DocumentValidationError("File type is not allowed")
    if detected not in allowed_types():
        raise DocumentValidationError("File type is not allowed")
    if declared_content_type is not None and declared_content_type != detected:
        raise DocumentValidationError("Declared type does not match file contents")

    return ValidatedDocument(
        content_type=detected,
        size_bytes=len(data),
        sha256=hashlib.sha256(data).hexdigest(),
        storage_name=new_storage_name(),
    )
