import uuid
from datetime import date
from decimal import Decimal

import pytest
from fastapi import status
from fastapi.testclient import TestClient

from app.core.database import get_db
from app.core.security import create_access_token, hash_password
from app.main import app
from app.models import Business, Claim, ClaimDocument, Equipment, Policy, User
from app.models.enums import DocumentType
from app.services.checklist import REQUIRED_DOCUMENT_TYPES, checklist_status, missing_required_documents


@pytest.fixture
def client(session):
    def override_get_db():
        yield session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def db_session(session):
    return session


def _make_business(session, name):
    business = Business(id=uuid.uuid4(), name=name)
    session.add(business)
    session.flush()
    return business


def _make_user(session, business, email, role="POLICYHOLDER"):
    user = User(
        id=uuid.uuid4(),
        email=email,
        password_hash=hash_password("checklist-password"),
        full_name=email,
        role=role,
        business_id=business.id,
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


def _make_policy(session, business):
    policy = Policy(
        id=uuid.uuid4(),
        policy_number=f"CHK-{uuid.uuid4().hex[:8].upper()}",
        business_id=business.id,
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


def _make_equipment(session, business):
    equipment = Equipment(
        id=uuid.uuid4(),
        business_id=business.id,
        category="REFRIGERATION",
        description="Checklist equipment",
    )
    session.add(equipment)
    session.flush()
    return equipment


def _make_claim(session, business, policy, equipment, reference):
    claim = Claim(
        id=uuid.uuid4(),
        reference=reference,
        business_id=business.id,
        policy_id=policy.id,
        equipment_id=equipment.id,
        status="SUBMITTED",
        incident_date=date(2026, 10, 1),
        incident_description="Checklist test claim",
        amount_claimed=Decimal("1200.00"),
    )
    session.add(claim)
    session.flush()
    return claim


def test_missing_required_documents_returns_required_missing_in_order() -> None:
    assert missing_required_documents([]) == list(REQUIRED_DOCUMENT_TYPES)
    assert missing_required_documents(["PHOTO"]) == ["INVOICE"]
    assert missing_required_documents(["INVOICE", "PHOTO"]) == []
    assert missing_required_documents(["INVOICE", "OTHER"]) == ["PHOTO"]


def test_checklist_status_reports_required_present_missing_and_complete() -> None:
    assert checklist_status([]) == {
        "required": list(REQUIRED_DOCUMENT_TYPES),
        "present": [],
        "missing": list(REQUIRED_DOCUMENT_TYPES),
        "complete": False,
    }
    assert checklist_status(["INVOICE"]) == {
        "required": list(REQUIRED_DOCUMENT_TYPES),
        "present": ["INVOICE"],
        "missing": ["PHOTO"],
        "complete": False,
    }
    assert checklist_status(["INVOICE", "PHOTO"]) == {
        "required": list(REQUIRED_DOCUMENT_TYPES),
        "present": ["INVOICE", "PHOTO"],
        "missing": [],
        "complete": True,
    }
    assert checklist_status(["INVOICE", "PHOTO", "OTHER"])["complete"] is True
    assert checklist_status(["INVOICE", "INVOICE"])["present"] == ["INVOICE"]

def test_claim_checklist_route_returns_incomplete_status_for_new_claim(client, db_session):
    business = _make_business(db_session, "Checklist Business")
    user = _make_user(db_session, business, "owner@checklist.example")
    policy = _make_policy(db_session, business)
    equipment = _make_equipment(db_session, business)
    claim = _make_claim(db_session, business, policy, equipment, "CHK-000001")

    response = client.get(
        f"/api/claims/{claim.id}/checklist",
        headers={"Authorization": f"Bearer {_token_for(user)}"},
    )

    assert response.status_code == status.HTTP_200_OK
    assert response.json() == {
        "required": ["INVOICE", "PHOTO"],
        "present": [],
        "missing": ["INVOICE", "PHOTO"],
        "complete": False,
    }


def test_claim_checklist_route_returns_complete_status_when_documents_are_present(client, db_session):
    business = _make_business(db_session, "Checklist Business 2")
    user = _make_user(db_session, business, "owner2@checklist.example")
    policy = _make_policy(db_session, business)
    equipment = _make_equipment(db_session, business)
    claim = _make_claim(db_session, business, policy, equipment, "CHK-000002")
    db_session.add_all(
        [
            ClaimDocument(
                id=uuid.uuid4(),
                claim_id=claim.id,
                document_type=DocumentType.INVOICE,
                storage_name="a" * 64,
                original_filename="invoice.pdf",
                content_type="application/pdf",
                size_bytes=100,
                sha256="b" * 64,
            ),
            ClaimDocument(
                id=uuid.uuid4(),
                claim_id=claim.id,
                document_type=DocumentType.PHOTO,
                storage_name="c" * 64,
                original_filename="photo.jpg",
                content_type="image/jpeg",
                size_bytes=200,
                sha256="d" * 64,
            ),
        ]
    )
    db_session.commit()

    response = client.get(
        f"/api/claims/{claim.id}/checklist",
        headers={"Authorization": f"Bearer {_token_for(user)}"},
    )

    assert response.status_code == status.HTTP_200_OK
    assert response.json() == {
        "required": ["INVOICE", "PHOTO"],
        "present": ["INVOICE", "PHOTO"],
        "missing": [],
        "complete": True,
    }


def test_claim_checklist_route_404s_for_claim_from_other_business(client, db_session):
    owner_business = _make_business(db_session, "Owner Business")
    other_business = _make_business(db_session, "Other Business")
    owner = _make_user(db_session, owner_business, "owner@cross.example")
    other_user = _make_user(db_session, other_business, "other@cross.example")
    owner_policy = _make_policy(db_session, owner_business)
    owner_equipment = _make_equipment(db_session, owner_business)
    claim = _make_claim(db_session, owner_business, owner_policy, owner_equipment, "CHK-000003")

    response = client.get(
        f"/api/claims/{claim.id}/checklist",
        headers={"Authorization": f"Bearer {_token_for(other_user)}"},
    )

    assert response.status_code == status.HTTP_404_NOT_FOUND
