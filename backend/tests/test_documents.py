import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.models import ClaimDocument


def _sample_document(claim_id, *, storage_name="doc-001.pdf", content_type="application/pdf", size_bytes=1024, sha256=None, document_type="INVOICE"):
    return ClaimDocument(
        id=uuid.uuid4(),
        claim_id=claim_id,
        document_type=document_type,
        original_filename="invoice.pdf",
        storage_name=storage_name,
        content_type=content_type,
        size_bytes=size_bytes,
        sha256=sha256 or ("a" * 64),
    )


def test_document_insert_succeeds(session, claim):
    doc = _sample_document(claim.id, storage_name="invoice-unique-001.pdf")
    session.add(doc)
    session.flush()
    assert doc.id is not None


def test_document_rejects_invalid_type(session, claim):
    with pytest.raises(IntegrityError):
        with session.begin_nested():
            session.add(_sample_document(claim.id, document_type="DRAFT"))
            session.flush()


def test_document_rejects_invalid_content_type(session, claim):
    with pytest.raises(IntegrityError):
        with session.begin_nested():
            session.add(_sample_document(claim.id, content_type="application/x-msdownload"))
            session.flush()


def test_document_rejects_zero_size(session, claim):
    with pytest.raises(IntegrityError):
        with session.begin_nested():
            session.add(_sample_document(claim.id, size_bytes=0))
            session.flush()


def test_document_rejects_size_over_limit(session, claim):
    with pytest.raises(IntegrityError):
        with session.begin_nested():
            session.add(_sample_document(claim.id, size_bytes=10485761))
            session.flush()


def test_document_rejects_bad_sha256_length(session, claim):
    with pytest.raises(IntegrityError):
        with session.begin_nested():
            session.add(_sample_document(claim.id, sha256=("a" * 63)))
            session.flush()


def test_document_rejects_duplicate_storage_name(session, claim):
    session.add(_sample_document(claim.id, storage_name="dup-name.pdf"))
    session.flush()
    with pytest.raises(IntegrityError):
        with session.begin_nested():
            session.add(_sample_document(claim.id, storage_name="dup-name.pdf"))
            session.flush()


def test_document_requires_existing_claim(session):
    with pytest.raises(IntegrityError):
        with session.begin_nested():
            session.add(_sample_document(uuid.uuid4()))
            session.flush()
