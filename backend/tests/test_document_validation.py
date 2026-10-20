import pytest

from app.core.config import settings
from app.services.documents import (
    DocumentValidationError,
    allowed_types,
    detect_content_type,
    new_storage_name,
    validate_upload,
)

PDF_BYTES = b"%PDF-1.4\n" + b"0" * 100
JPEG_BYTES = b"\xff\xd8\xff\xe0" + b"0" * 100
PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"0" * 100


def test_accepts_pdf():
    result = validate_upload(PDF_BYTES, "application/pdf")
    assert result.content_type == "application/pdf"
    assert result.size_bytes == len(PDF_BYTES)
    assert len(result.sha256) == 64


def test_accepts_jpeg_without_declared_type():
    result = validate_upload(JPEG_BYTES, None)
    assert result.content_type == "image/jpeg"


def test_accepts_png():
    result = validate_upload(PNG_BYTES, "image/png")
    assert result.content_type == "image/png"


def test_rejects_empty_file():
    with pytest.raises(DocumentValidationError, match="empty"):
        validate_upload(b"", None)


def test_rejects_renamed_executable():
    with pytest.raises(DocumentValidationError, match="not allowed"):
        validate_upload(b"MZ\x90\x00" + b"0" * 100, "application/pdf")


def test_rejects_declared_type_mismatch():
    with pytest.raises(DocumentValidationError, match="does not match"):
        validate_upload(PNG_BYTES, "application/pdf")


def test_rejects_over_size_limit(monkeypatch):
    monkeypatch.setattr(settings, "max_upload_bytes", 50)
    with pytest.raises(DocumentValidationError, match="size limit"):
        validate_upload(PDF_BYTES, None)


def test_rejects_type_not_in_allowed_list(monkeypatch):
    monkeypatch.setattr(settings, "allowed_upload_types", "image/jpeg")
    with pytest.raises(DocumentValidationError, match="not allowed"):
        validate_upload(PDF_BYTES, None)


def test_allowed_types_ignores_unknown_entries(monkeypatch):
    monkeypatch.setattr(settings, "allowed_upload_types", "application/pdf, text/html ,image/png")
    assert allowed_types() == {"application/pdf", "image/png"}


def test_storage_names_are_unique_and_64_hex():
    names = {new_storage_name() for _ in range(50)}
    assert len(names) == 50
    assert all(len(name) == 64 for name in names)
    assert all(set(name) <= set("0123456789abcdef") for name in names)
