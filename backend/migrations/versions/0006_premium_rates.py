"""Create premium_rates table and seed initial rates.

Revision ID: 0006_premium_rates
Revises: 0006
Create Date: 2026-11-04
"""

from decimal import Decimal
from typing import Sequence, Union
import uuid

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0006_premium_rates"
down_revision: Union[str, None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

INITIAL_RATES = [
    # CATEGORY
    {"kind": "CATEGORY", "code": "REFRIGERATION", "value": Decimal("0.0200")},
    {"kind": "CATEGORY", "code": "COOKING", "value": Decimal("0.0180")},
    {"kind": "CATEGORY", "code": "MACHINERY", "value": Decimal("0.0250")},
    {"kind": "CATEGORY", "code": "HVAC", "value": Decimal("0.0150")},
    {"kind": "CATEGORY", "code": "ELECTRICAL", "value": Decimal("0.0220")},
    {"kind": "CATEGORY", "code": "OTHER", "value": Decimal("0.0300")},
    # AGE_BAND
    {"kind": "AGE_BAND", "code": "0_2", "value": Decimal("0.0000")},
    {"kind": "AGE_BAND", "code": "3_5", "value": Decimal("0.1000")},
    {"kind": "AGE_BAND", "code": "6_PLUS", "value": Decimal("0.2500")},
    # COVER
    {"kind": "COVER", "code": "BASIC", "value": Decimal("0.0000")},
    {"kind": "COVER", "code": "STANDARD", "value": Decimal("0.2000")},
    {"kind": "COVER", "code": "COMPREHENSIVE", "value": Decimal("0.4000")},
    # MINIMUM
    {"kind": "MINIMUM", "code": "MINIMUM_PREMIUM", "value": Decimal("500.0000")},
]


def upgrade() -> None:
    premium_rates = op.create_table(
        "premium_rates",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("code", sa.String(length=32), nullable=False),
        sa.Column("value", sa.Numeric(precision=10, scale=4), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("kind", "code", name="uq_premium_rates_kind_code"),
        sa.CheckConstraint(
            "kind IN ('CATEGORY', 'AGE_BAND', 'COVER', 'MINIMUM')",
            name="ck_premium_rates_kind",
        ),
        sa.CheckConstraint("value >= 0", name="ck_premium_rates_value_nonneg"),
    )

    seed_data = [
        {
            "id": uuid.uuid4(),
            "kind": row["kind"],
            "code": row["code"],
            "value": row["value"],
        }
        for row in INITIAL_RATES
    ]
    op.bulk_insert(premium_rates, seed_data)


def downgrade() -> None:
    op.drop_table("premium_rates")

