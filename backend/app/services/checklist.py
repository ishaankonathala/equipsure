from typing import Iterable

from app.models.enums import DocumentType

REQUIRED_DOCUMENT_TYPES: tuple = ("INVOICE", "PHOTO")


def missing_required_documents(present_types: Iterable[str]) -> list[str]:
    present = set(present_types)
    return [doc_type for doc_type in REQUIRED_DOCUMENT_TYPES if doc_type not in present]


def checklist_status(present_types: Iterable[str]) -> dict:
    present = sorted(set(present_types))
    missing = missing_required_documents(present_types)
    return {
        "required": list(REQUIRED_DOCUMENT_TYPES),
        "present": present,
        "missing": missing,
        "complete": not missing,
    }
