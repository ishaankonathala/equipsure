from datetime import date
from decimal import Decimal
import uuid

import pytest
from fastapi import status
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.database import get_db
from app.core.security import create_access_token, hash_password
from app.main import app
from app.models import (
    Business,
    Claim,
    ClaimEvent,
    ClaimSettlement,
    Equipment,
    Notification,
    Policy,
    User,
)
from app.models.enums import ClaimStatus, SettlementStatus


@pytest.fixture
def client(session):
    def override_get_db():
        yield session

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


def _make_user(
    session,
    email: str,
    role: str,
    business_id: uuid.UUID | None,
    *,
    full_name: str | None = None,
    is_active: bool = True,
) -> User:
    user = User(
        id=uuid.uuid4(),
        email=email,
        password_hash=hash_password("test-password"),
        full_name=full_name or email,
        role=role,
        business_id=business_id,
        is_active=is_active,
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


def test_list_assignable_officers_rbac_and_filtering(
    client, session, business, policyholder_user
):
    ops_officer = _make_user(
        session,
        "ops-active@example.com",
        "OPS",
        None,
        full_name="Active Ops Officer",
    )
    admin_officer = _make_user(
        session,
        "admin-active@example.com",
        "ADMIN",
        None,
        full_name="Active Admin Officer",
    )
    inactive_ops = _make_user(
        session,
        "ops-inactive@example.com",
        "OPS",
        None,
        full_name="Inactive Ops Officer",
        is_active=False,
    )

    ph_resp = client.get(
        "/api/claims/officers",
        headers={"Authorization": f"Bearer {_token_for(policyholder_user)}"},
    )
    assert ph_resp.status_code == status.HTTP_403_FORBIDDEN

    ops_resp = client.get(
        "/api/claims/officers",
        headers={"Authorization": f"Bearer {_token_for(ops_officer)}"},
    )
    assert ops_resp.status_code == status.HTTP_200_OK
    officers = ops_resp.json()
    returned_ids = {item["id"] for item in officers}
    assert str(ops_officer.id) in returned_ids
    assert str(admin_officer.id) in returned_ids
    assert str(inactive_ops.id) not in returned_ids
    assert str(policyholder_user.id) not in returned_ids


def test_officer_assignment_transitions_under_review_and_exposes_fields(
    client, session, claim, policyholder_user
):
    ops_actor = _make_user(
        session,
        "dispatcher@example.com",
        "OPS",
        None,
        full_name="Lead Dispatcher",
    )
    investigator = _make_user(
        session,
        "investigator@example.com",
        "OPS",
        None,
        full_name="Priya Investigator",
    )
    claim.status = ClaimStatus.UNDER_REVIEW.value
    session.flush()

    assign_resp = client.post(
        f"/api/claims/{claim.id}/assignment",
        json={
            "officer_user_id": str(investigator.id),
            "notes": "Inspect espresso boiler pressure valve.",
            "move_to_investigation": True,
        },
        headers={"Authorization": f"Bearer {_token_for(ops_actor)}"},
    )
    assert assign_resp.status_code == status.HTTP_200_OK
    payload = assign_resp.json()
    assert payload["claim_id"] == str(claim.id)
    assert payload["status"] == ClaimStatus.INVESTIGATION_ASSIGNED.value
    assert payload["assigned_officer_id"] == str(investigator.id)
    assert payload["assigned_officer_name"] == "Priya Investigator"
    assert payload["assigned_officer_role"] == "OPS"
    assert payload["assigned_at"] is not None

    detail_resp = client.get(
        f"/api/claims/{claim.reference}",
        headers={"Authorization": f"Bearer {_token_for(policyholder_user)}"},
    )
    assert detail_resp.status_code == status.HTTP_200_OK
    detail = detail_resp.json()
    assert detail["status"] == ClaimStatus.INVESTIGATION_ASSIGNED.value
    assert detail["assigned_officer_id"] == str(investigator.id)
    assert detail["assigned_officer_name"] == "Priya Investigator"
    assert detail["assigned_officer_role"] == "OPS"
    assert detail["assigned_at"] is not None

    list_resp = client.get(
        "/api/claims",
        headers={"Authorization": f"Bearer {_token_for(ops_actor)}"},
    )
    assert list_resp.status_code == status.HTTP_200_OK
    listed = next(item for item in list_resp.json() if item["id"] == str(claim.id))
    assert listed["assigned_officer_id"] == str(investigator.id)
    assert listed["assigned_officer_name"] == "Priya Investigator"
    assert listed["assigned_at"] is not None

    events = (
        session.execute(
            select(ClaimEvent)
            .where(ClaimEvent.claim_id == claim.id)
            .order_by(ClaimEvent.id.asc())
        )
        .scalars()
        .all()
    )
    assert len(events) == 1
    assert events[0].old_status == ClaimStatus.UNDER_REVIEW.value
    assert events[0].new_status == ClaimStatus.INVESTIGATION_ASSIGNED.value
    assert "Priya Investigator" in events[0].explanation
    assert "Inspect espresso boiler pressure valve." in events[0].explanation

    notifications = (
        session.execute(
            select(Notification).where(Notification.claim_id == claim.id)
        )
        .scalars()
        .all()
    )
    assert len(notifications) >= 1


def test_assignment_rejects_invalid_target_terminal_status_and_unauthorized_users(
    client, session, claim, policyholder_user
):
    ops_actor = _make_user(session, "ops-assign-guard@example.com", "OPS", None)
    inactive_ops = _make_user(
        session,
        "ops-disabled@example.com",
        "OPS",
        None,
        is_active=False,
    )
    other_biz = Business(id=uuid.uuid4(), name="Other Cafe")
    session.add(other_biz)
    session.flush()
    other_ph = _make_user(
        session, "other-ph@example.com", "POLICYHOLDER", other_biz.id
    )

    own_ph_resp = client.post(
        f"/api/claims/{claim.id}/assignment",
        json={"officer_user_id": str(ops_actor.id)},
        headers={"Authorization": f"Bearer {_token_for(policyholder_user)}"},
    )
    assert own_ph_resp.status_code == status.HTTP_403_FORBIDDEN

    cross_ph_resp = client.post(
        f"/api/claims/{claim.id}/assignment",
        json={"officer_user_id": str(ops_actor.id)},
        headers={"Authorization": f"Bearer {_token_for(other_ph)}"},
    )
    assert cross_ph_resp.status_code == status.HTTP_404_NOT_FOUND

    assign_ph_target = client.post(
        f"/api/claims/{claim.id}/assignment",
        json={"officer_user_id": str(policyholder_user.id)},
        headers={"Authorization": f"Bearer {_token_for(ops_actor)}"},
    )
    assert assign_ph_target.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    assign_inactive_target = client.post(
        f"/api/claims/{claim.id}/assignment",
        json={"officer_user_id": str(inactive_ops.id)},
        headers={"Authorization": f"Bearer {_token_for(ops_actor)}"},
    )
    assert assign_inactive_target.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    claim.status = ClaimStatus.REJECTED.value
    session.flush()
    assign_rejected = client.post(
        f"/api/claims/{claim.id}/assignment",
        json={"officer_user_id": str(ops_actor.id)},
        headers={"Authorization": f"Bearer {_token_for(ops_actor)}"},
    )
    assert assign_rejected.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


def test_settlement_lifecycle_defaults_to_inr_and_updates_status_and_events(
    client, session, claim, policy, policyholder_user
):
    ops_officer = _make_user(
        session,
        "settlement-ops@example.com",
        "OPS",
        None,
        full_name="Settlement Officer",
    )
    claim.status = ClaimStatus.APPROVED.value
    session.flush()

    initial_get = client.get(
        f"/api/claims/{claim.id}/settlement",
        headers={"Authorization": f"Bearer {_token_for(policyholder_user)}"},
    )
    assert initial_get.status_code == status.HTTP_200_OK
    initial_data = initial_get.json()
    assert initial_data["simulated"] is True
    assert initial_data["default_currency"] == "INR"
    assert "INR" in initial_data["supported_currencies"]
    assert initial_data["settlement"] is None

    create_resp = client.post(
        f"/api/claims/{claim.id}/settlement",
        json={
            "amount": "18500.00",
            "notes": "Approved compressor replacement less deductible.",
            "mark_settled": False,
        },
        headers={"Authorization": f"Bearer {_token_for(ops_officer)}"},
    )
    assert create_resp.status_code == status.HTTP_201_CREATED
    created_data = create_resp.json()
    assert created_data["claim_status"] == ClaimStatus.SETTLEMENT_IN_PROGRESS.value
    settlement = created_data["settlement"]
    assert settlement is not None
    assert settlement["settlement_reference"].startswith("STL-")
    assert settlement["amount"] == "18500.00"
    assert settlement["currency"] == "INR"
    assert settlement["status"] == SettlementStatus.IN_PROGRESS.value
    assert settlement["settled_at"] is None
    assert settlement["simulated"] is True
    assert settlement["source"] == "MOCK_CLAIMCENTER"

    complete_resp = client.patch(
        f"/api/claims/{claim.reference}/settlement",
        json={"notes": "Simulated NEFT payout batch confirmed."},
        headers={"Authorization": f"Bearer {_token_for(ops_officer)}"},
    )
    assert complete_resp.status_code == status.HTTP_200_OK
    completed_data = complete_resp.json()
    assert completed_data["claim_status"] == ClaimStatus.SETTLED.value
    settled = completed_data["settlement"]
    assert settled["status"] == SettlementStatus.SETTLED.value
    assert settled["settled_at"] is not None
    assert settled["notes"] == "Simulated NEFT payout batch confirmed."

    events = (
        session.execute(
            select(ClaimEvent)
            .where(ClaimEvent.claim_id == claim.id)
            .order_by(ClaimEvent.id.asc())
        )
        .scalars()
        .all()
    )
    assert [e.new_status for e in events] == [
        ClaimStatus.SETTLEMENT_IN_PROGRESS.value,
        ClaimStatus.SETTLED.value,
    ]
    assert "INR 18500.00" in events[0].explanation
    assert settled["settlement_reference"] in events[1].explanation


def test_settlement_rejects_duplicate_invalid_status_excess_amount_and_unauthorized_access(
    client, session, business, policy, equipment, claim, policyholder_user
):
    ops_officer = _make_user(session, "ops-settle-guard@example.com", "OPS", None)
    other_biz = Business(id=uuid.uuid4(), name="Second Cafe")
    session.add(other_biz)
    session.flush()
    other_ph = _make_user(
        session, "other-owner@example.com", "POLICYHOLDER", other_biz.id
    )

    rejected_claim = Claim(
        id=uuid.uuid4(),
        reference="REJ-CLAIM-001",
        business_id=business.id,
        policy_id=policy.id,
        equipment_id=equipment.id,
        status=ClaimStatus.REJECTED.value,
        incident_date=date(2026, 9, 10),
        incident_description="Rejected grinder claim",
        amount_claimed=Decimal("1200.00"),
    )
    session.add(rejected_claim)
    session.flush()

    reject_settle_resp = client.post(
        f"/api/claims/{rejected_claim.id}/settlement",
        json={"amount": "1000.00"},
        headers={"Authorization": f"Bearer {_token_for(ops_officer)}"},
    )
    assert reject_settle_resp.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    claim.status = ClaimStatus.APPROVED.value
    session.flush()

    ph_create_resp = client.post(
        f"/api/claims/{claim.id}/settlement",
        json={"amount": "1000.00"},
        headers={"Authorization": f"Bearer {_token_for(policyholder_user)}"},
    )
    assert ph_create_resp.status_code == status.HTTP_403_FORBIDDEN

    cross_get_resp = client.get(
        f"/api/claims/{claim.id}/settlement",
        headers={"Authorization": f"Bearer {_token_for(other_ph)}"},
    )
    assert cross_get_resp.status_code == status.HTTP_404_NOT_FOUND

    cross_post_resp = client.post(
        f"/api/claims/{claim.id}/settlement",
        json={"amount": "1000.00"},
        headers={"Authorization": f"Bearer {_token_for(other_ph)}"},
    )
    assert cross_post_resp.status_code == status.HTTP_404_NOT_FOUND

    bad_currency_resp = client.post(
        f"/api/claims/{claim.id}/settlement",
        json={"amount": "1000.00", "currency": "JPY"},
        headers={"Authorization": f"Bearer {_token_for(ops_officer)}"},
    )
    assert bad_currency_resp.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    over_limit_resp = client.post(
        f"/api/claims/{claim.id}/settlement",
        json={"amount": "75000.00", "currency": "INR"},
        headers={"Authorization": f"Bearer {_token_for(ops_officer)}"},
    )
    assert over_limit_resp.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    first_ok = client.post(
        f"/api/claims/{claim.id}/settlement",
        json={"amount": "2500.00", "currency": "USD", "mark_settled": True},
        headers={"Authorization": f"Bearer {_token_for(ops_officer)}"},
    )
    assert first_ok.status_code == status.HTTP_201_CREATED
    assert first_ok.json()["claim_status"] == ClaimStatus.SETTLED.value
    assert first_ok.json()["settlement"]["currency"] == "USD"
    assert first_ok.json()["settlement"]["status"] == SettlementStatus.SETTLED.value

    duplicate_resp = client.post(
        f"/api/claims/{claim.id}/settlement",
        json={"amount": "2500.00", "currency": "USD"},
        headers={"Authorization": f"Bearer {_token_for(ops_officer)}"},
    )
    assert duplicate_resp.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    complete_again_resp = client.patch(
        f"/api/claims/{claim.id}/settlement",
        json={"notes": "Attempt duplicate completion"},
        headers={"Authorization": f"Bearer {_token_for(ops_officer)}"},
    )
    assert complete_again_resp.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    settlement_rows = (
        session.execute(
            select(ClaimSettlement).where(ClaimSettlement.claim_id == claim.id)
        )
        .scalars()
        .all()
    )
    assert len(settlement_rows) == 1

