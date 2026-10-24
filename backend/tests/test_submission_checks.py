import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select

from app.integrations.submission_checks import run_submission_checks
from app.models import BillingRecord, Claim, Equipment, PolicyEquipment
from app.models.enums import BillingStatus


def _link_equipment(session, policy, equipment):
    session.add(
        PolicyEquipment(policy_id=policy.id, equipment_id=equipment.id)
    )
    session.flush()


def _add_billing_record(
    session,
    policy,
    *,
    amount_paid=Decimal("1200.00"),
    due_date=date(2026, 2, 1),
):
    record = BillingRecord(
        id=uuid.uuid4(),
        policy_id=policy.id,
        period_start=date(2026, 1, 1),
        period_end=date(2027, 1, 1),
        amount_due=Decimal("1200.00"),
        amount_paid=amount_paid,
        status=BillingStatus.DUE.value,
        due_date=due_date,
    )
    session.add(record)
    session.flush()
    return record


def test_all_checks_pass_accepts(session, business, policy, equipment):
    _link_equipment(session, policy, equipment)
    _add_billing_record(session, policy)

    decision = run_submission_checks(
        session,
        policy.policy_number,
        equipment.id,
        date(2026, 6, 1),
        date(2026, 6, 1),
    )

    assert decision.accepted is True
    assert decision.failures == ()


def test_sources_are_labelled(session, business, policy, equipment):
    _link_equipment(session, policy, equipment)
    _add_billing_record(session, policy)

    decision = run_submission_checks(
        session,
        policy.policy_number,
        equipment.id,
        date(2026, 6, 1),
        date(2026, 6, 1),
    )

    assert decision.sources == (
        "MOCK_POLICYCENTER",
        "MOCK_POLICYCENTER",
        "MOCK_BILLINGCENTER",
    )


def test_uncovered_equipment_rejects(
    session, business, policy, equipment
):
    _add_billing_record(session, policy)
    uncovered = Equipment(
        id=uuid.uuid4(),
        business_id=business.id,
        category="COOKING",
        description="Uncovered test oven",
    )
    session.add(uncovered)
    session.flush()

    decision = run_submission_checks(
        session,
        policy.policy_number,
        uncovered.id,
        date(2026, 6, 1),
        date(2026, 6, 1),
    )

    assert decision.accepted is False
    assert "Equipment is not covered by this policy" in decision.failures


def test_incident_outside_period_rejects(
    session, business, policy, equipment
):
    _link_equipment(session, policy, equipment)
    _add_billing_record(session, policy)

    decision = run_submission_checks(
        session,
        policy.policy_number,
        equipment.id,
        date(2027, 6, 1),
        date(2026, 6, 1),
    )

    assert decision.accepted is False
    assert "Incident date is outside the policy period" in decision.failures


def test_overdue_account_rejects(session, business, policy, equipment):
    _link_equipment(session, policy, equipment)
    _add_billing_record(
        session,
        policy,
        amount_paid=Decimal("0.00"),
        due_date=date(2026, 2, 1),
    )

    decision = run_submission_checks(
        session,
        policy.policy_number,
        equipment.id,
        date(2026, 6, 1),
        date(2026, 6, 1),
    )

    assert decision.accepted is False
    assert "Policy account is overdue" in decision.failures


def test_all_reasons_reported_together(session, business, policy, equipment):
    uncovered = Equipment(
        id=uuid.uuid4(),
        business_id=business.id,
        category="COOKING",
        description="Uncovered test oven",
    )
    session.add(uncovered)
    session.flush()
    _add_billing_record(
        session,
        policy,
        amount_paid=Decimal("0.00"),
        due_date=date(2026, 2, 1),
    )

    decision = run_submission_checks(
        session,
        policy.policy_number,
        uncovered.id,
        date(2027, 6, 1),
        date(2026, 6, 1),
    )

    expected = (
        "Incident date is outside the policy period",
        "Equipment is not covered by this policy",
        "Policy account is overdue",
    )
    assert decision.accepted is False
    assert all(reason in decision.failures for reason in expected)
    assert all(decision.failures.count(reason) == 1 for reason in expected)


def test_unknown_policy_rejects(session, equipment):
    decision = run_submission_checks(
        session,
        "NOPE",
        equipment.id,
        date(2026, 6, 1),
        date(2026, 6, 1),
    )

    assert decision.accepted is False
    assert "Policy not found" in decision.failures


def test_no_claim_is_created(session, business, policy, equipment, claim):
    before = session.execute(select(func.count()).select_from(Claim)).scalar_one()

    run_submission_checks(
        session,
        policy.policy_number,
        equipment.id,
        date(2026, 6, 1),
        date(2026, 6, 1),
    )

    after = session.execute(select(func.count()).select_from(Claim)).scalar_one()
    assert after == before


def test_unknown_policy_lists_reason_once(session, business, equipment):
    decision = run_submission_checks(
        session,
        "NOPE",
        equipment.id,
        date(2026, 6, 1),
        date(2026, 6, 1),
    )
    assert decision.accepted is False
    assert decision.failures.count("Policy not found") == 1