"""
Document upload and management endpoints.
Handles file upload, triggers classification pipeline, and serves document data.
"""

import hashlib
import uuid

from fastapi import APIRouter, HTTPException, UploadFile, status
from pydantic import BaseModel
from sqlalchemy import select

from ..dependencies import DB, CurrentUser
from ..events.sse import broadcast_loan_event
from ..db.models.document import Document
from ..db.models.loan import Loan
from ..shared.types import DocumentCategory, DocumentStatus, DocumentType

router = APIRouter(prefix="/loans/{loan_id}/documents", tags=["documents"])


class DocumentResponse(BaseModel):
    id: str
    loan_id: str
    document_type: str | None
    category: str | None
    title: str | None
    file_name: str
    status: str
    classification_confidence: float | None
    extracted_data: dict | None
    page_count: int | None
    period_start: str | None
    period_end: str | None
    tax_year: int | None
    created_at: str


class DocumentListResponse(BaseModel):
    documents: list[DocumentResponse]
    total: int


@router.get("", response_model=DocumentListResponse)
async def list_documents(loan_id: uuid.UUID, user: CurrentUser, db: DB):
    """List all documents for a loan."""
    # Verify loan access
    loan = await _get_loan_or_404(loan_id, user, db)

    result = await db.execute(
        select(Document)
        .where(Document.loan_id == loan.id)
        .order_by(Document.created_at.desc())
    )
    docs = result.scalars().all()

    return DocumentListResponse(
        documents=[_doc_to_response(d) for d in docs],
        total=len(docs),
    )


@router.post("", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED)
async def upload_document(
    loan_id: uuid.UUID,
    file: UploadFile,
    user: CurrentUser,
    db: DB,
    borrower_id: uuid.UUID | None = None,
    document_type: DocumentType | None = None,
):
    """Upload a document for a loan. Triggers classification pipeline."""
    loan = await _get_loan_or_404(loan_id, user, db)

    # Read file
    content = await file.read()
    file_hash = hashlib.sha256(content).hexdigest()

    # Check for duplicate
    existing = await db.execute(
        select(Document).where(Document.loan_id == loan.id, Document.file_hash == file_hash)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Duplicate document already uploaded")

    # Store file (in production: upload to S3)
    s3_key = f"tenants/{user.tenant_id}/loans/{loan.id}/documents/{uuid.uuid4()}/{file.filename}"

    # TODO: Upload to S3
    # await s3_client.put_object(Bucket=bucket, Key=s3_key, Body=content)

    doc = Document(
        loan_id=loan.id,
        tenant_id=user.tenant_id,
        borrower_id=borrower_id,
        document_type=document_type,
        file_path=s3_key,
        file_name=file.filename or "unknown",
        file_size_bytes=len(content),
        file_hash=file_hash,
        mime_type=file.content_type,
        status=DocumentStatus.UPLOADED if not document_type else DocumentStatus.CLASSIFIED,
    )
    db.add(doc)
    await db.flush()

    # TODO: Trigger Document Classifier Agent via Temporal workflow
    # In Milestone 2, this will kick off OCR + classification + extraction

    # Broadcast event for real-time updates
    await broadcast_loan_event(
        str(loan.id),
        "document_uploaded",
        {"document_id": str(doc.id), "file_name": file.filename, "document_type": document_type},
    )

    return _doc_to_response(doc)


@router.get("/{document_id}", response_model=DocumentResponse)
async def get_document(loan_id: uuid.UUID, document_id: uuid.UUID, user: CurrentUser, db: DB):
    """Get document details including extracted data."""
    await _get_loan_or_404(loan_id, user, db)

    result = await db.execute(
        select(Document).where(Document.id == document_id, Document.loan_id == loan_id)
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    return _doc_to_response(doc)


async def _get_loan_or_404(loan_id: uuid.UUID, user: CurrentUser, db: DB) -> Loan:
    result = await db.execute(
        select(Loan).where(Loan.id == loan_id, Loan.tenant_id == user.tenant_id)
    )
    loan = result.scalar_one_or_none()
    if not loan:
        raise HTTPException(status_code=404, detail="Loan not found")
    return loan


def _doc_to_response(doc: Document) -> DocumentResponse:
    return DocumentResponse(
        id=str(doc.id),
        loan_id=str(doc.loan_id),
        document_type=doc.document_type,
        category=doc.category,
        title=doc.title,
        file_name=doc.file_name,
        status=doc.status,
        classification_confidence=float(doc.classification_confidence) if doc.classification_confidence else None,
        extracted_data=doc.extracted_data,
        page_count=doc.page_count,
        period_start=doc.period_start,
        period_end=doc.period_end,
        tax_year=doc.tax_year,
        created_at=doc.created_at.isoformat() if doc.created_at else "",
    )
