import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import CheckConstraint, ForeignKey, Integer, Numeric, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, created_at_column, uuid_pk


class PremiumQuote(Base):
    __tablename__ = "premium_quotes"
    __table_args__ = (
        CheckConstraint(
            "status IN ('OPEN', 'PURCHASED')",
            name="ck_premium_quotes_status",
        ),
        CheckConstraint(
            "sum_insured > 0",
            name="ck_premium_quotes_sum_insured_positive",
        ),
        CheckConstraint(
            "age_years >= 0",
            name="ck_premium_quotes_age_years_nonneg",
        ),
        CheckConstraint(
            "total >= 0",
            name="ck_premium_quotes_total_nonneg",
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    business_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("businesses.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    equipment_category: Mapped[str] = mapped_column(String(50), nullable=False)
    equipment_description: Mapped[str] = mapped_column(String(200), nullable=False)
    sum_insured: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    age_years: Mapped[int] = mapped_column(Integer, nullable=False)
    cover: Mapped[str] = mapped_column(String(50), nullable=False)
    total: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    lines: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="OPEN")
    policy_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("policies.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = created_at_column()

