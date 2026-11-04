from datetime import date, timedelta
from decimal import Decimal
import uuid

import pytest
from fastapi.testclient import TestClient

from app.core.database import get_db
from app.core.security import create_access_token, hash_password
from app.main import app
from app.models import Business, Equipment, Policy, PolicyEquipment, User
from app.models.enums import PolicyStatus

PASSWORD = "test-policy-doc-password"


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


def _make_policy_with_equipment(
    session,
    business: Business,
    policy_number: str,
    equipment_desc: str = "Espresso Machine",
) -> Policy:
    today = date.today()
    policy = Policy(
        id=uuid.uuid4(),
        policy_number=policy_number,
        business_id=business.id,
        status=PolicyStatus.ACTIVE.value,
        start_date=today,
        end_date=today + timedelta(days=365),
        premium_amount=Decimal("1200.00"),
        deductible_amount=Decimal("500.00"),
        coverage_limit=Decimal("50000.00"),
    )
    session.add(policy)
    session.flush()

    equipment = Equipment(
        id=uuid.uuid4(),
        business_id=business.id,
        category="COOKING",
        description=equipment_desc,
    )
    session.add(equipment)
    session.flush()

    session.add(
        PolicyEquipment(
            policy_id=policy.id,
            equipment_id=equipment.id,
        )
    )
    session.flush()
    return policy


def test_owner_lists_only_own_policies(session, client):
    biz_a = _make_business(session, "Alpha Cafe")
    biz_b = _make_business(session, "Beta Bistro")
    owner_a = _make_user(session, "owner.a@example.com", "POLICYHOLDER", biz_a)
    _make_user(session, "owner.b@example.com", "POLICYHOLDER", biz_b)

    policy_a1 = _make_policy_with_equipment(session, biz_a, "EQP-ALPHA001")
    policy_a2 = _make_policy_with_equipment(session, biz_a, "EQP-ALPHA002")
    _make_policy_with_equipment(session, biz_b, "EQP-BETA001")

    headers = {"Authorization": f"Bearer {_token_for(owner_a)}"}
    res = client.get("/api/policies", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert isinstance(data, list)

    policy_numbers = [p["policy_number"] for p in data]
    assert "EQP-ALPHA001" in policy_numbers
    assert "EQP-ALPHA002" in policy_numbers
    assert "EQP-BETA001" not in policy_numbers

    # Verify returned fields
    first = next(p for p in data if p["id"] == str(policy_a1.id))
    assert first["policy_number"] == policy_a1.policy_number
    assert first["status"] == policy_a1.status
    assert first["start_date"] == str(policy_a1.start_date)
    assert first["end_date"] == str(policy_a1.end_date)
    assert Decimal(str(first["premium_amount"])) == policy_a1.premium_amount
    assert Decimal(str(first["coverage_limit"])) == policy_a1.coverage_limit
    assert Decimal(str(first["deductible_amount"])) == policy_a1.deductible_amount


def test_owner_downloads_own_document(session, client):
    business = _make_business(session, "Corner Deli")
    owner = _make_user(session, "deli.owner@example.com", "POLICYHOLDER", business)
    policy = _make_policy_with_equipment(session, business, "EQP-DELI1001", "Meat Slicer")

    headers = {"Authorization": f"Bearer {_token_for(owner)}"}
    res = client.get(f"/api/policies/{policy.id}/document", headers=headers)
    assert res.status_code == 200
    assert "text/html" in res.headers.get("content-type", "")
    assert policy.policy_number in res.headers.get("content-disposition", "")
    assert f'{policy.policy_number}.html' in res.headers.get("content-disposition", "")

    html_text = res.text
    assert policy.policy_number in html_text
    assert "Corner Deli" in html_text
    assert "Meat Slicer" in html_text
    assert "Simulated policy for demonstration only" in html_text
    assert "Policy issued by EquipSure (simulated)" in html_text


def test_other_business_gets_404_for_document(session, client):
    biz_a = _make_business(session, "Bakery Alpha")
    biz_b = _make_business(session, "Bakery Beta")
    owner_b = _make_user(session, "baker.b@example.com", "POLICYHOLDER", biz_b)
    policy_a = _make_policy_with_equipment(session, biz_a, "EQP-SECURE01")

    headers = {"Authorization": f"Bearer {_token_for(owner_b)}"}
    res = client.get(f"/api/policies/{policy_a.id}/document", headers=headers)
    assert res.status_code == 404


def test_html_escaping_prevents_xss(session, client):
    malicious_name = "SuperCafe <script>alert('xss')</script>"
    business = _make_business(session, malicious_name)
    owner = _make_user(session, "xss.test@example.com", "POLICYHOLDER", business)
    policy = _make_policy_with_equipment(session, business, "EQP-XSS00001", "Grinder <img src=x onerror=alert(1)>")

    headers = {"Authorization": f"Bearer {_token_for(owner)}"}
    res = client.get(f"/api/policies/{policy.id}/document", headers=headers)
    assert res.status_code == 200
    html_text = res.text

    # Must NOT contain raw unescaped script or img tag
    assert "<script>alert('xss')</script>" not in html_text
    assert "<img src=x onerror=alert(1)>" not in html_text

    # Must contain HTML escaped entities
    assert "&lt;script&gt;" in html_text
    assert "&lt;img" in html_text


def test_ops_and_admin_may_download_any_policy(session, client):
    business = _make_business(session, "Downtown Bistro")
    ops_user = _make_user(session, "ops.inspect@example.com", "OPS")
    admin_user = _make_user(session, "admin.inspect@example.com", "ADMIN")
    policy = _make_policy_with_equipment(session, business, "EQP-STAFF001")

    # OPS can download
    res_ops = client.get(
        f"/api/policies/{policy.id}/document",
        headers={"Authorization": f"Bearer {_token_for(ops_user)}"},
    )
    assert res_ops.status_code == 200
    assert "EQP-STAFF001" in res_ops.headers.get("content-disposition", "")

    # ADMIN can download
    res_admin = client.get(
        f"/api/policies/{policy.id}/document",
        headers={"Authorization": f"Bearer {_token_for(admin_user)}"},
    )
    assert res_admin.status_code == 200
    assert "EQP-STAFF001" in res_admin.headers.get("content-disposition", "")

