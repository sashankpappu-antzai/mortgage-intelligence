"""
Cross-Document Validator Agent — ensures all documents on a loan are internally
consistent AND complete. Replaces manual Processor review.

Uses a LangGraph StateGraph with 7 nodes:
  gather → identity → employer → income → completeness → checklist_gaps → aggregate

Results are persisted to the agent_validations table and broadcast via SSE.
"""

import json
import logging
import time
import uuid
from typing import Any

from sqlalchemy import select

from ...agents.base_agent import BaseAgent
from ...db.models.agent_validation import AgentValidation
from ...db.models.document import Document
from ...db.models.loan import Loan
from ...db.postgres import get_db_session
from ...events.sse import broadcast_loan_event
from ...shared.types import ConfidenceLevel, confidence_level_from_score
from .graph import ValidationState, build_cross_doc_graph

logger = logging.getLogger(__name__)


async def run_cross_doc_validation(loan_id: str) -> dict:
    """
    Run the full cross-document validation pipeline for a loan.

    Called by background tasks after document classification completes.
    Loads all documents, generates the required checklist, runs the LangGraph,
    persists results, and broadcasts events.

    Returns the final_result dict.
    """
    start = time.monotonic()

    # 1. Load loan + ALL documents (both with and without extracted_data)
    async with get_db_session() as db:
        loan_result = await db.execute(
            select(Loan).where(Loan.id == uuid.UUID(loan_id))
        )
        loan = loan_result.scalar_one_or_none()
        if not loan:
            logger.error("Loan %s not found for cross-doc validation", loan_id)
            return {"overall_pass": False, "recommendation": "escalate",
                    "summary": "Loan not found."}

        # All documents on the loan
        all_docs_result = await db.execute(
            select(Document).where(Document.loan_id == uuid.UUID(loan_id))
        )
        all_docs = all_docs_result.scalars().all()

        # Loan metadata for checklist generation
        loan_metadata = {
            "loan_purpose": loan.loan_purpose,
            "persona": loan.primary_borrower_persona,
            "occupancy_type": loan.occupancy_type,
            "property_type": loan.property_type,
            "has_coborrower": len(loan.borrowers) > 1 if loan.borrowers else False,
        }

    if not all_docs:
        logger.info("No documents for loan %s — skipping cross-doc validation", loan_id)
        return {"overall_pass": True, "recommendation": "review_required",
                "summary": "No documents uploaded yet."}

    # 2. Generate the required document checklist
    from ...services.rules.doc_requirements.checklists import generate_checklist
    checklist = generate_checklist(
        persona=loan_metadata.get("persona"),
        loan_purpose=loan_metadata.get("loan_purpose"),
        occupancy_type=loan_metadata.get("occupancy_type"),
        property_type=loan_metadata.get("property_type"),
        has_coborrower=loan_metadata.get("has_coborrower", False),
    )

    # 3. Serialize documents
    doc_dicts_with_data = []  # Documents that have extracted_data (for cross-checks)
    all_doc_dicts = []        # All documents (for completeness + gap analysis)
    doc_ids = []

    for doc in all_docs:
        d = {
            "id": str(doc.id),
            "document_type": doc.document_type,
            "category": doc.category,
            "file_name": doc.file_name,
            "title": doc.title,
            "status": doc.status,
            "extracted_data": doc.extracted_data or {},
        }
        all_doc_dicts.append(d)
        doc_ids.append(doc.id)
        if doc.extracted_data:
            doc_dicts_with_data.append(d)

    logger.info(
        "Running cross-doc validation for loan %s: %d total docs, %d with extracted data, %d checklist items",
        loan_id, len(all_doc_dicts), len(doc_dicts_with_data), len(checklist),
    )

    # 4. Broadcast start event
    await broadcast_loan_event(loan_id, "cross_doc_validation_started", {
        "document_count": len(all_doc_dicts),
        "document_ids": [str(d) for d in doc_ids],
    })

    # 5. Build and run the LangGraph
    graph = build_cross_doc_graph()

    initial_state: ValidationState = {
        "loan_id": loan_id,
        "documents": doc_dicts_with_data,
        "all_documents": all_doc_dicts,
        "checklist": checklist,
        "loan_metadata": loan_metadata,
        "identity_docs": [],
        "employer_docs": [],
        "income_docs": [],
        "identity_result": {},
        "employer_result": {},
        "income_result": {},
        "completeness_result": {},
        "gaps_result": {},
        "final_result": {},
        "llm_tokens_used": 0,
        "llm_model": "",
        "errors": [],
    }

    final_state = await graph.ainvoke(initial_state)
    elapsed_ms = int((time.monotonic() - start) * 1000)

    final_result = final_state.get("final_result", {})
    confidence = final_result.get("overall_confidence", 0.5)
    confidence_lvl = confidence_level_from_score(confidence)

    # 6. Build full result with sub-check details
    full_result = {
        "identity": final_state.get("identity_result", {}),
        "employer": final_state.get("employer_result", {}),
        "income": final_state.get("income_result", {}),
        "completeness": final_state.get("completeness_result", {}),
        "gaps": final_state.get("gaps_result", {}),
        "aggregate": final_result,
    }

    # Build flags dict for UW
    flags = {}
    critical = final_result.get("critical_flags", [])
    warnings = final_result.get("warnings", [])
    borrower_actions = final_result.get("borrower_action_items", [])
    if critical:
        flags["critical"] = critical
    if warnings:
        flags["warnings"] = warnings
    if borrower_actions:
        flags["borrower_action_items"] = borrower_actions
    if not final_result.get("overall_pass", True):
        flags["action_required"] = True
    recommendation = final_result.get("recommendation", "review_required")
    flags["recommendation"] = recommendation

    # 7. Persist to agent_validations table
    async with get_db_session() as db:
        validation = AgentValidation(
            loan_id=uuid.UUID(loan_id),
            tenant_id=(await _get_loan_tenant(db, loan_id)),
            agent_name="cross_doc_validator",
            agent_version="2.0.0",
            validation_type="cross_document_consistency",
            input_document_ids=doc_ids,
            result=full_result,
            confidence_score=round(confidence, 3),
            confidence_level=confidence_lvl,
            flags=flags if flags else None,
            llm_model=final_state.get("llm_model", ""),
            llm_tokens_used=final_state.get("llm_tokens_used", 0),
            processing_time_ms=elapsed_ms,
            status="completed",
        )
        db.add(validation)
        await db.flush()
        validation_id = str(validation.id)

    # 8. Broadcast completion event
    gaps_result = final_state.get("gaps_result", {})
    await broadcast_loan_event(loan_id, "cross_doc_validation_completed", {
        "validation_id": validation_id,
        "overall_pass": final_result.get("overall_pass", True),
        "overall_confidence": confidence,
        "recommendation": recommendation,
        "identity_pass": final_result.get("identity_pass", True),
        "employer_pass": final_result.get("employer_pass", True),
        "income_pass": final_result.get("income_pass", True),
        "completeness_pass": final_result.get("completeness_pass", True),
        "checklist_pass": final_result.get("checklist_pass", True),
        "missing_documents": len(gaps_result.get("missing_documents", [])),
        "borrower_action_items": borrower_actions,
        "critical_flags": critical,
        "warnings": warnings,
        "processing_time_ms": elapsed_ms,
    })

    logger.info(
        "Cross-doc validation completed for loan %s: pass=%s confidence=%.2f rec=%s "
        "missing_docs=%d actions=%d (%dms)",
        loan_id,
        final_result.get("overall_pass"),
        confidence,
        recommendation,
        len(gaps_result.get("missing_documents", [])),
        len(borrower_actions),
        elapsed_ms,
    )

    return final_result


async def _get_loan_tenant(db, loan_id: str) -> uuid.UUID:
    """Get the tenant_id for a loan."""
    result = await db.execute(select(Loan.tenant_id).where(Loan.id == uuid.UUID(loan_id)))
    row = result.scalar_one_or_none()
    if not row:
        raise ValueError(f"Loan {loan_id} not found")
    return row


class CrossDocValidatorAgent(BaseAgent):
    """
    Langfuse-traced wrapper for cross-document validation.
    For background tasks, use run_cross_doc_validation() directly.
    """

    async def run(self, input: str, session_id: str) -> Any:
        """input = loan_id, session_id = loan_id (same for tracing)."""
        result = await run_cross_doc_validation(input)
        return result
