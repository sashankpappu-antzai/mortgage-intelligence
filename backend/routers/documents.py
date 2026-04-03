"""
Document upload and management endpoints.
Handles file upload, triggers classification pipeline, and serves document data.
"""

import hashlib
import logging
import uuid

from fastapi import APIRouter, BackgroundTasks, HTTPException, UploadFile, status
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import delete as sa_delete, select

from ..dependencies import DB, CurrentUser
from ..events.sse import broadcast_loan_event
from ..db.models.document import Document
from ..db.models.loan import Loan
from ..shared.types import DocumentCategory, DocumentStatus, DocumentType

logger = logging.getLogger(__name__)

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


async def _run_classifier(doc_id: str, loan_id: str, content: bytes, filename: str, mime_type: str | None) -> None:
    """Background task: runs the document classifier, then recalculates metrics.

    Cross-doc validation is NOT triggered per-document — it only runs when the user
    explicitly clicks "Run Validation" (via POST /loans/{id}/validate).  This avoids
    hammering the LLM with N×7 calls when uploading N documents in a batch.
    """
    from ..agents.document_classifier.agent import classify_document
    await classify_document(doc_id, loan_id, content, filename, mime_type)

    # Recalculate loan metrics after every document classification
    try:
        from ..services.loan_metrics import recalculate_loan_metrics
        await recalculate_loan_metrics(loan_id)
    except Exception as e:
        logger.warning("Loan metrics recalculation failed (non-fatal): %s", e)


@router.post("", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED)
async def upload_document(
    loan_id: uuid.UUID,
    file: UploadFile,
    user: CurrentUser,
    db: DB,
    background_tasks: BackgroundTasks,
    borrower_id: uuid.UUID | None = None,
    document_type: DocumentType | None = None,
):
    """Upload a document for a loan. Triggers classification pipeline."""
    loan = await _get_loan_or_404(loan_id, user, db)

    # Read file
    content = await file.read()
    file_hash = hashlib.sha256(content).hexdigest()

    # Check for duplicate
    existing_result = await db.execute(
        select(Document).where(Document.loan_id == loan.id, Document.file_hash == file_hash)
    )
    existing_doc = existing_result.scalar_one_or_none()
    if existing_doc:
        # If the same file exists without a type and we now know the type, update it
        if document_type and not existing_doc.document_type:
            existing_doc.document_type = document_type
            existing_doc.status = DocumentStatus.CLASSIFIED
            await db.flush()
            await broadcast_loan_event(
                str(loan.id),
                "document_updated",
                {"document_id": str(existing_doc.id), "document_type": document_type},
            )
            return _doc_to_response(existing_doc)
        raise HTTPException(status_code=409, detail="Duplicate document already uploaded")

    # Store file to local filesystem (falls back gracefully from S3 when MinIO not running)
    file_uid = uuid.uuid4()
    s3_key = f"tenants/{user.tenant_id}/loans/{loan.id}/documents/{file_uid}/{file.filename}"
    try:
        from ..shared.storage import LocalStorage
        await LocalStorage("./storage").upload(s3_key, content, file.content_type or "application/octet-stream")
    except Exception as e:
        logger.warning("Storage upload failed (non-fatal): %s", e)

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

    # Commit so background tasks (running in separate sessions) can see the row
    await db.commit()

    # Broadcast upload event
    await broadcast_loan_event(
        str(loan.id),
        "document_uploaded",
        {"document_id": str(doc.id), "file_name": file.filename, "document_type": document_type},
    )

    # Always trigger classifier to extract data (even when type is pre-specified)
    background_tasks.add_task(
        _run_classifier,
        str(doc.id),
        str(loan.id),
        content,
        file.filename or "unknown",
        file.content_type,
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


@router.get("/{document_id}/file")
async def download_document_file(
    loan_id: uuid.UUID, document_id: uuid.UUID, user: CurrentUser, db: DB
):
    """Serve the original document file for inline viewing."""
    await _get_loan_or_404(loan_id, user, db)

    result = await db.execute(
        select(Document).where(Document.id == document_id, Document.loan_id == loan_id)
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    try:
        from ..shared.storage import LocalStorage

        content = await LocalStorage("./storage").download(doc.file_path)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="File not found in storage")
    except Exception as e:
        logger.error("Failed to read file from storage: %s", e)
        raise HTTPException(status_code=500, detail="Failed to read file")

    return Response(
        content=content,
        media_type=doc.mime_type or "application/octet-stream",
        headers={
            "Content-Disposition": f'inline; filename="{doc.file_name}"',
            "Cache-Control": "private, max-age=3600",
        },
    )


class DocumentUpdateRequest(BaseModel):
    """Confirm or update a document's classification."""
    document_type: str | None = None
    status: str | None = None  # "classified" to confirm a needs_review doc


@router.patch("/{document_id}", response_model=DocumentResponse)
async def update_document(
    loan_id: uuid.UUID,
    document_id: uuid.UUID,
    body: DocumentUpdateRequest,
    user: CurrentUser,
    db: DB,
):
    """Confirm classification or reclassify a document."""
    loan = await _get_loan_or_404(loan_id, user, db)

    result = await db.execute(
        select(Document).where(Document.id == document_id, Document.loan_id == loan_id)
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    if body.document_type:
        try:
            doc.document_type = DocumentType(body.document_type)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid document_type: {body.document_type}")
        # Update category based on type
        from ..agents.document_classifier.agent import _TYPE_TO_CATEGORY
        cat = _TYPE_TO_CATEGORY.get(DocumentType(body.document_type))
        if cat:
            doc.category = cat

    if body.status:
        try:
            doc.status = DocumentStatus(body.status)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid status: {body.status}")

    await db.flush()
    await db.commit()

    await broadcast_loan_event(
        str(loan.id),
        "document_classified",
        {"document_id": str(doc.id), "document_type": doc.document_type, "status": doc.status},
    )

    return _doc_to_response(doc)


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    loan_id: uuid.UUID,
    document_id: uuid.UUID,
    user: CurrentUser,
    db: DB,
):
    """Delete a document from a loan (e.g. for re-upload)."""
    loan = await _get_loan_or_404(loan_id, user, db)

    result = await db.execute(
        select(Document).where(Document.id == document_id, Document.loan_id == loan.id)
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    # Try to remove the file from storage
    try:
        from ..shared.storage import LocalStorage
        await LocalStorage("./storage").delete(doc.file_path)
    except Exception as e:
        logger.warning("Storage delete failed (non-fatal): %s", e)

    await db.execute(sa_delete(Document).where(Document.id == document_id))
    await db.commit()

    await broadcast_loan_event(
        str(loan.id),
        "document_deleted",
        {"document_id": str(document_id)},
    )

    # Recalculate metrics after deletion
    try:
        from ..services.loan_metrics import recalculate_loan_metrics
        await recalculate_loan_metrics(str(loan.id))
    except Exception as e:
        logger.warning("Post-delete metrics recalculation failed (non-fatal): %s", e)


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
