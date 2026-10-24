import uuid
from datetime import date

from app.integrations.mock_policycenter import MockPolicyCenter
from app.models import Equipment, PolicyEquipment


def _link_equipment(session, policy, equipment):
    session.add(
        PolicyEquipment(policy_id=policy.id, equipment_id=equipment.id)
    )
    session.flush()


def test_get_policy_returns_policy_data(session, policy):
    result = MockPolicyCenter(session).get_policy("TEST-POL-1")

    assert result.ok is True
    assert result.data["policy_number"] == "TEST-POL-1"
    assert result.data["status"] == "ACTIVE"


def test_unknown_policy_is_not_found(session):
    service = MockPolicyCenter(session)

    policy_result = service.get_policy("NOPE")
    validity_result = service.check_validity("NOPE", date(2026, 6, 1))

    assert policy_result.ok is False
    assert policy_result.reason == "Policy not found"
    assert validity_result.ok is False
    assert validity_result.reason == "Policy not found"


def test_valid_date_inside_period(session, policy):
    result = MockPolicyCenter(session).check_validity(
        policy.policy_number, date(2026, 6, 1)
    )

    assert result.ok is True
    assert result.data == {"valid_on": "2026-06-01"}


def test_boundary_dates_are_inclusive(session, policy):
    service = MockPolicyCenter(session)

    start_result = service.check_validity(policy.policy_number, date(2026, 1, 1))
    end_result = service.check_validity(policy.policy_number, date(2027, 1, 1))

    assert start_result.ok is True
    assert end_result.ok is True


def test_expired_date_is_rejected(session, policy):
    result = MockPolicyCenter(session).check_validity(
        policy.policy_number, date(2027, 1, 2)
    )

    assert result.ok is False
    assert result.reason == "Incident date is outside the policy period"


def test_date_before_start_is_rejected(session, policy):
    result = MockPolicyCenter(session).check_validity(
        policy.policy_number, date(2025, 12, 31)
    )

    assert result.ok is False
    assert result.reason == "Incident date is outside the policy period"


def test_inactive_policy_is_rejected(session, policy):
    policy.status = "CANCELLED"
    session.flush()

    result = MockPolicyCenter(session).check_validity(
        policy.policy_number, date(2026, 6, 1)
    )

    assert result.ok is False
    assert result.reason == "Policy is not active"


def test_covered_equipment_is_accepted(session, policy, equipment):
    _link_equipment(session, policy, equipment)

    result = MockPolicyCenter(session).is_equipment_covered(
        policy.policy_number, equipment.id
    )

    assert result.ok is True
    assert result.data == {"equipment_id": str(equipment.id)}


def test_uncovered_equipment_is_rejected(
    session, business, policy, equipment
):
    _link_equipment(session, policy, equipment)
    uncovered = Equipment(
        id=uuid.uuid4(),
        business_id=business.id,
        category="COOKING",
        description="Uncovered test oven",
    )
    session.add(uncovered)
    session.flush()

    result = MockPolicyCenter(session).is_equipment_covered(
        policy.policy_number, uncovered.id
    )

    assert result.ok is False
    assert result.reason == "Equipment is not covered by this policy"