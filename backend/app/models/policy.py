import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, Date, ForeignKey, Numeric, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, created_at_column, uuid_pk
from app.models.enums import PolicyStatus


class Policy(Base):
    __tablename__ = "policies"
    __table_args__ = (
        CheckConstraint(
            f"status IN ({', '.join(repr(s.value) for s in PolicyStatus)})",
            name="ck_policies_status",
        ),
        CheckConstraint("end_date > start_date", name="ck_policies_end_after_start"),
        CheckConstraint("premium_amount >= 0", name="ck_policies_premium_amount_nonneg"),
        CheckConstraint(
            "deductible_amount >= 0", name="ck_policies_deductible_amount_nonneg"
        ),
        CheckConstraint(
            "coverage_limit >= 0", name="ck_policies_coverage_limit_nonneg"
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    policy_number: Mapped[str] = mapped_column(String(40), nullable=False, unique=True)
    business_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("businesses.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    premium_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    deductible_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    coverage_limit: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    created_at: Mapped[datetime] = created_at_column()


class PolicyEquipment(Base):
    __tablename__ = "policy_equipment"

    policy_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("policies.id", ondelete="CASCADE"),
        primary_key=True,
    )
    equipment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("equipment.id", ondelete="RESTRICT"),
        primary_key=True,
        index=True,
    )
