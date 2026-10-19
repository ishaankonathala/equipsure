"""Core schema: businesses, users, equipment, policies, billing, claims.

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-20
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "businesses",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("full_name", sa.String(length=200), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("business_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "is_active",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("email = lower(email)", name="ck_users_email_lower"),
        sa.CheckConstraint(
            "role IN ('POLICYHOLDER', 'OPS', 'ADMIN')",
            name="ck_users_role",
        ),
        sa.CheckConstraint(
            "role <> 'POLICYHOLDER' OR business_id IS NOT NULL",
            name="ck_users_policyholder_has_business",
        ),
        sa.ForeignKeyConstraint(
            ["business_id"],
            ["businesses.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
    )
    op.create_index("ix_users_business_id", "users", ["business_id"], unique=False)

    op.create_table(
        "equipment",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("business_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("category", sa.String(length=50), nullable=False),
        sa.Column("description", sa.String(length=200), nullable=False),
        sa.Column("serial_number", sa.String(length=100), nullable=True),
        sa.Column("purchase_date", sa.Date(), nullable=True),
        sa.Column("purchase_value", sa.Numeric(12, 2), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "category IN ("
            "'REFRIGERATION', 'COOKING', 'MACHINERY', 'HVAC', 'ELECTRICAL', 'OTHER'"
            ")",
            name="ck_equipment_category",
        ),
        sa.CheckConstraint(
            "purchase_value IS NULL OR purchase_value >= 0",
            name="ck_equipment_purchase_value_nonneg",
        ),
        sa.ForeignKeyConstraint(
            ["business_id"],
            ["businesses.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_equipment_business_id", "equipment", ["business_id"], unique=False
    )

    op.create_table(
        "policies",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("policy_number", sa.String(length=40), nullable=False),
        sa.Column("business_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("premium_amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("deductible_amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("coverage_limit", sa.Numeric(12, 2), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('ACTIVE', 'CANCELLED', 'EXPIRED')",
            name="ck_policies_status",
        ),
        sa.CheckConstraint(
            "end_date > start_date",
            name="ck_policies_end_after_start",
        ),
        sa.CheckConstraint(
            "premium_amount >= 0",
            name="ck_policies_premium_amount_nonneg",
        ),
        sa.CheckConstraint(
            "deductible_amount >= 0",
            name="ck_policies_deductible_amount_nonneg",
        ),
        sa.CheckConstraint(
            "coverage_limit >= 0",
            name="ck_policies_coverage_limit_nonneg",
        ),
        sa.ForeignKeyConstraint(
            ["business_id"],
            ["businesses.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("policy_number"),
    )
    op.create_index(
        "ix_policies_business_id", "policies", ["business_id"], unique=False
    )

    op.create_table(
        "policy_equipment",
        sa.Column("policy_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("equipment_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["equipment_id"],
            ["equipment.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["policy_id"],
            ["policies.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("policy_id", "equipment_id"),
    )
    op.create_index(
        "ix_policy_equipment_equipment_id",
        "policy_equipment",
        ["equipment_id"],
        unique=False,
    )

    op.create_table(
        "billing_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("policy_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("amount_due", sa.Numeric(12, 2), nullable=False),
        sa.Column(
            "amount_paid",
            sa.Numeric(12, 2),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "period_end > period_start",
            name="ck_billing_records_period_end_after_start",
        ),
        sa.CheckConstraint(
            "amount_due >= 0",
            name="ck_billing_records_amount_due_nonneg",
        ),
        sa.CheckConstraint(
            "amount_paid >= 0",
            name="ck_billing_records_amount_paid_nonneg",
        ),
        sa.CheckConstraint(
            "status IN ('PAID', 'DUE', 'OVERDUE')",
            name="ck_billing_records_status",
        ),
        sa.ForeignKeyConstraint(
            ["policy_id"],
            ["policies.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_billing_records_policy_id",
        "billing_records",
        ["policy_id"],
        unique=False,
    )

    op.create_table(
        "claims",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("reference", sa.String(length=20), nullable=False),
        sa.Column("business_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("policy_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("equipment_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("incident_date", sa.Date(), nullable=False),
        sa.Column("incident_description", sa.Text(), nullable=False),
        sa.Column("amount_claimed", sa.Numeric(12, 2), nullable=False),
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
            "status IN ("
            "'SUBMITTED', 'UNDER_VERIFICATION', 'DOCUMENTS_REQUIRED', "
            "'UNDER_REVIEW', 'INVESTIGATION_ASSIGNED', 'DECISION_PENDING', "
            "'APPROVED', 'REJECTED', 'SETTLEMENT_IN_PROGRESS', 'SETTLED', "
            "'CLOSED', 'WITHDRAWN'"
            ")",
            name="ck_claims_status",
        ),
        sa.CheckConstraint(
            "amount_claimed >= 0",
            name="ck_claims_amount_claimed_nonneg",
        ),
        sa.ForeignKeyConstraint(
            ["business_id"],
            ["businesses.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["equipment_id"],
            ["equipment.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["policy_id"],
            ["policies.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("reference"),
    )
    op.create_index("ix_claims_business_id", "claims", ["business_id"], unique=False)
    op.create_index(
        "ix_claims_equipment_id", "claims", ["equipment_id"], unique=False
    )
    op.create_index("ix_claims_policy_id", "claims", ["policy_id"], unique=False)

    op.create_table(
        "claim_events",
        sa.Column(
            "id",
            sa.BigInteger(),
            sa.Identity(always=False),
            nullable=False,
        ),
        sa.Column("claim_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("old_status", sa.String(length=30), nullable=True),
        sa.Column("new_status", sa.String(length=30), nullable=False),
        sa.Column("source", sa.String(length=20), nullable=False),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "new_status IN ("
            "'SUBMITTED', 'UNDER_VERIFICATION', 'DOCUMENTS_REQUIRED', "
            "'UNDER_REVIEW', 'INVESTIGATION_ASSIGNED', 'DECISION_PENDING', "
            "'APPROVED', 'REJECTED', 'SETTLEMENT_IN_PROGRESS', 'SETTLED', "
            "'CLOSED', 'WITHDRAWN'"
            ")",
            name="ck_claim_events_new_status",
        ),
        sa.CheckConstraint(
            "source IN ('POLICYHOLDER', 'OPS', 'SYSTEM', 'ADMIN')",
            name="ck_claim_events_source",
        ),
        sa.ForeignKeyConstraint(
            ["actor_user_id"],
            ["users.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["claim_id"],
            ["claims.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_claim_events_claim_id", "claim_events", ["claim_id"], unique=False
    )

    op.execute(
        """
        CREATE FUNCTION forbid_claim_event_change() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'claim_events is append-only';
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER claim_events_no_update_delete
        BEFORE UPDATE OR DELETE ON claim_events
        FOR EACH ROW EXECUTE FUNCTION forbid_claim_event_change();
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS claim_events_no_update_delete ON claim_events;")
    op.execute("DROP FUNCTION IF EXISTS forbid_claim_event_change();")

    op.drop_index("ix_claim_events_claim_id", table_name="claim_events")
    op.drop_table("claim_events")

    op.drop_index("ix_claims_policy_id", table_name="claims")
    op.drop_index("ix_claims_equipment_id", table_name="claims")
    op.drop_index("ix_claims_business_id", table_name="claims")
    op.drop_table("claims")

    op.drop_index("ix_billing_records_policy_id", table_name="billing_records")
    op.drop_table("billing_records")

    op.drop_index("ix_policy_equipment_equipment_id", table_name="policy_equipment")
    op.drop_table("policy_equipment")

    op.drop_index("ix_policies_business_id", table_name="policies")
    op.drop_table("policies")

    op.drop_index("ix_equipment_business_id", table_name="equipment")
    op.drop_table("equipment")

    op.drop_index("ix_users_business_id", table_name="users")
    op.drop_table("users")

    op.drop_table("businesses")
