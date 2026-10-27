from datetime import date
from decimal import Decimal
import uuid

from fastapi import status
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import func, select

from app.core.config import settings
from app.core.database import get_db
from app.core.security import create_access_token, hash_password
from app.main import app
from app.models import (
    BillingRecord,
    Business,
    Claim,
    ClaimDocument,
    ClaimEvent,
    Equipment,
    Policy,
    PolicyEquipment,
    User,
)
from app.models.enums import BillingStatus, ClaimStatus
from app.workflow.service import SYSTEM_ACTOR_ROLE, change_claim_status

PASSWORD = "phase2-verification-password"
PDF_BYTES = b"%PDF-1.4\n" + b"0" * 120
PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"0" * 120


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


def _make_user(session, email: str, role: str, business_id: uuid.UUID | None) -> User:
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


def _token_for(user: User) -> str:
    return create_access_token(
        user_id=str(user.id),
        role=user.role,
        business_id=str(user.business_id) if user.business_id else None,
    )


def _link_equipment(session, policy: Policy, equipment: Equipment) -> None:
    session.add(
        PolicyEquipment(policy_id=policy.id, equipment_id=equipment.id)
    )
    session.flush()


def _add_billing(
    session,
    policy: Policy,
    *,
    amount_due: Decimal = Decimal("1200.00"),
    amount_paid: Decimal = Decimal("1200.00"),
    due_date: date = date(2026, 2, 1),
) -> BillingRecord:
    record = BillingRecord(
        id=uuid.uuid4(),
        policy_id=policy.id,
        period_start=date(2026, 1, 1),
        period_end=date(2027, 1, 1),
        amount_due=amount_due,
        amount_paid=amount_paid,
        status=BillingStatus.PAID.value
        if amount_paid >= amount_due
        else BillingStatus.DUE.value,
        due_date=due_date,
    )
    session.add(record)
    session.flush()
    return record


# ============================================================================
# Task 1 — Policy and Billing Verification Tests
# ============================================================================


def test_verification_succeeds_and_is_read_only(
    client, session, business, policy, equipment, claim
):
    _link_equipment(session, policy, equipment)
    _add_billing(session, policy, amount_paid=Decimal("1200.00"))
    ops = _make_user(session, "ops-verify@example.com", "OPS", None)

    events_before = session.execute(
        select(func.count()).select_from(ClaimEvent).where(ClaimEvent.claim_id == claim.id)
    ).scalar_one()

    response = client.get(
        f"/api/claims/{claim.id}/verification",
        headers={"Authorization": f"Bearer {_token_for(ops)}"},
    )

    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert body["claim_id"] == str(claim.id)
    assert body["claim_reference"] == claim.reference
    assert body["simulated"] is True
    assert "MOCK_POLICYCENTER" in body["sources"]
    assert "MOCK_BILLINGCENTER" in body["sources"]
    assert body["overall_passed"] is True
    assert body["failures"] == []

    pol = body["policy_verification"]
    assert pol["source"] == "MOCK_POLICYCENTER"
    assert pol["simulated"] is True
    assert pol["passed"] is True
    assert pol["policy_number"] == policy.policy_number
    assert pol["status"] == "ACTIVE"
    assert pol["is_active"] is True
    assert pol["start_date"] == "2026-01-01"
    assert pol["end_date"] == "2027-01-01"
    assert pol["incident_date_within_period"] is True
    assert pol["equipment_covered"] is True
    assert pol["equipment_description"] == equipment.description
    assert pol["coverage_limit"] == "50000.00"
    assert pol["deductible_amount"] == "500.00"
    assert pol["reasons"] == []

    bil = body["billing_verification"]
    assert bil["source"] == "MOCK_BILLINGCENTER"
    assert bil["simulated"] is True
    assert bil["passed"] is True
    assert bil["account_status"] == "PAID"
    assert bil["business_rule_result"] == "ELIGIBLE"
    assert bil["premium_amount"] == "100.00"
    assert bil["record_count"] == 1
    assert bil["reasons"] == []

    # Read-only guarantee: claim status and event count unchanged
    session.refresh(claim)
    assert claim.status == "SUBMITTED"
    events_after = session.execute(
        select(func.count()).select_from(ClaimEvent).where(ClaimEvent.claim_id == claim.id)
    ).scalar_one()
    assert events_after == events_before


def test_verification_reports_failed_policy_and_billing_checks(
    client, session, business, policy, equipment, claim
):
    # Policy is cancelled, incident date outside period, equipment not linked, billing overdue
    policy.status = "CANCELLED"
    claim.incident_date = date(2027, 6, 15)
    session.flush()
    _add_billing(
        session,
        policy,
        amount_paid=Decimal("0.00"),
        due_date=date(2026, 2, 1),
    )
    ops = _make_user(session, "ops-fail-verify@example.com", "OPS", None)

    response = client.get(
        f"/api/claims/{claim.id}/verification",
        headers={"Authorization": f"Bearer {_token_for(ops)}"},
    )

    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert body["overall_passed"] is False
    assert "Policy is not active" in body["failures"]
    assert "Equipment is not covered by this policy" in body["failures"]
    assert "Policy account is overdue" in body["failures"]

    pol = body["policy_verification"]
    assert pol["passed"] is False
    assert pol["is_active"] is False
    assert pol["incident_date_within_period"] is False
    assert pol["equipment_covered"] is False
    assert "Policy is not active" in pol["reasons"]
    assert "Equipment is not covered by this policy" in pol["reasons"]

    bil = body["billing_verification"]
    assert bil["passed"] is False
    assert bil["account_status"] == "OVERDUE"
    assert bil["business_rule_result"] == "INELIGIBLE"
    assert "Policy account is overdue" in bil["reasons"]


def test_verification_handles_missing_billing_records_and_mismatched_policy_safely(
    client, session, business, policy, equipment, claim
):
    _link_equipment(session, policy, equipment)
    # No billing records added for policy
    ops = _make_user(session, "ops-missing-verify@example.com", "OPS", None)

    response = client.get(
        f"/api/claims/{claim.id}/verification",
        headers={"Authorization": f"Bearer {_token_for(ops)}"},
    )
    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert body["overall_passed"] is False
    assert body["policy_verification"]["passed"] is True
    assert body["billing_verification"]["passed"] is False
    assert body["billing_verification"]["account_status"] is None
    assert "No billing records for policy" in body["billing_verification"]["reasons"]

    # Now point claim to a policy belonging to another business to verify tenant safety
    other_biz = Business(id=uuid.uuid4(), name="Foreign Business")
    session.add(other_biz)
    session.flush()
    foreign_policy = Policy(
        id=uuid.uuid4(),
        policy_number="FOREIGN-POL-99",
        business_id=other_biz.id,
        status="ACTIVE",
        start_date=date(2026, 1, 1),
        end_date=date(2027, 1, 1),
        premium_amount=Decimal("999.00"),
        deductible_amount=Decimal("999.00"),
        coverage_limit=Decimal("999999.00"),
    )
    session.add(foreign_policy)
    session.flush()
    claim.policy_id = foreign_policy.id
    session.flush()

    response2 = client.get(
        f"/api/claims/{claim.id}/verification",
        headers={"Authorization": f"Bearer {_token_for(ops)}"},
    )
    assert response2.status_code == status.HTTP_200_OK
    body2 = response2.json()
    # Foreign policy details must never be leaked
    assert body2["overall_passed"] is False
    assert body2["policy_verification"]["policy_number"] is None
    assert body2["policy_verification"]["coverage_limit"] is None
    assert "Policy not found" in body2["policy_verification"]["reasons"]


def test_verification_authorization_and_cross_business_isolation(
    client, session, business, policy, equipment, claim
):
    _link_equipment(session, policy, equipment)
    _add_billing(session, policy)

    owner = _make_user(session, "owner-verify@example.com", "POLICYHOLDER", business.id)
    other_biz = Business(id=uuid.uuid4(), name="Other Verify Business")
    session.add(other_biz)
    session.flush()
    other_owner = _make_user(
        session, "other-verify@example.com", "POLICYHOLDER", other_biz.id
    )

    # Unauthenticated -> 401
    unauth = client.get(f"/api/claims/{claim.id}/verification")
    assert unauth.status_code == status.HTTP_401_UNAUTHORIZED

    # Cross-business policyholder -> 404
    cross = client.get(
        f"/api/claims/{claim.id}/verification",
        headers={"Authorization": f"Bearer {_token_for(other_owner)}"},
    )
    assert cross.status_code == status.HTTP_404_NOT_FOUND

    # Unknown claim -> 404
    missing = client.get(
        f"/api/claims/{uuid.uuid4()}/verification",
        headers={"Authorization": f"Bearer {_token_for(owner)}"},
    )
    assert missing.status_code == status.HTTP_404_NOT_FOUND

    # Own-business policyholder -> 200
    own = client.get(
        f"/api/claims/{claim.id}/verification",
        headers={"Authorization": f"Bearer {_token_for(owner)}"},
    )
    assert own.status_code == status.HTTP_200_OK
    assert own.json()["overall_passed"] is True


# ============================================================================
# Task 2 — Claim Status History Timeline Tests
# ============================================================================


def test_claim_history_empty_and_chronological_ordering(
    client, session, business, claim
):
    ops = _make_user(session, "ops-history@example.com", "OPS", None)
    owner = _make_user(session, "owner-history@example.com", "POLICYHOLDER", business.id)

    # Initially empty for fixture claim with no events
    empty_res = client.get(
        f"/api/claims/{claim.id}/history",
        headers={"Authorization": f"Bearer {_token_for(ops)}"},
    )
    assert empty_res.status_code == status.HTTP_200_OK
    assert empty_res.json() == []

    # Record initial policyholder submission event + OPS transition + SYSTEM transition
    initial_event = ClaimEvent(
        claim_id=claim.id,
        old_status=None,
        new_status=ClaimStatus.SUBMITTED.value,
        source="POLICYHOLDER",
        actor_user_id=owner.id,
        explanation="Claim submitted by policyholder.",
    )
    session.add(initial_event)
    session.flush()

    change_claim_status(
        session,
        claim,
        ClaimStatus.UNDER_VERIFICATION,
        "OPS",
        ops.id,
        "Started initial verification.",
    )
    change_claim_status(
        session,
        claim,
        ClaimStatus.DOCUMENTS_REQUIRED,
        SYSTEM_ACTOR_ROLE,
        None,
        "Required documents missing: INVOICE, PHOTO",
    )

    history_res = client.get(
        f"/api/claims/{claim.id}/history",
        headers={"Authorization": f"Bearer {_token_for(owner)}"},
    )
    assert history_res.status_code == status.HTTP_200_OK
    events = history_res.json()
    assert len(events) == 3

    assert events[0]["old_status"] is None
    assert events[0]["new_status"] == "SUBMITTED"
    assert events[0]["source"] == "POLICYHOLDER"
    assert events[0]["actor_user_id"] == str(owner.id)
    assert events[0]["is_system"] is False
    assert events[0]["explanation"] == "Claim submitted by policyholder."
    assert "created_at" in events[0]

    assert events[1]["old_status"] == "SUBMITTED"
    assert events[1]["new_status"] == "UNDER_VERIFICATION"
    assert events[1]["source"] == "OPS"
    assert events[1]["actor_user_id"] == str(ops.id)
    assert events[1]["is_system"] is False

    assert events[2]["old_status"] == "UNDER_VERIFICATION"
    assert events[2]["new_status"] == "DOCUMENTS_REQUIRED"
    assert events[2]["source"] == "SYSTEM"
    assert events[2]["actor_user_id"] is None
    assert events[2]["is_system"] is True


def test_claim_history_authorization_and_cross_business_isolation(
    client, session, business, claim
):
    other_biz = Business(id=uuid.uuid4(), name="Other History Business")
    session.add(other_biz)
    session.flush()
    other_owner = _make_user(
        session, "other-history@example.com", "POLICYHOLDER", other_biz.id
    )

    unauth = client.get(f"/api/claims/{claim.id}/history")
    assert unauth.status_code == status.HTTP_401_UNAUTHORIZED

    cross = client.get(
        f"/api/claims/{claim.id}/history",
        headers={"Authorization": f"Bearer {_token_for(other_owner)}"},
    )
    assert cross.status_code == status.HTTP_404_NOT_FOUND


# ============================================================================
# Task 3 — Document Listing and Download Tests
# ============================================================================


def test_document_listing_and_officer_download(
    client, session, business, claim
):
    owner = _make_user(session, "owner-docs@example.com", "POLICYHOLDER", business.id)
    ops = _make_user(session, "ops-docs@example.com", "OPS", None)

    # Empty list initially
    empty_res = client.get(
        f"/api/claims/{claim.id}/documents",
        headers={"Authorization": f"Bearer {_token_for(ops)}"},
    )
    assert empty_res.status_code == status.HTTP_200_OK
    assert empty_res.json() == []

    # Upload two documents
    up1 = client.post(
        f"/api/claims/{claim.id}/documents",
        files={"file": ("repair_invoice.pdf", PDF_BYTES, "application/pdf")},
        data={"document_type": "INVOICE"},
        headers={"Authorization": f"Bearer {_token_for(owner)}"},
    )
    assert up1.status_code == status.HTTP_201_CREATED

    up2 = client.post(
        f"/api/claims/{claim.id}/documents",
        files={"file": ("damage_photo.png", PNG_BYTES, "image/png")},
        data={"document_type": "PHOTO"},
        headers={"Authorization": f"Bearer {_token_for(owner)}"},
    )
    assert up2.status_code == status.HTTP_201_CREATED

    # Officer lists documents
    list_res = client.get(
        f"/api/claims/{claim.id}/documents",
        headers={"Authorization": f"Bearer {_token_for(ops)}"},
    )
    assert list_res.status_code == status.HTTP_200_OK
    docs = list_res.json()
    assert len(docs) == 2
    assert {d["original_filename"] for d in docs} == {
        "repair_invoice.pdf",
        "damage_photo.png",
    }
    assert {d["document_type"] for d in docs} == {"INVOICE", "PHOTO"}
    for doc_meta in docs:
        assert "id" in doc_meta
        assert doc_meta["claim_id"] == str(claim.id)
        assert doc_meta["size_bytes"] > 0
        assert "uploaded_at" in doc_meta
        # Internal storage details must never be exposed in the list payload
        assert "storage_name" not in doc_meta
        assert "sha256" not in doc_meta

    # Officer downloads the invoice document
    invoice_doc = next(d for d in docs if d["document_type"] == "INVOICE")
    dl_res = client.get(
        f"/api/claims/{claim.id}/documents/{invoice_doc['id']}",
        headers={"Authorization": f"Bearer {_token_for(ops)}"},
    )
    assert dl_res.status_code == status.HTTP_200_OK
    assert dl_res.content == PDF_BYTES
    assert "repair_invoice.pdf" in dl_res.headers["content-disposition"]


def test_document_list_and_download_cross_business_and_missing_checks(
    client, session, business, policy, equipment, claim
):
    owner = _make_user(
        session, "owner-doc-iso@example.com", "POLICYHOLDER", business.id
    )
    other_biz = Business(id=uuid.uuid4(), name="Other Doc Iso Business")
    session.add(other_biz)
    session.flush()
    other_owner = _make_user(
        session, "other-doc-iso@example.com", "POLICYHOLDER", other_biz.id
    )
    ops = _make_user(session, "ops-doc-iso@example.com", "OPS", None)

    second_claim = Claim(
        id=uuid.uuid4(),
        reference="TEST-000002",
        business_id=business.id,
        policy_id=policy.id,
        equipment_id=equipment.id,
        status="SUBMITTED",
        incident_date=date(2026, 10, 2),
        incident_description="Second incident",
        amount_claimed=Decimal("800.00"),
    )
    session.add(second_claim)
    session.flush()

    upload = client.post(
        f"/api/claims/{claim.id}/documents",
        files={"file": ("evidence.pdf", PDF_BYTES, "application/pdf")},
        data={"document_type": "INVOICE"},
        headers={"Authorization": f"Bearer {_token_for(owner)}"},
    )
    doc_id = upload.json()["id"]

    # Unauthenticated list -> 401
    assert (
        client.get(f"/api/claims/{claim.id}/documents").status_code
        == status.HTTP_401_UNAUTHORIZED
    )

    # Cross-business policyholder cannot list or download -> 404
    assert (
        client.get(
            f"/api/claims/{claim.id}/documents",
            headers={"Authorization": f"Bearer {_token_for(other_owner)}"},
        ).status_code
        == status.HTTP_404_NOT_FOUND
    )
    assert (
        client.get(
            f"/api/claims/{claim.id}/documents/{doc_id}",
            headers={"Authorization": f"Bearer {_token_for(other_owner)}"},
        ).status_code
        == status.HTTP_404_NOT_FOUND
    )

    # Requesting a document ID under a different claim returns 404
    wrong_claim_res = client.get(
        f"/api/claims/{second_claim.id}/documents/{doc_id}",
        headers={"Authorization": f"Bearer {_token_for(ops)}"},
    )
    assert wrong_claim_res.status_code == status.HTTP_404_NOT_FOUND
    assert wrong_claim_res.json()["detail"] == "Document not found"

    # Unknown document ID returns 404
    unknown_doc_res = client.get(
        f"/api/claims/{claim.id}/documents/{uuid.uuid4()}",
        headers={"Authorization": f"Bearer {_token_for(ops)}"},
    )
    assert unknown_doc_res.status_code == status.HTTP_404_NOT_FOUND
    assert unknown_doc_res.json()["detail"] == "Document not found"


def test_claim_detail_and_phase2_routes_resolve_both_uuid_and_reference_with_tenant_isolation(
    client, session, business, policy, equipment, claim
):
    _link_equipment(session, policy, equipment)
    _add_billing(session, policy)

    owner = _make_user(
        session, "owner-ref-lookup@example.com", "POLICYHOLDER", business.id
    )
    other_biz = Business(id=uuid.uuid4(), name="Other Ref Lookup Business")
    session.add(other_biz)
    session.flush()
    other_owner = _make_user(
        session, "other-ref-lookup@example.com", "POLICYHOLDER", other_biz.id
    )

    owner_headers = {"Authorization": f"Bearer {_token_for(owner)}"}
    other_headers = {"Authorization": f"Bearer {_token_for(other_owner)}"}

    # Valid access by claim reference as well as UUID
    for identifier in (str(claim.id), claim.reference):
        detail_res = client.get(f"/api/claims/{identifier}", headers=owner_headers)
        assert detail_res.status_code == status.HTTP_200_OK
        assert detail_res.json()["id"] == str(claim.id)
        assert detail_res.json()["reference"] == claim.reference

        verify_res = client.get(
            f"/api/claims/{identifier}/verification", headers=owner_headers
        )
        assert verify_res.status_code == status.HTTP_200_OK
        assert verify_res.json()["claim_id"] == str(claim.id)
        assert verify_res.json()["overall_passed"] is True

        history_res = client.get(
            f"/api/claims/{identifier}/history", headers=owner_headers
        )
        assert history_res.status_code == status.HTTP_200_OK
        assert isinstance(history_res.json(), list)

        docs_res = client.get(
            f"/api/claims/{identifier}/documents", headers=owner_headers
        )
        assert docs_res.status_code == status.HTTP_200_OK
        assert isinstance(docs_res.json(), list)

        # Cross-business denial by both UUID and claim reference
        for suffix in ("", "/verification", "/history", "/documents"):
            denied = client.get(
                f"/api/claims/{identifier}{suffix}", headers=other_headers
            )
            assert denied.status_code == status.HTTP_404_NOT_FOUND
            assert denied.json()["detail"] == "Claim not found"


