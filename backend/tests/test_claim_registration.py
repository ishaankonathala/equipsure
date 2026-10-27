from datetime import date
from decimal import Decimal
import uuid

import pytest
from fastapi import status
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.core.config import settings
from app.core.database import get_db
from app.core.security import create_access_token, hash_password
from app.main import app
from app.models import (
    BillingRecord,
    Business,
    Claim,
    ClaimEvent,
    Equipment,
    Policy,
    PolicyEquipment,
    User,
)
from app.models.enums import BillingStatus, PolicyStatus
from app.services.claims import ClaimRegistrationError, register_claim_for_user


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


def _make_user(session, email: str, role: str, business_id: uuid.UUID | None) -> User:
    user = User(
        id=uuid.uuid4(),
        email=email,
        password_hash=hash_password("test-password"),
        full_name=email,
        role=role,
        business_id=business_id,
        is_active=True,
    )
    session.add(user)
    session.flush()
    return user


def _token_for(user: User) -> str:
    return create_access_token(
        user_id=str(user.id),
        role=user.role,
        business_id=str(user.business_id) if user.business_id else None,
    )


def _setup_eligible_policy(
    session,
    policy: Policy,
    equipment: Equipment,
    *,
    amount_paid: Decimal = Decimal("100.00"),
    due_date: date = date(2026, 2, 1),
) -> BillingRecord:
    session.add(PolicyEquipment(policy_id=policy.id, equipment_id=equipment.id))
    billing = BillingRecord(
        id=uuid.uuid4(),
        policy_id=policy.id,
        period_start=date(2026, 1, 1),
        period_end=date(2027, 1, 1),
        amount_due=Decimal("100.00"),
        amount_paid=amount_paid,
        status=BillingStatus.PAID.value if amount_paid >= Decimal("100.00") else BillingStatus.DUE.value,
        due_date=due_date,
    )
    session.add(billing)
    session.flush()
    return billing


def _claim_count(session) -> int:
    return session.execute(select(func.count()).select_from(Claim)).scalar_one()


def _event_count(session) -> int:
    return session.execute(select(func.count()).select_from(ClaimEvent)).scalar_one()


def test_policyholder_registers_claim_successfully(
    client, session, business, policy, equipment
):
    _setup_eligible_policy(session, policy, equipment)
    owner = _make_user(session, "reg-owner@example.com", "POLICYHOLDER", business.id)

    before_claims = _claim_count(session)
    before_events = _event_count(session)

    response = client.post(
        "/api/claims",
        json={
            "policy_number": policy.policy_number,
            "equipment_id": str(equipment.id),
            "incident_date": "2026-06-15",
            "incident_description": "Commercial espresso boiler pressure valve failed during service.",
            "amount_claimed": "1250.50",
        },
        headers={"Authorization": f"Bearer {_token_for(owner)}"},
    )

    assert response.status_code == status.HTTP_201_CREATED
    body = response.json()
    assert body["reference"].startswith("CLM-")
    assert body["business_id"] == str(business.id)
    assert body["policy_id"] == str(policy.id)
    assert body["equipment_id"] == str(equipment.id)
    assert body["status"] == "SUBMITTED"
    assert body["incident_date"] == "2026-06-15"
    assert body["amount_claimed"] == "1250.50"
    assert body["sources"] == [
        "MOCK_POLICYCENTER",
        "MOCK_POLICYCENTER",
        "MOCK_BILLINGCENTER",
        "MOCK_CLAIMCENTER",
    ]

    assert _claim_count(session) == before_claims + 1
    assert _event_count(session) == before_events + 1

    created_claim = session.get(Claim, uuid.UUID(body["id"]))
    assert created_claim is not None
    assert created_claim.reference == body["reference"]

    event = session.execute(
        select(ClaimEvent).where(ClaimEvent.claim_id == created_claim.id)
    ).scalar_one()
    assert event.old_status is None
    assert event.new_status == "SUBMITTED"
    assert event.source == "POLICYHOLDER"
    assert event.actor_user_id == owner.id

    list_res = client.get(
        "/api/claims",
        headers={"Authorization": f"Bearer {_token_for(owner)}"},
    )
    assert list_res.status_code == status.HTTP_200_OK
    assert any(item["id"] == body["id"] for item in list_res.json())


def test_sequential_registrations_generate_distinct_references(
    client, session, business, policy, equipment
):
    _setup_eligible_policy(session, policy, equipment)
    owner = _make_user(session, "seq-owner@example.com", "POLICYHOLDER", business.id)
    headers = {"Authorization": f"Bearer {_token_for(owner)}"}

    first = client.post(
        "/api/claims",
        json={
            "policy_number": policy.policy_number,
            "equipment_id": str(equipment.id),
            "incident_date": "2026-06-10",
            "incident_description": "First breakdown incident",
            "amount_claimed": "400.00",
        },
        headers=headers,
    )
    second = client.post(
        "/api/claims",
        json={
            "policy_number": policy.policy_number,
            "equipment_id": str(equipment.id),
            "incident_date": "2026-06-12",
            "incident_description": "Second breakdown incident",
            "amount_claimed": "550.00",
        },
        headers=headers,
    )

    assert first.status_code == status.HTTP_201_CREATED
    assert second.status_code == status.HTTP_201_CREATED
    assert first.json()["reference"] != second.json()["reference"]


def test_unknown_policy_rejected_with_422(client, session, business, equipment):
    owner = _make_user(session, "unknown-pol@example.com", "POLICYHOLDER", business.id)
    before_claims = _claim_count(session)
    before_events = _event_count(session)

    response = client.post(
        "/api/claims",
        json={
            "policy_number": "NON-EXISTENT-POL",
            "equipment_id": str(equipment.id),
            "incident_date": "2026-06-15",
            "incident_description": "Compressor failure",
            "amount_claimed": "800.00",
        },
        headers={"Authorization": f"Bearer {_token_for(owner)}"},
    )

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    assert "Policy not found" in response.json()["detail"]
    assert _claim_count(session) == before_claims
    assert _event_count(session) == before_events


def test_inactive_policy_rejected_with_422(
    client, session, business, policy, equipment
):
    policy.status = PolicyStatus.CANCELLED.value
    _setup_eligible_policy(session, policy, equipment)
    owner = _make_user(session, "inactive-pol@example.com", "POLICYHOLDER", business.id)
    before_claims = _claim_count(session)

    response = client.post(
        "/api/claims",
        json={
            "policy_number": policy.policy_number,
            "equipment_id": str(equipment.id),
            "incident_date": "2026-06-15",
            "incident_description": "Grinder motor burnout",
            "amount_claimed": "600.00",
        },
        headers={"Authorization": f"Bearer {_token_for(owner)}"},
    )

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    assert "Policy is not active" in response.json()["detail"]
    assert _claim_count(session) == before_claims


def test_out_of_period_incident_date_rejected_with_422(
    client, session, business, policy, equipment
):
    _setup_eligible_policy(session, policy, equipment)
    owner = _make_user(session, "period-pol@example.com", "POLICYHOLDER", business.id)
    before_claims = _claim_count(session)

    response = client.post(
        "/api/claims",
        json={
            "policy_number": policy.policy_number,
            "equipment_id": str(equipment.id),
            "incident_date": "2027-03-01",
            "incident_description": "Incident after policy end date",
            "amount_claimed": "700.00",
        },
        headers={"Authorization": f"Bearer {_token_for(owner)}"},
    )

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    assert "Incident date is outside the policy period" in response.json()["detail"]
    assert _claim_count(session) == before_claims


def test_uncovered_equipment_rejected_with_422(
    client, session, business, policy, equipment
):
    _setup_eligible_policy(session, policy, equipment)
    uncovered = Equipment(
        id=uuid.uuid4(),
        business_id=business.id,
        category="COOKING",
        description="Uncovered toaster oven",
    )
    session.add(uncovered)
    session.flush()

    owner = _make_user(session, "uncovered-eq@example.com", "POLICYHOLDER", business.id)
    before_claims = _claim_count(session)

    response = client.post(
        "/api/claims",
        json={
            "policy_number": policy.policy_number,
            "equipment_id": str(uncovered.id),
            "incident_date": "2026-06-15",
            "incident_description": "Heating element failed",
            "amount_claimed": "300.00",
        },
        headers={"Authorization": f"Bearer {_token_for(owner)}"},
    )

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    assert "Equipment is not covered by this policy" in response.json()["detail"]
    assert _claim_count(session) == before_claims


def test_overdue_billing_rejected_with_422(
    client, session, business, policy, equipment
):
    _setup_eligible_policy(
        session,
        policy,
        equipment,
        amount_paid=Decimal("0.00"),
        due_date=date(2026, 2, 1),
    )
    owner = _make_user(session, "overdue-owner@example.com", "POLICYHOLDER", business.id)
    before_claims = _claim_count(session)

    response = client.post(
        "/api/claims",
        json={
            "policy_number": policy.policy_number,
            "equipment_id": str(equipment.id),
            "incident_date": "2026-06-15",
            "incident_description": "Refrigeration compressor failure",
            "amount_claimed": "950.00",
        },
        headers={"Authorization": f"Bearer {_token_for(owner)}"},
    )

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    assert "Policy account is overdue" in response.json()["detail"]
    assert _claim_count(session) == before_claims


def test_unauthenticated_and_non_policyholder_roles_rejected(
    client, session, business, policy, equipment
):
    _setup_eligible_policy(session, policy, equipment)
    ops = _make_user(session, "ops-reg@example.com", "OPS", None)
    admin = _make_user(session, "admin-reg@example.com", "ADMIN", None)
    payload = {
        "policy_number": policy.policy_number,
        "equipment_id": str(equipment.id),
        "incident_date": "2026-06-15",
        "incident_description": "Unauthorised role test",
        "amount_claimed": "500.00",
    }

    unauth_res = client.post("/api/claims", json=payload)
    assert unauth_res.status_code == status.HTTP_401_UNAUTHORIZED

    ops_res = client.post(
        "/api/claims",
        json=payload,
        headers={"Authorization": f"Bearer {_token_for(ops)}"},
    )
    assert ops_res.status_code == status.HTTP_403_FORBIDDEN

    admin_res = client.post(
        "/api/claims",
        json=payload,
        headers={"Authorization": f"Bearer {_token_for(admin)}"},
    )
    assert admin_res.status_code == status.HTTP_403_FORBIDDEN


def test_policyholder_cannot_register_against_other_business_policy(
    client, session, business, policy, equipment
):
    _setup_eligible_policy(session, policy, equipment)
    other_business = Business(id=uuid.uuid4(), name="Other Cafe Tenant")
    session.add(other_business)
    session.flush()
    other_owner = _make_user(
        session, "other-tenant@example.com", "POLICYHOLDER", other_business.id
    )
    before_claims = _claim_count(session)

    response = client.post(
        "/api/claims",
        json={
            "policy_number": policy.policy_number,
            "equipment_id": str(equipment.id),
            "incident_date": "2026-06-15",
            "incident_description": "Cross-tenant attempt",
            "amount_claimed": "500.00",
        },
        headers={"Authorization": f"Bearer {_token_for(other_owner)}"},
    )

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    assert response.json()["detail"] == "Policy not found"
    assert _claim_count(session) == before_claims


def test_invalid_inputs_rejected_with_422(
    client, session, business, policy, equipment
):
    _setup_eligible_policy(session, policy, equipment)
    owner = _make_user(session, "invalid-in@example.com", "POLICYHOLDER", business.id)
    headers = {"Authorization": f"Bearer {_token_for(owner)}"}

    zero_amount = client.post(
        "/api/claims",
        json={
            "policy_number": policy.policy_number,
            "equipment_id": str(equipment.id),
            "incident_date": "2026-06-15",
            "incident_description": "Valid description",
            "amount_claimed": "0.00",
        },
        headers=headers,
    )
    assert zero_amount.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    blank_desc = client.post(
        "/api/claims",
        json={
            "policy_number": policy.policy_number,
            "equipment_id": str(equipment.id),
            "incident_date": "2026-06-15",
            "incident_description": "    ",
            "amount_claimed": "250.00",
        },
        headers=headers,
    )
    assert blank_desc.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


def test_duplicate_reference_and_transaction_safety(
    session, business, policy, equipment, claim
):
    _setup_eligible_policy(session, policy, equipment)
    owner = _make_user(session, "dup-ref@example.com", "POLICYHOLDER", business.id)
    before_claims = _claim_count(session)
    before_events = _event_count(session)

    with pytest.raises(ClaimRegistrationError, match="Claim reference already exists"):
        register_claim_for_user(
            session,
            owner,
            policy_number=policy.policy_number,
            equipment_id=equipment.id,
            incident_date=date(2026, 6, 15),
            incident_description="Duplicate reference test",
            amount_claimed=Decimal("300.00"),
            reference=claim.reference,
        )

    assert _claim_count(session) == before_claims
    assert _event_count(session) == before_events


def test_route_rolls_back_claim_if_reference_collision_occurs_at_flush(
    client, session, business, policy, equipment, claim, monkeypatch
):
    _setup_eligible_policy(session, policy, equipment)
    owner = _make_user(session, "rollback-owner@example.com", "POLICYHOLDER", business.id)
    before_claims = _claim_count(session)
    before_events = _event_count(session)

    monkeypatch.setattr(
        "app.services.claims.generate_claim_reference",
        lambda _db: claim.reference,
    )

    response = client.post(
        "/api/claims",
        json={
            "policy_number": policy.policy_number,
            "equipment_id": str(equipment.id),
            "incident_date": "2026-06-15",
            "incident_description": "Simulated race condition collision on reference",
            "amount_claimed": "420.00",
        },
        headers={"Authorization": f"Bearer {_token_for(owner)}"},
    )

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    assert "Claim reference already exists" in response.json()["detail"]
    assert _claim_count(session) == before_claims
    assert _event_count(session) == before_events


def test_registration_options_endpoint_scoped_to_policyholder_business(
    client, session, business, policy, equipment
):
    _setup_eligible_policy(session, policy, equipment)
    other_business = Business(id=uuid.uuid4(), name="Other Options Cafe")
    session.add(other_business)
    session.flush()
    other_eq = Equipment(
        id=uuid.uuid4(),
        business_id=other_business.id,
        category="MACHINERY",
        description="Other business grinder",
    )
    session.add(other_eq)
    session.flush()

    owner = _make_user(session, "opt-owner@example.com", "POLICYHOLDER", business.id)
    ops = _make_user(session, "opt-ops@example.com", "OPS", None)

    res = client.get(
        "/api/claims/options",
        headers={"Authorization": f"Bearer {_token_for(owner)}"},
    )
    assert res.status_code == status.HTTP_200_OK
    data = res.json()
    assert [p["policy_number"] for p in data["policies"]] == [policy.policy_number]
    assert [e["id"] for e in data["equipment"]] == [str(equipment.id)]

    ops_res = client.get(
        "/api/claims/options",
        headers={"Authorization": f"Bearer {_token_for(ops)}"},
    )
    assert ops_res.status_code == status.HTTP_403_FORBIDDEN
