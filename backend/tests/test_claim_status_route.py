import uuid

import pytest
from fastapi import status
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.core.config import settings
from app.core.database import get_db
from app.core.security import create_access_token, hash_password
from app.main import app
from app.models import Business, ClaimEvent, User


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
        password_hash=hash_password("claim-status-password"),
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


def _event_count(session, claim):
    return session.execute(
        select(func.count())
        .select_from(ClaimEvent)
        .where(ClaimEvent.claim_id == claim.id)
    ).scalar_one()


def test_policyholder_withdraws_own_claim(client, session, business, claim):
    owner = _make_user(session, "owner@status.example", "POLICYHOLDER", business.id)
    response = client.post(
        f"/api/claims/{claim.id}/status",
        json={"target_status": "WITHDRAWN", "explanation": "Customer withdrew"},
        headers={"Authorization": f"Bearer {_token_for(owner)}"},
    )

    assert response.status_code == status.HTTP_200_OK
    assert response.json()["new_status"] == "WITHDRAWN"
    assert response.json()["source"] == "POLICYHOLDER"
    session.refresh(claim)
    assert claim.status == "WITHDRAWN"


def test_policyholder_cannot_advance(client, session, business, claim):
    owner = _make_user(session, "owner-advance@status.example", "POLICYHOLDER", business.id)
    response = client.post(
        f"/api/claims/{claim.id}/status",
        json={"target_status": "UNDER_VERIFICATION", "explanation": "Trying to advance"},
        headers={"Authorization": f"Bearer {_token_for(owner)}"},
    )

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    assert claim.status == "SUBMITTED"


def test_ops_advances_claim(client, session, claim):
    ops = _make_user(session, "ops@status.example", "OPS", None)
    response = client.post(
        f"/api/claims/{claim.id}/status",
        json={"target_status": "UNDER_VERIFICATION", "explanation": "Checked"},
        headers={"Authorization": f"Bearer {_token_for(ops)}"},
    )

    assert response.status_code == status.HTTP_200_OK
    assert response.json()["new_status"] == "UNDER_VERIFICATION"
    assert response.json()["source"] == "OPS"


def test_illegal_move_returns_422_and_no_event(client, session, claim):
    ops = _make_user(session, "ops-illegal@status.example", "OPS", None)
    response = client.post(
        f"/api/claims/{claim.id}/status",
        json={"target_status": "APPROVED", "explanation": "Skip ahead"},
        headers={"Authorization": f"Bearer {_token_for(ops)}"},
    )

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    assert claim.status == "SUBMITTED"
    assert _event_count(session, claim) == 0


def test_unknown_status_returns_422(client, session, claim):
    ops = _make_user(session, "ops-unknown@status.example", "OPS", None)
    response = client.post(
        f"/api/claims/{claim.id}/status",
        json={"target_status": "NOT_A_STATUS", "explanation": "Unknown target"},
        headers={"Authorization": f"Bearer {_token_for(ops)}"},
    )

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


def test_other_business_policyholder_gets_404(
    client, session, business, claim
):
    other_business = Business(id=uuid.uuid4(), name="Other Status Business")
    session.add(other_business)
    session.flush()
    other_user = _make_user(
        session,
        "other@status.example",
        "POLICYHOLDER",
        other_business.id,
    )
    response = client.post(
        f"/api/claims/{claim.id}/status",
        json={"target_status": "WITHDRAWN", "explanation": "Customer withdrew"},
        headers={"Authorization": f"Bearer {_token_for(other_user)}"},
    )

    assert response.status_code == status.HTTP_404_NOT_FOUND


def test_blank_explanation_returns_422(client, session, claim):
    ops = _make_user(session, "ops-blank@status.example", "OPS", None)
    response = client.post(
        f"/api/claims/{claim.id}/status",
        json={"target_status": "UNDER_VERIFICATION", "explanation": "   "},
        headers={"Authorization": f"Bearer {_token_for(ops)}"},
    )

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    assert claim.status == "SUBMITTED"