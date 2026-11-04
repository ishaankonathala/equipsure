import uuid
from decimal import Decimal

from sqlalchemy import CheckConstraint, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, uuid_pk


class PremiumRate(Base):
    __tablename__ = "premium_rates"
    __table_args__ = (
        UniqueConstraint("kind", "code", name="uq_premium_rates_kind_code"),
        CheckConstraint(
            "kind IN ('CATEGORY', 'AGE_BAND', 'COVER', 'MINIMUM')",
            name="ck_premium_rates_kind",
        ),
        CheckConstraint("value >= 0", name="ck_premium_rates_value_nonneg"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    code: Mapped[str] = mapped_column(String(32), nullable=False)
    value: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=False)

