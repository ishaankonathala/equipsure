import uuid

import pytest
from fastapi import status
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.core.config import settings
from app.core.database import get_db
from app.core.security import create_access_token, hash_password
from app.main import app
from app.models import Business, ClaimDocument, ClaimEvent, User
from app.services.assessment import build_assessment_prompt
from app.services.assessment_service import run_claim_assessment
from app.ai.fake_provider import FakeAIProvider
from app.services.assessment import build_assessment_schema_hint

ASSESSMENT_JSON = (
    '{"summary":"Refrigerator reported stopped cooling; the claim is consistent '
    'with a sudden breakdown, subject to review.","cited_clause_ids":'
    '["DEMO-COV-01","DEMO-REP-01"],"missing_items":["Repair estimate"],'
    '"inconsistencies":[],"recommendation":"Request the repair estimate and '
    'confirm the incident date before review.","advisory_only":true}'
)


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
        password_hash=hash_password("assessment-route-password"),
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


def _patch_fake_provider(monkeypatch, claim, response_text=ASSESSMENT_JSON):
    prompt = build_assessment_prompt(
        claim.reference,
        claim.incident_date.isoformat(),
        claim.incident_description,
        str(claim.amount_claimed),
        [],
    )
    fake_provider = FakeAIProvider({prompt: response_text})
    monkeypatch.setattr(
        "app.api.routes.claims.build_provider",
        lambda **kwargs: fake_provider,
    )
    return fake_provider


def _count_claim_rows(session, model, claim):
    return session.execute(
        select(func.count()).select_from(model).where(model.claim_id == claim.id)
    ).scalar_one()


def test_ops_gets_assessment(client, session, claim, monkeypatch):
    ops = _make_user(session, "ops-assessment@example.com", "OPS", None)
    _patch_fake_provider(monkeypatch, claim)

    response = client.post(
        f"/api/claims/{claim.id}/assessment",
        headers={"Authorization": f"Bearer {_token_for(ops)}"},
    )

    assert response.status_code == status.HTTP_200_OK
    assert response.json()["advisory_only"] is True
    assert "DEMO-COV-01" in response.json()["cited_clause_ids"]


def test_admin_gets_assessment(client, session, claim, monkeypatch):
    admin = _make_user(session, "admin-assessment@example.com", "ADMIN", None)
    _patch_fake_provider(monkeypatch, claim)

    response = client.post(
        f"/api/claims/{claim.id}/assessment",
        headers={"Authorization": f"Bearer {_token_for(admin)}"},
    )

    assert response.status_code == status.HTTP_200_OK
    assert response.json()["advisory_only"] is True


def test_policyholder_gets_403(client, session, business, claim):
    owner = _make_user(
        session, "owner-assessment@example.com", "POLICYHOLDER", business.id
    )

    response = client.post(
        f"/api/claims/{claim.id}/assessment",
        headers={"Authorization": f"Bearer {_token_for(owner)}"},
    )

    assert response.status_code == status.HTTP_403_FORBIDDEN


def test_other_business_gets_404(client, session, claim):
    other_business = Business(id=uuid.uuid4(), name="Other Assessment Business")
    session.add(other_business)
    session.flush()
    owner = _make_user(
        session,
        "other-owner-assessment@example.com",
        "POLICYHOLDER",
        other_business.id,
    )

    response = client.post(
        f"/api/claims/{claim.id}/assessment",
        headers={"Authorization": f"Bearer {_token_for(owner)}"},
    )

    assert response.status_code == status.HTTP_404_NOT_FOUND


def test_provider_failure_returns_503(client, session, claim, monkeypatch):
    ops = _make_user(session, "ops-failure-assessment@example.com", "OPS", None)
    fake_provider = FakeAIProvider()
    monkeypatch.setattr(
        "app.api.routes.claims.build_provider",
        lambda **kwargs: fake_provider,
    )

    response = client.post(
        f"/api/claims/{claim.id}/assessment",
        headers={"Authorization": f"Bearer {_token_for(ops)}"},
    )

    assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    assert response.json()["detail"] == "AI provider unavailable"


def test_assessment_stores_nothing(client, session, claim, monkeypatch):
    ops = _make_user(session, "ops-readonly-assessment@example.com", "OPS", None)
    _patch_fake_provider(monkeypatch, claim)
    events_before = _count_claim_rows(session, ClaimEvent, claim)
    documents_before = _count_claim_rows(session, ClaimDocument, claim)
    status_before = claim.status

    response = client.post(
        f"/api/claims/{claim.id}/assessment",
        headers={"Authorization": f"Bearer {_token_for(ops)}"},
    )

    assert response.status_code == status.HTTP_200_OK
    assert _count_claim_rows(session, ClaimEvent, claim) == events_before
    assert _count_claim_rows(session, ClaimDocument, claim) == documents_before
    assert claim.status == status_before