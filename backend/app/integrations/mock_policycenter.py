import uuid
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.integrations.base import IntegrationResult, POLICYCENTER_SOURCE
from app.models import Policy, PolicyEquipment
from app.models.enums import PolicyStatus


class MockPolicyCenter:
    source = POLICYCENTER_SOURCE

    def __init__(self, session: Session) -> None:
        self.session = session

    def get_policy(self, policy_number: str) -> IntegrationResult:
        policy = self.session.execute(
            select(Policy).where(Policy.policy_number == policy_number)
        ).scalar_one_or_none()
        if policy is None:
            return IntegrationResult(
                source=self.source,
                ok=False,
                reason="Policy not found",
            )

        return IntegrationResult(
            source=self.source,
            ok=True,
            data={
                "policy_number": policy.policy_number,
                "status": policy.status,
                "start_date": policy.start_date.isoformat(),
                "end_date": policy.end_date.isoformat(),
                "coverage_limit": str(policy.coverage_limit),
                "deductible_amount": str(policy.deductible_amount),
                "business_id": str(policy.business_id),
            },
        )

    def check_validity(self, policy_number: str, on_date: date) -> IntegrationResult:
        policy = self.session.execute(
            select(Policy).where(Policy.policy_number == policy_number)
        ).scalar_one_or_none()
        if policy is None:
            return IntegrationResult(
                source=self.source,
                ok=False,
                reason="Policy not found",
            )
        if policy.status != PolicyStatus.ACTIVE.value:
            return IntegrationResult(
                source=self.source,
                ok=False,
                reason="Policy is not active",
            )
        if on_date < policy.start_date or on_date > policy.end_date:
            return IntegrationResult(
                source=self.source,
                ok=False,
                reason="Incident date is outside the policy period",
            )

        return IntegrationResult(
            source=self.source,
            ok=True,
            data={"valid_on": on_date.isoformat()},
        )

    def is_equipment_covered(
        self, policy_number: str, equipment_id: uuid.UUID
    ) -> IntegrationResult:
        policy = self.session.execute(
            select(Policy).where(Policy.policy_number == policy_number)
        ).scalar_one_or_none()
        if policy is None:
            return IntegrationResult(
                source=self.source,
                ok=False,
                reason="Policy not found",
            )

        link = self.session.execute(
            select(PolicyEquipment).where(
                PolicyEquipment.policy_id == policy.id,
                PolicyEquipment.equipment_id == equipment_id,
            )
        ).scalar_one_or_none()
        if link is None:
            return IntegrationResult(
                source=self.source,
                ok=False,
                reason="Equipment is not covered by this policy",
            )

        return IntegrationResult(
            source=self.source,
            ok=True,
            data={"equipment_id": str(equipment_id)},
        )