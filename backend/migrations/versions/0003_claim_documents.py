"""Claim documents

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-20
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "claim_documents",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("claim_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("document_type", sa.String(length=30), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("storage_name", sa.String(length=64), nullable=False),
        sa.Column("content_type", sa.String(length=100), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column(
            "uploaded_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "document_type IN ('INVOICE', 'REPAIR_ESTIMATE', 'PHOTO', 'MAINTENANCE_RECORD', 'PURCHASE_RECORD', 'OTHER')",
            name="ck_claim_documents_type",
        ),
        sa.CheckConstraint(
            "length(storage_name) > 0",
            name="ck_claim_documents_storage_name_nonempty",
        ),
        sa.CheckConstraint(
            "content_type IN ('application/pdf', 'image/jpeg', 'image/png')",
            name="ck_claim_documents_content_type",
        ),
        sa.CheckConstraint(
            "size_bytes > 0",
            name="ck_claim_documents_size_positive",
        ),
        sa.CheckConstraint(
            "size_bytes <= 10485760",
            name="ck_claim_documents_size_limit",
        ),
        sa.CheckConstraint(
            "length(sha256) = 64",
            name="ck_claim_documents_sha256_length",
        ),
        sa.ForeignKeyConstraint(
            ["claim_id"],
            ["claims.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("storage_name"),
    )
    op.create_index(
        "ix_claim_documents_claim_id", "claim_documents", ["claim_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_claim_documents_claim_id", table_name="claim_documents")
    op.drop_table("claim_documents")
