import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, Date, ForeignKey, Numeric, String, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, created_at_column, uuid_pk
from app.models.enums import BillingStatus


class BillingRecord(Base):
    __tablename__ = "billing_records"
    __table_args__ = (
        CheckConstraint(
            "period_end > period_start", name="ck_billing_records_period_end_after_start"
        ),
        CheckConstraint(
            "amount_due >= 0", name="ck_billing_records_amount_due_nonneg"
        ),
        CheckConstraint(
            "amount_paid >= 0", name="ck_billing_records_amount_paid_nonneg"
        ),
        CheckConstraint(
            f"status IN ({', '.join(repr(s.value) for s in BillingStatus)})",
            name="ck_billing_records_status",
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    policy_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("policies.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    amount_due: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    amount_paid: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False, server_default=text("0"), default=0
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    due_date: Mapped[date] = mapped_column(Date, nullable=False)
    created_at: Mapped[datetime] = created_at_column()
