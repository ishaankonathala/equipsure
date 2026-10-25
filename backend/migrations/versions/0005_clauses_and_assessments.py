"""Add policy clauses and AI assessments.

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-25
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "policy_clauses",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("clause_id", sa.String(length=40), nullable=False),
        sa.Column("category", sa.String(length=30), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("source_reference", sa.String(length=500), nullable=False),
        sa.Column("is_fictional", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "length(trim(clause_id)) > 0",
            name="ck_policy_clauses_clause_id_nonblank",
        ),
        sa.CheckConstraint(
            "category IN ('COVERAGE', 'EXCLUSION', 'REPORTING', 'LIMIT')",
            name="ck_policy_clauses_category",
        ),
        sa.CheckConstraint(
            "length(trim(summary)) > 0",
            name="ck_policy_clauses_summary_nonblank",
        ),
        sa.CheckConstraint(
            "length(trim(source_reference)) > 0",
            name="ck_policy_clauses_source_nonblank",
        ),
        sa.CheckConstraint(
            "is_fictional = true",
            name="ck_policy_clauses_fictional_true",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("clause_id"),
    )

    op.create_table(
        "ai_assessments",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("claim_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "requested_by_user_id", postgresql.UUID(as_uuid=True), nullable=False
        ),
        sa.Column("provider", sa.String(length=20), nullable=False),
        sa.Column("prompt_version", sa.String(length=20), nullable=False),
        sa.Column("validation_status", sa.String(length=20), nullable=False),
        sa.Column("advisory_only", sa.Boolean(), nullable=False),
        sa.Column("result_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("cited_clause_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "provider IN ('fake', 'gemini')",
            name="ck_ai_assessments_provider",
        ),
        sa.CheckConstraint(
            "length(trim(prompt_version)) > 0",
            name="ck_ai_assessments_prompt_version_nonblank",
        ),
        sa.CheckConstraint(
            "validation_status IN ('VALID', 'INVALID')",
            name="ck_ai_assessments_validation_status",
        ),
        sa.CheckConstraint(
            "advisory_only = true",
            name="ck_ai_assessments_advisory_true",
        ),
        sa.ForeignKeyConstraint(
            ["claim_id"], ["claims.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["requested_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_ai_assessments_claim_id",
        "ai_assessments",
        ["claim_id"],
        unique=False,
    )

    op.execute(
        """
        CREATE FUNCTION forbid_ai_assessment_change() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'ai_assessments is append-only';
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER ai_assessments_no_update_delete
        BEFORE UPDATE OR DELETE ON ai_assessments
        FOR EACH ROW EXECUTE FUNCTION forbid_ai_assessment_change();
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS ai_assessments_no_update_delete ON ai_assessments;")
    op.execute("DROP FUNCTION IF EXISTS forbid_ai_assessment_change();")
    op.drop_index("ix_ai_assessments_claim_id", table_name="ai_assessments")
    op.drop_table("ai_assessments")
    op.drop_table("policy_clauses")