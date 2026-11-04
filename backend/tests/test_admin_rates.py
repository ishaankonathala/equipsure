from decimal import Decimal
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.core.database import get_db
from app.core.security import create_access_token, hash_password
from app.main import app
from app.models import ClaimEvent, PremiumRate, User
from app.services.premium import calculate_premium

PASSWORD = "admin-rates-test-pw"


@pytest.fixture
def client(session):
    def override_get_db():
        yield session

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


def _make_user(session, email: str, role: str) -> User:
    user = User(
        id=uuid.uuid4(),
        email=email,
        password_hash=hash_password(PASSWORD),
        full_name=f"User {role}",
        role=role,
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


def test_admin_can_list_and_update_rates(session, client):
    admin = _make_user(session, "admin-rates@test.com", "ADMIN")
    token = _token_for(admin)
    headers = {"Authorization": f"Bearer {token}"}

    # List
    response = client.get("/api/admin/rates", headers=headers)
    assert response.status_code == 200
    rates = response.json()
    assert isinstance(rates, list)
    assert len(rates) >= 13

    # Check refrigeration category rate is initially 0.0200
    refrig = next(r for r in rates if r["kind"] == "CATEGORY" and r["code"] == "REFRIGERATION")
    assert Decimal(str(refrig["value"])) == Decimal("0.0200")

    # Count claim_events before update
    events_count_before = session.execute(select(func.count(ClaimEvent.id))).scalar()

    # Update refrigeration rate
    put_res = client.put(
        "/api/admin/rates/CATEGORY/REFRIGERATION",
        headers=headers,
        json={"value": "0.0350"},
    )
    assert put_res.status_code == 200
    updated = put_res.json()
    assert updated["kind"] == "CATEGORY"
    assert updated["code"] == "REFRIGERATION"
    assert Decimal(str(updated["value"])) == Decimal("0.0350")

    # Verify claim_events count has not changed (writes nothing to claim_events)
    events_count_after = session.execute(select(func.count(ClaimEvent.id))).scalar()
    assert events_count_after == events_count_before

    # Verify updated value in database
    db_rate = session.execute(
        select(PremiumRate).where(
            PremiumRate.kind == "CATEGORY",
            PremiumRate.code == "REFRIGERATION",
        )
    ).scalar_one()
    assert Decimal(str(db_rate.value)) == Decimal("0.0350")


def test_ops_gets_403(session, client):
    ops = _make_user(session, "ops-rates@test.com", "OPS")
    token = _token_for(ops)
    headers = {"Authorization": f"Bearer {token}"}

    list_res = client.get("/api/admin/rates", headers=headers)
    assert list_res.status_code == 403

    put_res = client.put(
        "/api/admin/rates/CATEGORY/REFRIGERATION",
        headers=headers,
        json={"value": "0.0250"},
    )
    assert put_res.status_code == 403


def test_unauthenticated_gets_401(client):
    list_res = client.get("/api/admin/rates")
    assert list_res.status_code == 401

    put_res = client.put(
        "/api/admin/rates/CATEGORY/REFRIGERATION",
        json={"value": "0.0250"},
    )
    assert put_res.status_code == 401


def test_negative_value_gets_422(session, client):
    admin = _make_user(session, "admin-neg@test.com", "ADMIN")
    token = _token_for(admin)
    headers = {"Authorization": f"Bearer {token}"}

    put_res = client.put(
        "/api/admin/rates/CATEGORY/REFRIGERATION",
        headers=headers,
        json={"value": "-0.0100"},
    )
    assert put_res.status_code == 422


def test_calculate_premium_with_rates_mapping_matches_defaults(session):
    # Fetch all rates from the table
    all_rates = session.execute(select(PremiumRate)).scalars().all()
    rates_mapping = {(r.kind, r.code): r.value for r in all_rates}

    # Compare default calculation vs table-backed mapping
    default_quote = calculate_premium(
        category="REFRIGERATION",
        sum_insured=Decimal("100000.00"),
        age_years=1,
        cover="BASIC",
    )
    mapped_quote = calculate_premium(
        category="REFRIGERATION",
        sum_insured=Decimal("100000.00"),
        age_years=1,
        cover="BASIC",
        rates=rates_mapping,
    )

    assert default_quote.total == mapped_quote.total
    assert default_quote.lines == mapped_quote.lines

    # Another combination with age charge and cover charge
    default_quote2 = calculate_premium(
        category="COOKING",
        sum_insured=Decimal("50000.00"),
        age_years=4,
        cover="COMPREHENSIVE",
    )
    mapped_quote2 = calculate_premium(
        category="COOKING",
        sum_insured=Decimal("50000.00"),
        age_years=4,
        cover="COMPREHENSIVE",
        rates=rates_mapping,
    )

    assert default_quote2.total == mapped_quote2.total
    assert default_quote2.lines == mapped_quote2.lines

