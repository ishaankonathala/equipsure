import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.core.config import settings
from app.core.database import get_db
from app.core.security import create_access_token, hash_password
from app.main import app
from app.models import ClaimDocument, ClaimEvent, User

PDF_BYTES = b"%PDF-1.4\n" + b"0" * 100
PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"0" * 100


@pytest.fixture
def client(session):
    def override_get_db():
        yield session

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def redirect_storage(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "storage_dir", str(tmp_path))


def _make_owner(session, business):
    owner = User(
        id=uuid.uuid4(),
        email=f"owner-{uuid.uuid4().hex}@system.example",
        password_hash=hash_password("system-transition-password"),
        full_name="System Transition Owner",
        role="POLICYHOLDER",
        business_id=business.id,
        is_active=True,
    )
    session.add(owner)
    session.flush()
    return owner


def _token_for(user):
    return create_access_token(
        user_id=str(user.id),
        role=user.role,
        business_id=str(user.business_id) if user.business_id else None,
    )


def _event_count(session, claim):
    return session.execute(
        select(func.count())
        .select_from(ClaimEvent)
        .where(ClaimEvent.claim_id == claim.id)
    ).scalar_one()


def _upload(client, claim, owner, filename, content, content_type, document_type):
    return client.post(
        f"/api/claims/{claim.id}/documents",
        files={"file": (filename, content, content_type)},
        data={"document_type": document_type},
        headers={"Authorization": f"Bearer {_token_for(owner)}"},
    )


def test_upload_of_invoice_only_moves_to_documents_required(
    client, session, business, claim
):
    owner = _make_owner(session, business)
    claim.status = "UNDER_VERIFICATION"
    session.flush()

    response = _upload(
        client, claim, owner, "invoice.pdf", PDF_BYTES, "application/pdf", "INVOICE"
    )

    assert response.status_code == 201
    session.refresh(claim)
    assert claim.status == "DOCUMENTS_REQUIRED"
    assert _event_count(session, claim) == 1
    event = session.execute(
        select(ClaimEvent).where(
            ClaimEvent.claim_id == claim.id,
            ClaimEvent.source == "SYSTEM",
        )
    ).scalar_one()
    assert event.new_status == "DOCUMENTS_REQUIRED"
    assert event.source == "SYSTEM"


def test_upload_of_both_documents_moves_to_under_verification(
    client, session, business, claim
):
    owner = _make_owner(session, business)
    claim.status = "UNDER_VERIFICATION"
    session.flush()

    invoice_response = _upload(
        client, claim, owner, "invoice.pdf", PDF_BYTES, "application/pdf", "INVOICE"
    )
    photo_response = _upload(
        client, claim, owner, "photo.png", PNG_BYTES, "image/png", "PHOTO"
    )

    assert invoice_response.status_code == 201
    assert photo_response.status_code == 201
    session.refresh(claim)
    assert claim.status == "UNDER_VERIFICATION"


def test_submitted_claim_is_not_moved(client, session, business, claim):
    owner = _make_owner(session, business)

    response = _upload(
        client, claim, owner, "invoice.pdf", PDF_BYTES, "application/pdf", "INVOICE"
    )

    assert response.status_code == 201
    session.refresh(claim)
    assert claim.status == "SUBMITTED"
    assert _event_count(session, claim) == 0


def test_upload_survives_failed_status_move(client, session, business, claim):
    owner = _make_owner(session, business)
    claim.status = "APPROVED"
    session.flush()

    response = _upload(
        client, claim, owner, "invoice.pdf", PDF_BYTES, "application/pdf", "INVOICE"
    )

    assert response.status_code == 201
    assert session.execute(
        select(func.count())
        .select_from(ClaimDocument)
        .where(ClaimDocument.claim_id == claim.id)
    ).scalar_one() == 1