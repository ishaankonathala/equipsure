from datetime import date, timedelta
from decimal import Decimal
import secrets
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import BillingRecord, Equipment, Policy, PolicyEquipment, PremiumQuote, User
from app.models.enums import BillingStatus, PolicyStatus


class PurchaseError(Exception):
    """Raised when quote purchase fails."""


def generate_unique_policy_number(session: Session) -> str:
    for _ in range(100):
        number = f"EQP-{secrets.token_hex(4).upper()}"
        exists = session.execute(
            select(Policy.id).where(Policy.policy_number == number)
        ).scalar_one_or_none()
        if exists is None:
            return number
    raise PurchaseError("Failed to generate unique policy number")


def purchase_quote(session: Session, quote: PremiumQuote, user: User) -> dict:
    if quote.status != "OPEN":
        raise PurchaseError("Quote has already been purchased")

    policy_number = generate_unique_policy_number(session)
    today = date.today()
    end_date = today + timedelta(days=365)

    policy = Policy(
        id=uuid.uuid4(),
        policy_number=policy_number,
        business_id=quote.business_id,
        status=PolicyStatus.ACTIVE.value,
        start_date=today,
        end_date=end_date,
        premium_amount=quote.total,
        deductible_amount=Decimal("500.00"),
        coverage_limit=quote.sum_insured,
    )
    session.add(policy)
    session.flush()

    equipment = Equipment(
        id=uuid.uuid4(),
        business_id=quote.business_id,
        category=quote.equipment_category,
        description=quote.equipment_description,
    )
    session.add(equipment)
    session.flush()

    policy_equipment = PolicyEquipment(
        policy_id=policy.id,
        equipment_id=equipment.id,
    )
    session.add(policy_equipment)

    billing_record = BillingRecord(
        id=uuid.uuid4(),
        policy_id=policy.id,
        period_start=today,
        period_end=end_date,
        due_date=today,
        amount_due=quote.total,
        amount_paid=quote.total,
        status=BillingStatus.PAID.value,
    )
    session.add(billing_record)

    payment_ref = f"SIM-PAY-{secrets.token_hex(5).upper()}"

    quote.status = "PURCHASED"
    quote.policy_id = policy.id
    session.flush()

    return {
        "quote_id": str(quote.id),
        "policy_id": str(policy.id),
        "policy_number": policy.policy_number,
        "payment_reference": payment_ref,
        "simulated": True,
        "payment_simulated": True,
        "is_simulated": True,
        "status": "PURCHASED",
    }

