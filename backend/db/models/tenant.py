import uuid

from sqlalchemy import String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin


class Tenant(Base, TimestampMixin):
    __tablename__ = "tenants"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    encompass_instance_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    encompass_client_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    encompass_client_secret_ref: Mapped[str | None] = mapped_column(
        String(512), nullable=True, comment="Reference to secret in vault, never the actual secret"
    )
    settings: Mapped[dict | None] = mapped_column(JSONB, nullable=True, default=dict)
    is_active: Mapped[bool] = mapped_column(default=True)

    users = relationship("User", back_populates="tenant", lazy="selectin")
    loans = relationship("Loan", back_populates="tenant", lazy="noload")
