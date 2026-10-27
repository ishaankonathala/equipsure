import uuid
from datetime import date
from decimal import Decimal

from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.database import get_db
from app.core.security import create_access_token, hash_password
from app.main import app
from app.models import Business, Claim, Equipment, Policy, User


def _user(session, email, role, business_id):
    user = User(
        id=uuid.uuid4(),
        email=email,
        password_hash=hash_password("x"),
        full_name=email,
        role=role,
        business_id=business_id,
        is_active=True,
    )
    session.add(user)
    session.flush()
    return user


def _token(user):
    return create_access_token(
        user_id=str(user.id),
        role=user.role,
        business_id=str(user.business_id) if user.business_id else None,
    )


def _claim(session, business, reference):
    policy = Policy(
        id=uuid.uuid4(),
        policy_number=f"P-{reference}",
        business_id=business.id,
        status="ACTIVE",
        start_date=date(2026, 1, 1),
        end_date=date(2027, 1, 1),
        premium_amount=Decimal("1.00"),
        deductible_amount=Decimal("1.00"),
        coverage_limit=Decimal("1.00"),
    )
    equipment = Equipment(
        id=uuid.uuid4(),
        business_id=business.id,
        category="COOKING",
        description=f"Oven {reference}",
    )
    session.add_all([policy, equipment])
    session.flush()
    claim = Claim(
        id=uuid.uuid4(),
        reference=reference,
        business_id=business.id,
        policy_id=policy.id,
        equipment_id=equipment.id,
        status="SUBMITTED",
        incident_date=date(2026, 10, 1),
        incident_description="x",
        amount_claimed=Decimal("10.00"),
    )
    session.add(claim)
    session.flush()
    return claim


def _client(session, monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "storage_dir", str(tmp_path))

    def override():
        yield session

    app.dependency_overrides[get_db] = override
    return TestClient(app)


def test_policyholder_sees_only_own_business_claims(session, business, monkeypatch, tmp_path):
    other = Business(id=uuid.uuid4(), name="Other Cafe")
    session.add(other)
    session.flush()
    _claim(session, business, "LIST-OWN")
    _claim(session, other, "LIST-OTHER")
    owner = _user(session, "owner-list@example.com", "POLICYHOLDER", business.id)
    client = _client(session, monkeypatch, tmp_path)
    try:
        response = client.get("/api/claims", headers={"Authorization": f"Bearer {_token(owner)}"})
        assert response.status_code == 200
        refs = [c["reference"] for c in response.json()]
        assert "LIST-OWN" in refs
        assert "LIST-OTHER" not in refs
    finally:
        app.dependency_overrides.clear()


def test_ops_sees_all_claims(session, business, monkeypatch, tmp_path):
    other = Business(id=uuid.uuid4(), name="Other Cafe 2")
    session.add(other)
    session.flush()
    _claim(session, business, "LIST-A")
    _claim(session, other, "LIST-B")
    ops = _user(session, "ops-list@example.com", "OPS", None)
    client = _client(session, monkeypatch, tmp_path)
    try:
        response = client.get("/api/claims", headers={"Authorization": f"Bearer {_token(ops)}"})
        assert response.status_code == 200
        refs = [c["reference"] for c in response.json()]
        assert "LIST-A" in refs and "LIST-B" in refs
    finally:
        app.dependency_overrides.clear()


def test_list_requires_authentication(session, monkeypatch, tmp_path):
    client = _client(session, monkeypatch, tmp_path)
    try:
        assert client.get("/api/claims").status_code == 401
    finally:
        app.dependency_overrides.clear()