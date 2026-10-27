from datetime import datetime
from decimal import Decimal
import uuid

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Numeric,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, created_at_column, uuid_pk
from app.models.enums import SettlementCurrency, SettlementStatus


class ClaimSettlement(Base):
    __tablename__ = "claim_settlements"
    __table_args__ = (
        CheckConstraint(
            "amount > 0",
            name="ck_claim_settlements_amount_positive",
        ),
        CheckConstraint(
            f"currency IN ({', '.join(repr(c.value) for c in SettlementCurrency)})",
            name="ck_claim_settlements_currency",
        ),
        CheckConstraint(
            f"status IN ({', '.join(repr(s.value) for s in SettlementStatus)})",
            name="ck_claim_settlements_status",
        ),
        CheckConstraint(
            "(status = 'SETTLED') = (settled_at IS NOT NULL)",
            name="ck_claim_settlements_settled_at",
        ),
        CheckConstraint(
            "length(trim(settlement_reference)) > 0",
            name="ck_claim_settlements_ref_nonblank",
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    claim_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("claims.id", ondelete="RESTRICT"),
        nullable=False,
        unique=True,
        index=True,
    )
    settlement_reference: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        unique=True,
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(
        String(3),
        nullable=False,
        default=SettlementCurrency.INR.value,
        server_default=text("'INR'"),
    )
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    settled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

