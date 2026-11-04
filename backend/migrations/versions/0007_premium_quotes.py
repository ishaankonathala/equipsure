"""Create premium_quotes table.

Revision ID: 0007
Revises: 0006_premium_rates
Create Date: 2026-11-04
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0007"
down_revision: Union[str, None] = "0006_premium_rates"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "premium_quotes",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("business_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("equipment_category", sa.String(length=50), nullable=False),
        sa.Column("equipment_description", sa.String(length=200), nullable=False),
        sa.Column("sum_insured", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("age_years", sa.Integer(), nullable=False),
        sa.Column("cover", sa.String(length=50), nullable=False),
        sa.Column("total", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("lines", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("policy_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["business_id"],
            ["businesses.id"],
            name="fk_premium_quotes_business_id_businesses",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
            name="fk_premium_quotes_created_by_user_id_users",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["policy_id"],
            ["policies.id"],
            name="fk_premium_quotes_policy_id_policies",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "status IN ('OPEN', 'PURCHASED')",
            name="ck_premium_quotes_status",
        ),
        sa.CheckConstraint(
            "sum_insured > 0",
            name="ck_premium_quotes_sum_insured_positive",
        ),
        sa.CheckConstraint(
            "age_years >= 0",
            name="ck_premium_quotes_age_years_nonneg",
        ),
        sa.CheckConstraint(
            "total >= 0",
            name="ck_premium_quotes_total_nonneg",
        ),
    )
    op.create_index(
        "ix_premium_quotes_business_id",
        "premium_quotes",
        ["business_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_premium_quotes_business_id", table_name="premium_quotes")
    op.drop_table("premium_quotes")

