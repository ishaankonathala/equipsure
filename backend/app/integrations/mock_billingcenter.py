from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.integrations.base import BILLINGCENTER_SOURCE, IntegrationResult
from app.models import BillingRecord, Policy
from app.models.enums import BillingStatus


class MockBillingCenter:
    source = BILLINGCENTER_SOURCE

    def __init__(self, session: Session) -> None:
        self.session = session

    def get_account_status(
        self, policy_number: str, on_date: date
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

        records = self.session.execute(
            select(BillingRecord)
            .where(BillingRecord.policy_id == policy.id)
            .order_by(BillingRecord.period_start)
        ).scalars().all()
        if not records:
            return IntegrationResult(
                source=self.source,
                ok=False,
                reason="No billing records for policy",
            )

        record_data = []
        statuses = []
        for record in records:
            if record.amount_paid >= record.amount_due:
                effective_status = BillingStatus.PAID.value
            elif record.due_date < on_date:
                effective_status = BillingStatus.OVERDUE.value
            else:
                effective_status = BillingStatus.DUE.value

            statuses.append(effective_status)
            record_data.append(
                {
                    "period_start": record.period_start.isoformat(),
                    "period_end": record.period_end.isoformat(),
                    "due_date": record.due_date.isoformat(),
                    "amount_due": str(record.amount_due),
                    "amount_paid": str(record.amount_paid),
                    "status": effective_status,
                }
            )

        if BillingStatus.OVERDUE.value in statuses:
            account_status = BillingStatus.OVERDUE.value
        elif BillingStatus.DUE.value in statuses:
            account_status = BillingStatus.DUE.value
        else:
            account_status = BillingStatus.PAID.value

        return IntegrationResult(
            source=self.source,
            ok=True,
            data={
                "policy_number": policy_number,
                "account_status": account_status,
                "as_of": on_date.isoformat(),
                "records": record_data,
            },
        )