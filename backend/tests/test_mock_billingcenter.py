import uuid
from datetime import date
from decimal import Decimal

from app.integrations.mock_billingcenter import MockBillingCenter
from app.models import BillingRecord
from app.models.enums import BillingStatus


def _add_billing_record(
    session,
    policy,
    *,
    period_start=date(2026, 1, 1),
    period_end=date(2027, 1, 1),
    amount_due=Decimal("1200.00"),
    amount_paid=Decimal("0.00"),
    due_date=date(2026, 2, 1),
):
    record = BillingRecord(
        id=uuid.uuid4(),
        policy_id=policy.id,
        period_start=period_start,
        period_end=period_end,
        amount_due=amount_due,
        amount_paid=amount_paid,
        status=BillingStatus.DUE.value,
        due_date=due_date,
    )
    session.add(record)
    session.flush()
    return record


def test_unknown_policy_is_not_found(session, business, policy):
    service = MockBillingCenter(session)

    result = service.get_account_status("NOPE", date(2026, 6, 1))

    assert result.ok is False
    assert result.reason == "Policy not found"


def test_no_records_is_reported(session, business, policy):
    result = MockBillingCenter(session).get_account_status(
        policy.policy_number, date(2026, 6, 1)
    )

    assert result.ok is False
    assert result.reason == "No billing records for policy"


def test_paid_record_is_paid(session, business, policy):
    _add_billing_record(
        session,
        policy,
        amount_paid=Decimal("1200.00"),
        due_date=date(2026, 2, 1),
    )

    result = MockBillingCenter(session).get_account_status(
        policy.policy_number, date(2026, 6, 1)
    )

    assert result.ok is True
    assert result.data["account_status"] == "PAID"
    assert result.data["records"][0]["status"] == "PAID"


def test_unpaid_before_due_is_due(session, business, policy):
    _add_billing_record(session, policy, due_date=date(2026, 7, 1))

    result = MockBillingCenter(session).get_account_status(
        policy.policy_number, date(2026, 6, 1)
    )

    assert result.data["account_status"] == "DUE"
    assert result.data["records"][0]["status"] == "DUE"


def test_unpaid_after_due_is_overdue(session, business, policy):
    _add_billing_record(session, policy, due_date=date(2026, 2, 1))

    result = MockBillingCenter(session).get_account_status(
        policy.policy_number, date(2026, 6, 1)
    )

    assert result.data["account_status"] == "OVERDUE"
    assert result.data["records"][0]["status"] == "OVERDUE"


def test_due_date_equal_to_as_of_is_not_overdue(session, business, policy):
    _add_billing_record(session, policy, due_date=date(2026, 6, 1))

    result = MockBillingCenter(session).get_account_status(
        policy.policy_number, date(2026, 6, 1)
    )

    assert result.data["account_status"] == "DUE"
    assert result.data["records"][0]["status"] == "DUE"


def test_any_overdue_record_makes_account_overdue(session, business, policy):
    _add_billing_record(
        session,
        policy,
        period_start=date(2026, 1, 1),
        period_end=date(2026, 7, 1),
        amount_paid=Decimal("1200.00"),
        due_date=date(2026, 2, 1),
    )
    _add_billing_record(
        session,
        policy,
        period_start=date(2026, 7, 1),
        period_end=date(2027, 1, 1),
        amount_paid=Decimal("0.00"),
        due_date=date(2026, 3, 1),
    )

    result = MockBillingCenter(session).get_account_status(
        policy.policy_number, date(2026, 6, 1)
    )

    assert result.data["account_status"] == "OVERDUE"
    assert [record["status"] for record in result.data["records"]] == [
        "PAID",
        "OVERDUE",
    ]


def test_money_values_are_strings(session, business, policy):
    _add_billing_record(session, policy)

    result = MockBillingCenter(session).get_account_status(
        policy.policy_number, date(2026, 6, 1)
    )

    assert isinstance(result.data["records"][0]["amount_due"], str)
    assert isinstance(result.data["records"][0]["amount_paid"], str)