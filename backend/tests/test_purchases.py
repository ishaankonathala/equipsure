from datetime import date
from decimal import Decimal
import re
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.database import get_db
from app.core.security import create_access_token, hash_password
from app.main import app
from app.models import (
    BillingRecord,
    Business,
    Equipment,
    Policy,
    PolicyEquipment,
    PremiumQuote,
    User,
)
from app.models.enums import BillingStatus, PolicyStatus

PASSWORD = "test-purchases-password"
POLICY_NUM_PATTERN = re.compile(r"^EQP-[0-9A-F]{8}$")
SIM_PAY_PATTERN = re.compile(r"^SIM-PAY-[0-9A-F]{10}$")


@pytest.fixture
def client(session):
    def override_get_db():
        yield session

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


def _make_business(session, name: str = "Test Bakery") -> Business:
    biz = Business(
        id=uuid.uuid4(),
        name=name,
    )
    session.add(biz)
    session.flush()
    return biz


def _make_user(session, email: str, role: str, business: Business | None = None) -> User:
    user = User(
        id=uuid.uuid4(),
        email=email,
        password_hash=hash_password(PASSWORD),
        full_name=f"User {role}",
        role=role,
        business_id=business.id if business else None,
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


def test_quote_then_purchase_creates_policy_equipment_and_billing(session, client):
    business = _make_business(session, "Sunny Cafe")
    customer = _make_user(session, "sunny.owner@example.com", "POLICYHOLDER", business)
    headers = {"Authorization": f"Bearer {_token_for(customer)}"}

    # 1. Create quote
    quote_payload = {
        "equipment_category": "REFRIGERATION",
        "equipment_description": "Commercial Walk-in Chiller",
        "sum_insured": "50000.00",
        "age_years": 1,
        "cover": "BASIC",
    }
    res_quote = client.post("/api/quotes", headers=headers, json=quote_payload)
    assert res_quote.status_code == 201
    quote_data = res_quote.json()
    assert quote_data["status"] == "OPEN"
    assert Decimal(str(quote_data["total"])) > Decimal("0")
    assert len(quote_data["lines"]) == 4
    quote_id = quote_data["id"]

    # 2. Purchase quote
    res_purchase = client.post(f"/api/quotes/{quote_id}/purchase", headers=headers)
    assert res_purchase.status_code == 200
    purchase_data = res_purchase.json()

    policy_number = purchase_data["policy_number"]
    assert POLICY_NUM_PATTERN.match(policy_number), f"Unexpected policy number format: {policy_number}"

    payment_ref = purchase_data["payment_reference"]
    assert SIM_PAY_PATTERN.match(payment_ref), f"Unexpected payment reference format: {payment_ref}"
    assert purchase_data.get("simulated") is True

    # 3. Verify database state
    policy_id = uuid.UUID(purchase_data["policy_id"])
    policy = session.get(Policy, policy_id)
    assert policy is not None
    assert policy.policy_number == policy_number
    assert policy.status == PolicyStatus.ACTIVE.value
    assert policy.start_date == date.today()
    assert policy.end_date == date.today() + date.resolution * 365
    assert policy.premium_amount == Decimal(str(quote_data["total"]))
    assert policy.deductible_amount == Decimal("500.00")
    assert policy.coverage_limit == Decimal("50000.00")
    assert policy.business_id == business.id

    # Verify equipment and link
    links = session.execute(
        select(PolicyEquipment).where(PolicyEquipment.policy_id == policy.id)
    ).scalars().all()
    assert len(links) == 1
    equipment = session.get(Equipment, links[0].equipment_id)
    assert equipment is not None
    assert equipment.category == "REFRIGERATION"
    assert equipment.description == "Commercial Walk-in Chiller"
    assert equipment.business_id == business.id

    # Verify billing record
    billing = session.execute(
        select(BillingRecord).where(BillingRecord.policy_id == policy.id)
    ).scalar_one()
    assert billing.status == BillingStatus.PAID.value
    assert billing.amount_due == policy.premium_amount
    assert billing.amount_paid == policy.premium_amount
    assert billing.period_start == policy.start_date
    assert billing.period_end == policy.end_date

    # Verify quote status updated
    updated_quote = session.get(PremiumQuote, uuid.UUID(quote_id))
    assert updated_quote.status == "PURCHASED"
    assert updated_quote.policy_id == policy.id


def test_buying_twice_returns_422(session, client):
    business = _make_business(session, "Bake Shop")
    customer = _make_user(session, "baker@example.com", "POLICYHOLDER", business)
    headers = {"Authorization": f"Bearer {_token_for(customer)}"}

    res_quote = client.post(
        "/api/quotes",
        headers=headers,
        json={
            "equipment_category": "COOKING",
            "equipment_description": "Pizza Oven",
            "sum_insured": "20000.00",
            "age_years": 2,
            "cover": "STANDARD",
        },
    )
    assert res_quote.status_code == 201
    quote_id = res_quote.json()["id"]

    # First purchase succeeds
    first = client.post(f"/api/quotes/{quote_id}/purchase", headers=headers)
    assert first.status_code == 200

    # Second purchase must return 422
    second = client.post(f"/api/quotes/{quote_id}/purchase", headers=headers)
    assert second.status_code == 422


def test_another_business_quote_returns_404(session, client):
    biz_a = _make_business(session, "Business A")
    biz_b = _make_business(session, "Business B")
    user_a = _make_user(session, "user.a@example.com", "POLICYHOLDER", biz_a)
    user_b = _make_user(session, "user.b@example.com", "POLICYHOLDER", biz_b)

    # User A creates a quote
    res_quote = client.post(
        "/api/quotes",
        headers={"Authorization": f"Bearer {_token_for(user_a)}"},
        json={
            "equipment_category": "MACHINERY",
            "equipment_description": "Packaging Line",
            "sum_insured": "80000.00",
            "age_years": 3,
            "cover": "COMPREHENSIVE",
        },
    )
    assert res_quote.status_code == 201
    quote_id = res_quote.json()["id"]

    # User B attempts to purchase User A's quote -> 404
    res_b = client.post(
        f"/api/quotes/{quote_id}/purchase",
        headers={"Authorization": f"Bearer {_token_for(user_b)}"},
    )
    assert res_b.status_code == 404


def test_ops_cannot_purchase_returns_403(session, client):
    business = _make_business(session, "Clean Dry Cleaners")
    customer = _make_user(session, "cleaner@example.com", "POLICYHOLDER", business)
    ops_user = _make_user(session, "ops.officer@example.com", "OPS")

    res_quote = client.post(
        "/api/quotes",
        headers={"Authorization": f"Bearer {_token_for(customer)}"},
        json={
            "equipment_category": "ELECTRICAL",
            "equipment_description": "Power Generator",
            "sum_insured": "15000.00",
            "age_years": 0,
            "cover": "BASIC",
        },
    )
    assert res_quote.status_code == 201
    quote_id = res_quote.json()["id"]

    # OPS tries to purchase -> 403
    res_ops = client.post(
        f"/api/quotes/{quote_id}/purchase",
        headers={"Authorization": f"Bearer {_token_for(ops_user)}"},
    )
    assert res_ops.status_code == 403


def test_policy_numbers_are_unique_across_two_purchases(session, client):
    business = _make_business(session, "Dual Equipment Co")
    customer = _make_user(session, "dual@example.com", "POLICYHOLDER", business)
    headers = {"Authorization": f"Bearer {_token_for(customer)}"}

    res1 = client.post(
        "/api/quotes",
        headers=headers,
        json={
            "equipment_category": "HVAC",
            "equipment_description": "Rooftop AC Unit",
            "sum_insured": "25000.00",
            "age_years": 1,
            "cover": "STANDARD",
        },
    )
    assert res1.status_code == 201
    q1_id = res1.json()["id"]

    res2 = client.post(
        "/api/quotes",
        headers=headers,
        json={
            "equipment_category": "OTHER",
            "equipment_description": "Security System",
            "sum_insured": "10000.00",
            "age_years": 1,
            "cover": "BASIC",
        },
    )
    assert res2.status_code == 201
    q2_id = res2.json()["id"]

    p1 = client.post(f"/api/quotes/{q1_id}/purchase", headers=headers)
    p2 = client.post(f"/api/quotes/{q2_id}/purchase", headers=headers)
    assert p1.status_code == 200
    assert p2.status_code == 200

    num1 = p1.json()["policy_number"]
    num2 = p2.json()["policy_number"]

    assert POLICY_NUM_PATTERN.match(num1)
    assert POLICY_NUM_PATTERN.match(num2)
    assert num1 != num2
