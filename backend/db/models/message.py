import uuid

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TenantMixin, TimestampMixin
from ...shared.types import MessageType


class Message(Base, TenantMixin, TimestampMixin):
    __tablename__ = "messages"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    loan_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("loans.id"), nullable=False, index=True)

    from_type: Mapped[str] = mapped_column(String(20), nullable=False)  # system, agent, user
    from_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    to_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )

    message_type: Mapped[MessageType] = mapped_column(nullable=False)
    subject: Mapped[str | None] = mapped_column(String(500), nullable=True)
    body: Mapped[str] = mapped_column(Text, nullable=False)

    related_condition_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("conditions.id"), nullable=True
    )
    related_document_ids: Mapped[list | None] = mapped_column(
        type_=__import__("sqlalchemy").dialects.postgresql.ARRAY(UUID(as_uuid=True)), nullable=True
    )

    status: Mapped[str] = mapped_column(String(20), default="sent")  # sent, read, responded

    loan = relationship("Loan", lazy="selectin")
    to_user = relationship("User", lazy="selectin")
