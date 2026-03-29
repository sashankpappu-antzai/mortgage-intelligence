"""
Encompass webhook receiver.
Handles incoming events and routes them to the appropriate processing pipeline.
"""

import logging
import uuid

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy import select

from ..core.config import get_settings
from ..events.sse import broadcast_loan_event
from ..db.models.audit import AuditEvent
from ..db.models.condition import Condition
from ..db.models.loan import Loan
from ..db.postgres import get_db
from ..services.encompass.client import EncompassClient
from ..shared.types import ConditionSource, ConditionStatus, ConditionType, LoanStatus, ProcessingPhase

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/webhooks", tags=["webhooks"])


class EncompassWebhookEvent(BaseModel):
    event_type: str  # loan.milestone.changed, loan.document.added, etc.
    resource_type: str  # loan
    resource_id: str  # Encompass loan ID
    instance_id: str | None = None
    data: dict | None = None


@router.post("/encompass")
async def receive_encompass_webhook(request: Request):
    """Receive and process Encompass webhook events."""
    body = await request.body()

    # Verify webhook signature
    signature = request.headers.get("X-Encompass-Signature", "")
    if settings.encompass_webhook_secret:
        client = EncompassClient(
            instance_url=settings.encompass_instance_url,
            client_id=settings.encompass_client_id,
            client_secret=settings.encompass_client_secret,
            webhook_secret=settings.encompass_webhook_secret,
        )
        if not client.verify_webhook_signature(body, signature):
            raise HTTPException(status_code=401, detail="Invalid webhook signature")

    event = EncompassWebhookEvent.model_validate_json(body)
    logger.info(f"Webhook received: {event.event_type} for loan {event.resource_id}")

    # Route to handler
    handler = _WEBHOOK_HANDLERS.get(event.event_type)
    if handler:
        # Process in background (in production, this would be a Temporal workflow)
        async for db in get_db():
            await handler(event, db)
            # Audit log
            db.add(AuditEvent(
                tenant_id=uuid.UUID("00000000-0000-0000-0000-000000000000"),  # TODO: resolve from instance_id
                loan_id=None,
                event_type=f"webhook.{event.event_type}",
                actor_type="encompass_webhook",
                actor_id=event.instance_id,
                action=f"Received {event.event_type}",
                details={"resource_id": event.resource_id, "data": event.data},
            ))
            await db.commit()
    else:
        logger.warning(f"No handler for webhook event: {event.event_type}")

    return {"status": "received"}


async def _handle_milestone_changed(event: EncompassWebhookEvent, db):
    """Handle loan milestone changes - triggers phase transitions."""
    loan = await _get_or_create_loan(event.resource_id, db)
    if not loan:
        return

    milestone = (event.data or {}).get("milestone", "")
    loan.encompass_milestone = milestone

    # Map Encompass milestones to our processing phases
    milestone_phase_map = {
        "File Started": (LoanStatus.INTAKE, ProcessingPhase.INTAKE),
        "Submitted to Processing": (LoanStatus.PROCESSING, ProcessingPhase.DOC_COLLECTION),
        "Docs Requested": (LoanStatus.PROCESSING, ProcessingPhase.DOC_COLLECTION),
        "Docs Received": (LoanStatus.PROCESSING, ProcessingPhase.DATA_VERIFICATION),
        "Submitted to UW": (LoanStatus.SUBMITTED_TO_UW, ProcessingPhase.UW_SUBMISSION),
        "Conditionally Approved": (LoanStatus.CONDITIONALLY_APPROVED, ProcessingPhase.UW_SUBMISSION),
        "Clear to Close": (LoanStatus.CLEAR_TO_CLOSE, ProcessingPhase.CLOSING),
        "Closing": (LoanStatus.CLOSING, ProcessingPhase.CLOSING),
        "Funded": (LoanStatus.FUNDED, ProcessingPhase.CLOSING),
    }

    if milestone in milestone_phase_map:
        new_status, new_phase = milestone_phase_map[milestone]
        loan.status = new_status
        loan.processing_phase = new_phase

    await broadcast_loan_event(str(loan.id), "milestone_changed", {"milestone": milestone})


async def _handle_document_added(event: EncompassWebhookEvent, db):
    """Handle new document upload - triggers classification pipeline."""
    loan = await _get_or_create_loan(event.resource_id, db)
    if not loan:
        return

    # In production: trigger Document Classifier Agent via Temporal
    logger.info(f"Document added to loan {event.resource_id}, triggering classification pipeline")
    await broadcast_loan_event(str(loan.id), "document_added", event.data or {})


async def _handle_condition_changed(event: EncompassWebhookEvent, db):
    """Handle condition status changes from UW."""
    loan = await _get_or_create_loan(event.resource_id, db)
    if not loan:
        return

    condition_data = event.data or {}
    encompass_cond_id = condition_data.get("conditionId")

    if encompass_cond_id:
        result = await db.execute(
            select(Condition).where(
                Condition.loan_id == loan.id,
                Condition.encompass_condition_id == encompass_cond_id,
            )
        )
        condition = result.scalar_one_or_none()

        if condition:
            new_status = condition_data.get("status", "").lower()
            status_map = {
                "open": ConditionStatus.OPEN,
                "received": ConditionStatus.RECEIVED,
                "reviewed": ConditionStatus.REVIEWED,
                "cleared": ConditionStatus.CLEARED,
                "waived": ConditionStatus.WAIVED,
            }
            if new_status in status_map:
                condition.status = status_map[new_status]

    await broadcast_loan_event(str(loan.id), "condition_changed", condition_data)


async def _get_or_create_loan(encompass_loan_id: str, db) -> Loan | None:
    """Get existing loan by Encompass ID or create a placeholder."""
    result = await db.execute(select(Loan).where(Loan.encompass_loan_id == encompass_loan_id))
    loan = result.scalar_one_or_none()

    if not loan:
        # Create a placeholder loan - will be populated when we fetch from Encompass
        loan = Loan(
            encompass_loan_id=encompass_loan_id,
            tenant_id=uuid.UUID("00000000-0000-0000-0000-000000000000"),  # TODO: resolve from instance
            status=LoanStatus.CREATED,
            processing_phase=ProcessingPhase.INTAKE,
        )
        db.add(loan)
        await db.flush()
        logger.info(f"Created placeholder loan for Encompass ID: {encompass_loan_id}")

    return loan


_WEBHOOK_HANDLERS = {
    "loan.milestone.changed": _handle_milestone_changed,
    "loan.document.added": _handle_document_added,
    "loan.condition.statusChanged": _handle_condition_changed,
}
