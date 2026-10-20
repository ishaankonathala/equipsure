import uuid
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.exc import DBAPIError, IntegrityError

from app.models import Business, Claim, ClaimEvent, Equipment, Policy, User


def _insert_billing(session, policy_id, **overrides):
    params = {
        "id": uuid.uuid4(),
        "policy_id": policy_id,
        "period_start": date(2026, 1, 1),
        "period_end": date(2027, 1, 1),
        "amount_due": Decimal("100.00"),
        "amount_paid": Decimal("0.00"),
        "status": "DUE",
        "due_date": date(2026, 2, 1),
    }
    params.update(overrides)
    session.execute(
        text(
            "INSERT INTO billing_records "
            "(id, policy_id, period_start, period_end, amount_due, amount_paid, status, due_date) "
            "VALUES (:id, :policy_id, :period_start, :period_end, :amount_due, :amount_paid, :status, :due_date)"
        ),
        params,
    )


def _add_claim_event(session, claim, user):
    event = ClaimEvent(
        claim_id=claim.id,
        old_status=None,
        new_status="SUBMITTED",
        source="POLICYHOLDER",
        actor_user_id=user.id,
        explanation="Claim submitted",
    )
    session.add(event)
    session.flush()
    return event


def test_test_database_is_migrated(session):
    version = session.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
    assert version == "0004"


def test_user_rejects_invalid_role(session, business):
    with pytest.raises(IntegrityError):
        with session.begin_nested():
            session.add(User(
                id=uuid.uuid4(), email="bad-role@example.com", password_hash="x",
                full_name="Bad Role", role="ADMINX", business_id=business.id, is_active=True,
            ))
            session.flush()


def test_user_rejects_duplicate_email(session, business):
    session.add(User(
        id=uuid.uuid4(), email="dup@example.com", password_hash="x",
        full_name="First", role="POLICYHOLDER", business_id=business.id, is_active=True,
    ))
    session.flush()
    with pytest.raises(IntegrityError):
        with session.begin_nested():
            session.add(User(
                id=uuid.uuid4(), email="dup@example.com", password_hash="x",
                full_name="Second", role="POLICYHOLDER", business_id=business.id, is_active=True,
            ))
            session.flush()


def test_user_rejects_uppercase_email(session, business):
    with pytest.raises(IntegrityError):
        with session.begin_nested():
            session.add(User(
                id=uuid.uuid4(), email="Upper@Example.com", password_hash="x",
                full_name="Upper", role="POLICYHOLDER", business_id=business.id, is_active=True,
            ))
            session.flush()


def test_policyholder_requires_business(session):
    with pytest.raises(IntegrityError):
        with session.begin_nested():
            session.add(User(
                id=uuid.uuid4(), email="nobiz@example.com", password_hash="x",
                full_name="No Biz", role="POLICYHOLDER", business_id=None, is_active=True,
            ))
            session.flush()


def test_ops_user_may_have_no_business(session):
    session.add(User(
        id=uuid.uuid4(), email="ops@example.com", password_hash="x",
        full_name="Ops", role="OPS", business_id=None, is_active=True,
    ))
    session.flush()


def test_policy_rejects_end_before_start(session, business):
    with pytest.raises(IntegrityError):
        with session.begin_nested():
            session.add(Policy(
                id=uuid.uuid4(), policy_number="BAD-DATES", business_id=business.id,
                status="ACTIVE", start_date=date(2027, 1, 1), end_date=date(2026, 1, 1),
                premium_amount=Decimal("100.00"), deductible_amount=Decimal("500.00"),
                coverage_limit=Decimal("50000.00"),
            ))
            session.flush()


def test_equipment_rejects_invalid_category(session, business):
    with pytest.raises(IntegrityError):
        with session.begin_nested():
            session.add(Equipment(
                id=uuid.uuid4(), business_id=business.id,
                category="FURNITURE", description="Not allowed category",
            ))
            session.flush()


def test_equipment_rejects_negative_purchase_value(session, business):
    with pytest.raises(IntegrityError):
        with session.begin_nested():
            session.add(Equipment(
                id=uuid.uuid4(), business_id=business.id,
                category="REFRIGERATION", description="Negative value",
                purchase_value=Decimal("-1.00"),
            ))
            session.flush()


def test_business_delete_blocked_when_equipment_exists(session, business, equipment):
    with pytest.raises(IntegrityError):
        with session.begin_nested():
            session.execute(
                text("DELETE FROM businesses WHERE id = :id"), {"id": business.id}
            )


def test_claim_rejects_invalid_status(session, business, policy, equipment):
    with pytest.raises(IntegrityError):
        with session.begin_nested():
            session.add(Claim(
                id=uuid.uuid4(), reference="BAD-STATUS-1", business_id=business.id,
                policy_id=policy.id, equipment_id=equipment.id, status="DRAFT",
                incident_date=date(2026, 10, 1), incident_description="x",
                amount_claimed=Decimal("10.00"),
            ))
            session.flush()


def test_claim_rejects_negative_amount(session, business, policy, equipment):
    with pytest.raises(IntegrityError):
        with session.begin_nested():
            session.add(Claim(
                id=uuid.uuid4(), reference="BAD-AMOUNT-1", business_id=business.id,
                policy_id=policy.id, equipment_id=equipment.id, status="SUBMITTED",
                incident_date=date(2026, 10, 1), incident_description="x",
                amount_claimed=Decimal("-10.00"),
            ))
            session.flush()


def test_claim_event_insert_succeeds(session, claim, policyholder_user):
    event = _add_claim_event(session, claim, policyholder_user)
    assert event.id is not None


def test_claim_event_update_is_rejected(session, claim, policyholder_user):
    event = _add_claim_event(session, claim, policyholder_user)
    with pytest.raises(DBAPIError) as exc_info:
        with session.begin_nested():
            session.execute(
                text("UPDATE claim_events SET explanation = 'tampered' WHERE id = :id"),
                {"id": event.id},
            )
    assert "claim_events is append-only" in str(exc_info.value)


def test_claim_event_delete_is_rejected(session, claim, policyholder_user):
    event = _add_claim_event(session, claim, policyholder_user)
    with pytest.raises(DBAPIError) as exc_info:
        with session.begin_nested():
            session.execute(
                text("DELETE FROM claim_events WHERE id = :id"), {"id": event.id}
            )
    assert "claim_events is append-only" in str(exc_info.value)


def test_billing_rejects_invalid_status(session, policy):
    with pytest.raises(IntegrityError):
        with session.begin_nested():
            _insert_billing(session, policy.id, status="PENDING")


def test_billing_rejects_period_end_before_start(session, policy):
    with pytest.raises(IntegrityError):
        with session.begin_nested():
            _insert_billing(
                session, policy.id,
                period_start=date(2027, 1, 1), period_end=date(2026, 1, 1),
            )


def test_billing_record_has_no_card_columns(session):
    columns = [c["name"].lower() for c in inspect(session.connection()).get_columns("billing_records")]
    for forbidden in ("card", "bank", "account"):
        assert not any(forbidden in name for name in columns), (
            f"billing_records must not contain payment-instrument columns: {columns}"
        )