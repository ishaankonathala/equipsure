import uuid

import pytest
from fastapi.testclient import TestClient

from app.core.database import get_db
from app.core.security import create_access_token, hash_password
from app.main import app
from app.models import Business, User

PASSWORD = "test-compare-password"


@pytest.fixture
def client(session):
    def override_get_db():
        yield session

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


def _make_business(session, name: str = "Compare Biz") -> Business:
    biz = Business(id=uuid.uuid4(), name=name)
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


def _create_quote(client, token: str, category: str, sum_insured: str, age: int, cover: str) -> dict:
    headers = {"Authorization": f"Bearer {token}"}
    res = client.post(
        "/api/quotes",
        headers=headers,
        json={
            "equipment_category": category,
            "equipment_description": f"{category} unit",
            "sum_insured": sum_insured,
            "age_years": age,
            "cover": cover,
        },
    )
    assert res.status_code == 201
    return res.json()


def test_compare_requires_two_or_three_ids_otherwise_422(session, client):
    biz = _make_business(session, "Biz Val")
    user = _make_user(session, "val@example.com", "POLICYHOLDER", biz)
    token = _token_for(user)
    headers = {"Authorization": f"Bearer {token}"}

    q1 = _create_quote(client, token, "REFRIGERATION", "50000.00", 1, "BASIC")
    q2 = _create_quote(client, token, "COOKING", "30000.00", 2, "STANDARD")
    q3 = _create_quote(client, token, "MACHINERY", "70000.00", 4, "COMPREHENSIVE")
    q4 = _create_quote(client, token, "HVAC", "25000.00", 0, "BASIC")

    # 0 IDs -> 422
    res0 = client.get("/api/quotes/compare", headers=headers)
    assert res0.status_code == 422

    # 1 ID -> 422
    res1 = client.get(f"/api/quotes/compare?ids={q1['id']}", headers=headers)
    assert res1.status_code == 422

    # 4 IDs -> 422
    res4 = client.get(
        f"/api/quotes/compare?ids={q1['id']}&ids={q2['id']}&ids={q3['id']}&ids={q4['id']}",
        headers=headers,
    )
    assert res4.status_code == 422


def test_compare_two_quotes_success(session, client):
    biz = _make_business(session, "Biz Compare Two")
    user = _make_user(session, "comp2@example.com", "POLICYHOLDER", biz)
    token = _token_for(user)
    headers = {"Authorization": f"Bearer {token}"}

    q1 = _create_quote(client, token, "REFRIGERATION", "50000.00", 1, "BASIC")
    q2 = _create_quote(client, token, "REFRIGERATION", "50000.00", 1, "COMPREHENSIVE")

    # Request order: q2, q1
    res = client.get(
        f"/api/quotes/compare?ids={q2['id']}&ids={q1['id']}",
        headers=headers,
    )
    assert res.status_code == 200
    data = res.json()
    assert isinstance(data, list)
    assert len(data) == 2

    # Must preserve requested order
    assert data[0]["id"] == q2["id"]
    assert data[1]["id"] == q1["id"]

    # Verify fields: total, every premium line, sum_insured, age, cover
    for item in data:
        assert "total" in item
        assert "lines" in item
        assert len(item["lines"]) == 4
        assert "sum_insured" in item
        assert "age_years" in item
        assert "cover" in item

    assert data[0]["cover"] == "COMPREHENSIVE"
    assert data[1]["cover"] == "BASIC"


def test_compare_three_quotes_preserves_order(session, client):
    biz = _make_business(session, "Biz Compare Three")
    user = _make_user(session, "comp3@example.com", "POLICYHOLDER", biz)
    token = _token_for(user)
    headers = {"Authorization": f"Bearer {token}"}

    q1 = _create_quote(client, token, "COOKING", "10000.00", 0, "BASIC")
    q2 = _create_quote(client, token, "COOKING", "20000.00", 2, "STANDARD")
    q3 = _create_quote(client, token, "COOKING", "30000.00", 5, "COMPREHENSIVE")

    # Order q3, q1, q2
    res = client.get(
        f"/api/quotes/compare?ids={q3['id']}&ids={q1['id']}&ids={q2['id']}",
        headers=headers,
    )
    assert res.status_code == 200
    data = res.json()
    assert len(data) == 3
    assert data[0]["id"] == q3["id"]
    assert data[1]["id"] == q1["id"]
    assert data[2]["id"] == q2["id"]


def test_other_business_id_returns_404_for_whole_request(session, client):
    biz_a = _make_business(session, "Biz A")
    biz_b = _make_business(session, "Biz B")
    user_a = _make_user(session, "owner.a@example.com", "POLICYHOLDER", biz_a)
    user_b = _make_user(session, "owner.b@example.com", "POLICYHOLDER", biz_b)

    q_a1 = _create_quote(client, _token_for(user_a), "HVAC", "40000.00", 2, "STANDARD")
    q_b1 = _create_quote(client, _token_for(user_b), "HVAC", "40000.00", 2, "STANDARD")

    headers_a = {"Authorization": f"Bearer {_token_for(user_a)}"}

    # User A tries to compare their quote with User B's quote -> 404
    res = client.get(
        f"/api/quotes/compare?ids={q_a1['id']}&ids={q_b1['id']}",
        headers=headers_a,
    )
    assert res.status_code == 404


def test_invalid_or_nonexistent_id_returns_404(session, client):
    biz = _make_business(session, "Biz Missing")
    user = _make_user(session, "missing@example.com", "POLICYHOLDER", biz)
    token = _token_for(user)
    headers = {"Authorization": f"Bearer {token}"}

    q1 = _create_quote(client, token, "ELECTRICAL", "20000.00", 1, "BASIC")
    fake_uuid = str(uuid.uuid4())

    res = client.get(
        f"/api/quotes/compare?ids={q1['id']}&ids={fake_uuid}",
        headers=headers,
    )
    assert res.status_code == 404

    res_invalid = client.get(
        f"/api/quotes/compare?ids={q1['id']}&ids=not-a-uuid",
        headers=headers,
    )
    assert res_invalid.status_code == 404

