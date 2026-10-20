import uuid
from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.database import get_db
from app.core.security import create_access_token, hash_password
from app.main import app
from app.models import Business, Claim, ClaimDocument, Equipment, Policy, User
from app.services.document_storage import write_document

PASSWORD = "document-route-password"

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


def _make_user(session, email, role, business_id):
    user = User(
        id=uuid.uuid4(),
        email=email,
        password_hash=hash_password(PASSWORD),
        full_name=email,
        role=role,
        business_id=business_id,
        is_active=True,
    )
    session.add(user)
    session.flush()
    return user


def _token_for(user):
    return create_access_token(
        user_id=str(user.id),
        role=user.role,
        business_id=str(user.business_id) if user.business_id else None,
    )


def _make_claim(session, business, policy, equipment, reference):
    claim = Claim(
        id=uuid.uuid4(),
        reference=reference,
        business_id=business.id,
        policy_id=policy.id,
        equipment_id=equipment.id,
        status="SUBMITTED",
        incident_date=date(2026, 10, 1),
        incident_description="Test incident",
        amount_claimed=Decimal("1200.00"),
    )
    session.add(claim)
    session.flush()
    return claim


@pytest.fixture
def owner_business(session):
    biz = Business(id=uuid.uuid4(), name="Owner Business")
    session.add(biz)
    session.flush()
    return biz


@pytest.fixture
def other_business(session):
    biz = Business(id=uuid.uuid4(), name="Other Business")
    session.add(biz)
    session.flush()
    return biz


@pytest.fixture
def owner_policy(session, owner_business):
    policy = Policy(
        id=uuid.uuid4(),
        policy_number="DOC-OWN-1",
        business_id=owner_business.id,
        status="ACTIVE",
        start_date=date(2026, 1, 1),
        end_date=date(2027, 1, 1),
        premium_amount=Decimal("100.00"),
        deductible_amount=Decimal("500.00"),
        coverage_limit=Decimal("50000.00"),
    )
    session.add(policy)
    session.flush()
    return policy


@pytest.fixture
def owner_equipment(session, owner_business):
    eq = Equipment(
        id=uuid.uuid4(),
        business_id=owner_business.id,
        category="REFRIGERATION",
        description="Owner fridge",
    )
    session.add(eq)
    session.flush()
    return eq


@pytest.fixture
def owner_claim(session, owner_business, owner_policy, owner_equipment):
    return _make_claim(session, owner_business, owner_policy, owner_equipment, "DOC-000001")


@pytest.fixture
def other_claim(session, other_business):
    policy = Policy(
        id=uuid.uuid4(),
        policy_number="DOC-OTH-1",
        business_id=other_business.id,
        status="ACTIVE",
        start_date=date(2026, 1, 1),
        end_date=date(2027, 1, 1),
        premium_amount=Decimal("100.00"),
        deductible_amount=Decimal("500.00"),
        coverage_limit=Decimal("50000.00"),
    )
    eq = Equipment(
        id=uuid.uuid4(),
        business_id=other_business.id,
        category="COOKING",
        description="Other oven",
    )
    session.add_all([policy, eq])
    session.flush()
    return _make_claim(session, other_business, policy, eq, "DOC-000002")


@pytest.fixture
def owner_user(session, owner_business):
    return _make_user(session, "owner@doc.example", "POLICYHOLDER", owner_business.id)


@pytest.fixture
def ops_user(session):
    return _make_user(session, "ops@doc.example", "OPS", None)


def test_policyholder_uploads_pdf_to_own_claim(client, owner_user, owner_claim):
    response = client.post(
        f"/api/claims/{owner_claim.id}/documents",
        files={"file": ("invoice.pdf", PDF_BYTES, "application/pdf")},
        data={"document_type": "INVOICE"},
        headers={"Authorization": f"Bearer {_token_for(owner_user)}"},
    )
    assert response.status_code == 201
    payload = response.json()
    assert payload["document_type"] == "INVOICE"
    assert payload["content_type"] == "application/pdf"
    assert payload["claim_id"] == str(owner_claim.id)
    assert len(payload["sha256"]) == 64


def test_policyholder_upload_to_other_business_claim_returns_404(client, owner_user, other_claim):
    response = client.post(
        f"/api/claims/{other_claim.id}/documents",
        files={"file": ("invoice.pdf", PDF_BYTES, "application/pdf")},
        data={"document_type": "INVOICE"},
        headers={"Authorization": f"Bearer {_token_for(owner_user)}"},
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "Claim not found"


def test_ops_can_upload_to_any_claim(client, ops_user, other_claim):
    response = client.post(
        f"/api/claims/{other_claim.id}/documents",
        files={"file": ("report.png", PNG_BYTES, "image/png")},
        data={"document_type": "PHOTO"},
        headers={"Authorization": f"Bearer {_token_for(ops_user)}"},
    )
    assert response.status_code == 201
    assert response.json()["document_type"] == "PHOTO"
    assert response.json()["content_type"] == "image/png"


def test_upload_rejects_unknown_document_type(client, owner_user, owner_claim):
    response = client.post(
        f"/api/claims/{owner_claim.id}/documents",
        files={"file": ("invoice.pdf", PDF_BYTES, "application/pdf")},
        data={"document_type": "DRAFT"},
        headers={"Authorization": f"Bearer {_token_for(owner_user)}"},
    )
    assert response.status_code == 422
    assert response.json()["detail"] == "Unknown document type"


def test_upload_rejects_renamed_executable(client, owner_user, owner_claim):
    response = client.post(
        f"/api/claims/{owner_claim.id}/documents",
        files={"file": ("bad.pdf", b"MZ\x90\x00" + b"0" * 100, "application/pdf")},
        data={"document_type": "INVOICE"},
        headers={"Authorization": f"Bearer {_token_for(owner_user)}"},
    )
    assert response.status_code == 422
    assert "not allowed" in response.json()["detail"]


def test_upload_rejects_oversize_with_413(client, owner_user, owner_claim, monkeypatch):
    monkeypatch.setattr(settings, "max_upload_bytes", 100)
    response = client.post(
        f"/api/claims/{owner_claim.id}/documents",
        files={"file": ("invoice.pdf", b"0" * 200, "application/pdf")},
        data={"document_type": "INVOICE"},
        headers={"Authorization": f"Bearer {_token_for(owner_user)}"},
    )
    assert response.status_code == 413
    assert response.json()["detail"] == "File exceeds the size limit"


def test_download_returns_uploaded_bytes(client, owner_user, owner_claim):
    upload = client.post(
        f"/api/claims/{owner_claim.id}/documents",
        files={"file": ("invoice.pdf", PDF_BYTES, "application/pdf")},
        data={"document_type": "INVOICE"},
        headers={"Authorization": f"Bearer {_token_for(owner_user)}"},
    )
    payload = upload.json()
    response = client.get(
        f"/api/claims/{owner_claim.id}/documents/{payload['id']}",
        headers={"Authorization": f"Bearer {_token_for(owner_user)}"},
    )
    assert response.status_code == 200
    assert response.content == PDF_BYTES
    assert response.headers["content-type"].startswith("application/pdf")
    assert "invoice.pdf" in response.headers["content-disposition"]


def test_download_other_business_returns_404(client, owner_user, other_claim, ops_user):
    upload = client.post(
        f"/api/claims/{other_claim.id}/documents",
        files={"file": ("photo.png", PNG_BYTES, "image/png")},
        data={"document_type": "PHOTO"},
        headers={"Authorization": f"Bearer {_token_for(ops_user)}"},
    )
    doc_id = upload.json()["id"]
    response = client.get(
        f"/api/claims/{other_claim.id}/documents/{doc_id}",
        headers={"Authorization": f"Bearer {_token_for(owner_user)}"},
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "Claim not found"


def test_download_missing_file_returns_404(client, owner_user, owner_claim, session):
    doc = ClaimDocument(
        id=uuid.uuid4(),
        claim_id=owner_claim.id,
        document_type="INVOICE",
        original_filename="missing.pdf",
        storage_name="0" * 64,
        content_type="application/pdf",
        size_bytes=123,
        sha256="a" * 64,
    )
    session.add(doc)
    session.flush()
    response = client.get(
        f"/api/claims/{owner_claim.id}/documents/{doc.id}",
        headers={"Authorization": f"Bearer {_token_for(owner_user)}"},
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "Document file not found"


def test_storage_name_rejects_path_traversal():
    with pytest.raises(ValueError):
        write_document("../evil", b"x")
