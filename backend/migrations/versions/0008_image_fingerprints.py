"""Create image_fingerprints table.

Revision ID: 0008
Revises: 0007
Create Date: 2026-11-04
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0008"
down_revision: Union[str, None] = "0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "image_fingerprints",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("dhash", sa.String(length=16), nullable=False),
        sa.Column("blur_score", sa.Float(), nullable=False),
        sa.Column("width", sa.Integer(), nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["claim_documents.id"],
            name="fk_image_fingerprints_document_id_claim_documents",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("document_id", name="uq_image_fingerprints_document_id"),
    )
    op.create_index(
        "ix_image_fingerprints_sha256",
        "image_fingerprints",
        ["sha256"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_image_fingerprints_sha256", table_name="image_fingerprints")
    op.drop_table("image_fingerprints")

