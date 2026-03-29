import uuid

from sqlalchemy import ForeignKey, Index, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TenantMixin, TimestampMixin
from ...shared.types import DocumentCategory, DocumentStatus, DocumentType


class Document(Base, TenantMixin, TimestampMixin):
    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    loan_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("loans.id"), nullable=False, index=True)
    borrower_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("loan_borrowers.id"), nullable=True
    )

    # Encompass references
    encompass_document_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    encompass_attachment_id: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Classification
    document_type: Mapped[DocumentType | None] = mapped_column(nullable=True)
    category: Mapped[DocumentCategory | None] = mapped_column(nullable=True)
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Storage
    file_path: Mapped[str] = mapped_column(String(1024), nullable=False, comment="S3 key")
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    file_size_bytes: Mapped[int | None] = mapped_column(nullable=True)
    file_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, comment="SHA-256 for dedup")
    mime_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    page_count: Mapped[int | None] = mapped_column(nullable=True)

    # AI extraction
    ocr_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    extracted_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    classification_confidence: Mapped[float | None] = mapped_column(Numeric(4, 3), nullable=True)

    # Status
    status: Mapped[DocumentStatus] = mapped_column(default=DocumentStatus.UPLOADED)

    # Period covered (for income/asset docs)
    period_start: Mapped[str | None] = mapped_column(String(10), nullable=True)  # YYYY-MM-DD
    period_end: Mapped[str | None] = mapped_column(String(10), nullable=True)
    tax_year: Mapped[int | None] = mapped_column(nullable=True)

    loan = relationship("Loan", back_populates="documents")
    borrower = relationship("LoanBorrower", lazy="selectin")

    __table_args__ = (
        Index("ix_documents_loan_type", "loan_id", "document_type"),
    )
