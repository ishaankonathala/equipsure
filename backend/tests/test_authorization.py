import uuid
from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.core.database import get_db
from app.core.security import create_access_token, hash_password
from app.main import app
from app.models import Business, Claim, Equipment, Policy, User

PASSWORD = "authz-test-password"


@pytest.fixture
def client(session):
    def override_get_db():
        yield session

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


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
        incident_description="Fridge stopped cooling",
        amount_claimed=Decimal("1200.00"),
    )
    session.add(claim)
    session.flush()
    return claim


@pytest.fixture
def owner_business(session):
    biz = Business(id=uuid.uuid4(), name="Owner Cafe")
    session.add(biz)
    session.flush()
    return biz


@pytest.fixture
def other_business(session):
    biz = Business(id=uuid.uuid4(), name="Other Cafe")
    session.add(biz)
    session.flush()
    return biz


@pytest.fixture
def owner_policy(session, owner_business):
    pol = Policy(
        id=uuid.uuid4(), policy_number="AUTHZ-OWN-1", business_id=owner_business.id,
        status="ACTIVE", start_date=date(2026, 1, 1), end_date=date(2027, 1, 1),
        premium_amount=Decimal("100.00"), deductible_amount=Decimal("500.00"),
        coverage_limit=Decimal("50000.00"),
    )
    session.add(pol)
    session.flush()
    return pol


@pytest.fixture
def owner_equipment(session, owner_business):
    eq = Equipment(
        id=uuid.uuid4(), business_id=owner_business.id,
        category="REFRIGERATION", description="Owner fridge",
    )
    session.add(eq)
    session.flush()
    return eq


@pytest.fixture
def owner_claim(session, owner_business, owner_policy, owner_equipment):
    return _make_claim(session, owner_business, owner_policy, owner_equipment, "AUTHZ-000001")


@pytest.fixture
def other_claim(session, other_business):
    pol = Policy(
        id=uuid.uuid4(), policy_number="AUTHZ-OTH-1", business_id=other_business.id,
        status="ACTIVE", start_date=date(2026, 1, 1), end_date=date(2027, 1, 1),
        premium_amount=Decimal("100.00"), deductible_amount=Decimal("500.00"),
        coverage_limit=Decimal("50000.00"),
    )
    eq = Equipment(
        id=uuid.uuid4(), business_id=other_business.id,
        category="COOKING", description="Other oven",
    )
    session.add_all([pol, eq])
    session.flush()
    return _make_claim(session, other_business, pol, eq, "AUTHZ-000002")


@pytest.fixture
def owner_user(session, owner_business):
    return _make_user(session, "owner@authz.example", "POLICYHOLDER", owner_business.id)


@pytest.fixture
def ops_user(session):
    return _make_user(session, "ops@authz.example", "OPS", None)


def test_policyholder_reads_own_claim(client, owner_user, owner_claim):
    response = client.get(
        f"/api/claims/{owner_claim.id}",
        headers={"Authorization": f"Bearer {_token_for(owner_user)}"},
    )
    assert response.status_code == 200
    assert response.json()["reference"] == "AUTHZ-000001"


def test_policyholder_cannot_read_other_business_claim(client, owner_user, other_claim):
    response = client.get(
        f"/api/claims/{other_claim.id}",
        headers={"Authorization": f"Bearer {_token_for(owner_user)}"},
    )
    assert response.status_code == 404


def test_missing_claim_returns_404(client, owner_user):
    response = client.get(
        f"/api/claims/{uuid.uuid4()}",
        headers={"Authorization": f"Bearer {_token_for(owner_user)}"},
    )
    assert response.status_code == 404


def test_ops_user_reads_any_claim(client, ops_user, other_claim):
    response = client.get(
        f"/api/claims/{other_claim.id}",
        headers={"Authorization": f"Bearer {_token_for(ops_user)}"},
    )
    assert response.status_code == 200


def test_claim_request_without_token_returns_401(client, owner_claim):
    response = client.get(f"/api/claims/{owner_claim.id}")
    assert response.status_code == 401


def test_deactivated_user_loses_access_with_valid_token(client, session, owner_user, owner_claim):
    token = _token_for(owner_user)
    owner_user.is_active = False
    session.flush()
    response = client.get(
        f"/api/claims/{owner_claim.id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 401
