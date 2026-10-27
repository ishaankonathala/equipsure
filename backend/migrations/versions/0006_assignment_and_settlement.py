"""Add officer assignment columns on claims and claim_settlements table.

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-27
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "claims",
        sa.Column("assigned_officer_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "claims",
        sa.Column("assigned_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_claims_assigned_officer_id_users",
        "claims",
        "users",
        ["assigned_officer_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index(
        "ix_claims_assigned_officer_id",
        "claims",
        ["assigned_officer_id"],
        unique=False,
    )
    op.create_check_constraint(
        "ck_claims_assignment_pair",
        "claims",
        "(assigned_officer_id IS NULL) = (assigned_at IS NULL)",
    )

    op.create_table(
        "claim_settlements",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("claim_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("settlement_reference", sa.String(length=30), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column(
            "currency",
            sa.String(length=3),
            server_default=sa.text("'INR'"),
            nullable=False,
        ),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("settled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "amount > 0",
            name="ck_claim_settlements_amount_positive",
        ),
        sa.CheckConstraint(
            "currency IN ('INR', 'USD', 'EUR', 'GBP')",
            name="ck_claim_settlements_currency",
        ),
        sa.CheckConstraint(
            "status IN ('IN_PROGRESS', 'SETTLED')",
            name="ck_claim_settlements_status",
        ),
        sa.CheckConstraint(
            "(status = 'SETTLED') = (settled_at IS NOT NULL)",
            name="ck_claim_settlements_settled_at",
        ),
        sa.CheckConstraint(
            "length(trim(settlement_reference)) > 0",
            name="ck_claim_settlements_ref_nonblank",
        ),
        sa.ForeignKeyConstraint(
            ["claim_id"],
            ["claims.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("claim_id", name="uq_claim_settlements_claim_id"),
        sa.UniqueConstraint(
            "settlement_reference",
            name="uq_claim_settlements_settlement_reference",
        ),
    )
    op.create_index(
        "ix_claim_settlements_claim_id",
        "claim_settlements",
        ["claim_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_claim_settlements_claim_id", table_name="claim_settlements")
    op.drop_table("claim_settlements")

    op.drop_constraint("ck_claims_assignment_pair", "claims", type_="check")
    op.drop_index("ix_claims_assigned_officer_id", table_name="claims")
    op.drop_constraint(
        "fk_claims_assigned_officer_id_users", "claims", type_="foreignkey"
    )
    op.drop_column("claims", "assigned_at")
    op.drop_column("claims", "assigned_officer_id")

