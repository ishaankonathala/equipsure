import uuid

from sqlalchemy import CheckConstraint, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, created_at_column, uuid_pk
from app.models.enums import MessageAuthorRole


class ClaimMessage(Base):
    __tablename__ = "claim_messages"
    __table_args__ = (
        CheckConstraint(
            f"author_role IN ({', '.join(repr(role.value) for role in MessageAuthorRole)})",
            name="ck_claim_messages_author_role",
        ),
        CheckConstraint(
            "length(trim(body)) > 0",
            name="ck_claim_messages_body_nonblank",
        ),
        CheckConstraint(
            "length(body) <= 2000",
            name="ck_claim_messages_body_length",
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    claim_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("claims.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    author_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    author_role: Mapped[str] = mapped_column(String(20), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    created_at = created_at_column()