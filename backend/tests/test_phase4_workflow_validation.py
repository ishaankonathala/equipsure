from decimal import Decimal
import uuid

import pytest
from fastapi import status
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.config import settings
from app.core.database import get_db
from app.core.security import create_access_token, hash_password
from app.main import app
from app.models import ClaimEvent, Notification, User
from app.models.enums import ClaimStatus

PDF_BYTES = b"%PDF-1.4\n" + b"0" * 100


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
        password_hash=hash_password("phase4-test-password"),
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


def test_generic_status_route_cannot_bypass_settlement_endpoints(
    client, session, claim
):
    ops = _make_user(session, "ops-bypass@example.com", "OPS", None)
    claim.status = ClaimStatus.APPROVED.value
    session.flush()

    bypass_start = client.post(
        f"/api/claims/{claim.id}/status",
        json={
            "target_status": ClaimStatus.SETTLEMENT_IN_PROGRESS.value,
            "explanation": "Try to bypass settlement creation",
        },
        headers={"Authorization": f"Bearer {_token_for(ops)}"},
    )
    assert bypass_start.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    assert "settlement endpoints" in bypass_start.json()["detail"].lower()
    session.refresh(claim)
    assert claim.status == ClaimStatus.APPROVED.value

    claim.status = ClaimStatus.SETTLEMENT_IN_PROGRESS.value
    session.flush()

    bypass_complete = client.post(
        f"/api/claims/{claim.id}/status",
        json={
            "target_status": ClaimStatus.SETTLED.value,
            "explanation": "Try to bypass settlement completion",
        },
        headers={"Authorization": f"Bearer {_token_for(ops)}"},
    )
    assert bypass_complete.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    assert "settlement endpoints" in bypass_complete.json()["detail"].lower()
    session.refresh(claim)
    assert claim.status == ClaimStatus.SETTLEMENT_IN_PROGRESS.value


def test_settlement_rejects_amount_above_amount_claimed(
    client, session, claim, policy
):
    ops = _make_user(session, "ops-amount-guard@example.com", "OPS", None)
    claim.status = ClaimStatus.APPROVED.value
    claim.amount_claimed = Decimal("1500.00")
    session.flush()

    resp = client.post(
        f"/api/claims/{claim.id}/settlement",
        json={"amount": "1500.01", "currency": "INR"},
        headers={"Authorization": f"Bearer {_token_for(ops)}"},
    )
    assert resp.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    assert "claimed amount" in resp.json()["detail"].lower()


def test_rejection_reason_persisted_and_exposed_on_claim_detail(
    client, session, claim, policyholder_user
):
    ops = _make_user(session, "ops-reject@example.com", "OPS", None)
    claim.status = ClaimStatus.DECISION_PENDING.value
    session.flush()

    pre_detail = client.get(
        f"/api/claims/{claim.id}",
        headers={"Authorization": f"Bearer {_token_for(policyholder_user)}"},
    )
    assert pre_detail.status_code == status.HTTP_200_OK
    assert pre_detail.json()["rejection_reason"] is None

    blank_reject = client.post(
        f"/api/claims/{claim.id}/status",
        json={"target_status": ClaimStatus.REJECTED.value, "explanation": "   "},
        headers={"Authorization": f"Bearer {_token_for(ops)}"},
    )
    assert blank_reject.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    reason = "Failure caused by routine wear and descaling neglect (Clause CL-WEAR-01)."
    reject_resp = client.post(
        f"/api/claims/{claim.id}/status",
        json={
            "target_status": ClaimStatus.REJECTED.value,
            "explanation": reason,
        },
        headers={"Authorization": f"Bearer {_token_for(ops)}"},
    )
    assert reject_resp.status_code == status.HTTP_200_OK
    assert reject_resp.json()["new_status"] == ClaimStatus.REJECTED.value

    rejected_detail = client.get(
        f"/api/claims/{claim.id}",
        headers={"Authorization": f"Bearer {_token_for(policyholder_user)}"},
    )
    assert rejected_detail.status_code == status.HTTP_200_OK
    assert rejected_detail.json()["status"] == ClaimStatus.REJECTED.value
    assert rejected_detail.json()["rejection_reason"] == reason

    close_resp = client.post(
        f"/api/claims/{claim.id}/status",
        json={
            "target_status": ClaimStatus.CLOSED.value,
            "explanation": "File closed after rejection notice.",
        },
        headers={"Authorization": f"Bearer {_token_for(ops)}"},
    )
    assert close_resp.status_code == status.HTTP_200_OK

    closed_detail = client.get(
        f"/api/claims/{claim.id}",
        headers={"Authorization": f"Bearer {_token_for(policyholder_user)}"},
    )
    assert closed_detail.status_code == status.HTTP_200_OK
    assert closed_detail.json()["status"] == ClaimStatus.CLOSED.value
    assert closed_detail.json()["rejection_reason"] == reason

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
        ClaimStatus.REJECTED.value,
        ClaimStatus.CLOSED.value,
    ]


def test_officer_reassignment_blocked_after_approval_and_uploads_blocked_on_terminal_states(
    client, session, claim, policyholder_user
):
    ops = _make_user(session, "ops-post-approval@example.com", "OPS", None)

    for locked_status in (
        ClaimStatus.APPROVED.value,
        ClaimStatus.SETTLEMENT_IN_PROGRESS.value,
    ):
        claim.status = locked_status
        session.flush()
        assign_resp = client.post(
            f"/api/claims/{claim.id}/assignment",
            json={"officer_user_id": str(ops.id)},
            headers={"Authorization": f"Bearer {_token_for(ops)}"},
        )
        assert assign_resp.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    for terminal_status in (
        ClaimStatus.REJECTED.value,
        ClaimStatus.SETTLED.value,
        ClaimStatus.CLOSED.value,
        ClaimStatus.WITHDRAWN.value,
    ):
        claim.status = terminal_status
        session.flush()
        upload_resp = client.post(
            f"/api/claims/{claim.id}/documents",
            files={"file": ("invoice.pdf", PDF_BYTES, "application/pdf")},
            data={"document_type": "INVOICE"},
            headers={"Authorization": f"Bearer {_token_for(policyholder_user)}"},
        )
        assert upload_resp.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        assert terminal_status in upload_resp.json()["detail"]


def test_status_change_notifies_all_active_policyholders_of_business(
    client, session, business, claim, policyholder_user
):
    second_ph = _make_user(
        session,
        "co-owner@example.com",
        "POLICYHOLDER",
        business.id,
        full_name="Second Cafe Owner",
        is_active=True,
    )
    inactive_ph = _make_user(
        session,
        "former-owner@example.com",
        "POLICYHOLDER",
        business.id,
        full_name="Inactive Owner",
        is_active=False,
    )
    ops = _make_user(session, "ops-notify-all@example.com", "OPS", None)

    resp = client.post(
        f"/api/claims/{claim.id}/status",
        json={
            "target_status": ClaimStatus.UNDER_VERIFICATION.value,
            "explanation": "Initial verification started.",
        },
        headers={"Authorization": f"Bearer {_token_for(ops)}"},
    )
    assert resp.status_code == status.HTTP_200_OK

    notifications = (
        session.execute(
            select(Notification).where(Notification.claim_id == claim.id)
        )
        .scalars()
        .all()
    )
    notified_user_ids = {n.user_id for n in notifications}
    assert policyholder_user.id in notified_user_ids
    assert second_ph.id in notified_user_ids
    assert inactive_ph.id not in notified_user_ids
