"""
Cross-Document Validation — LangGraph StateGraph.

Validates that all documents on a loan are internally consistent AND complete:
  1. gather_documents    — load all docs with extracted_data from DB
  2. check_identity      — compare names, SSN-last-4, DOB across docs
  3. check_employer      — compare employer info across W-2, pay stubs, VOE
  4. check_income        — reconcile income figures across doc types
  5. check_completeness  — each doc: missing fields, signatures, pages, staleness
  6. check_checklist_gaps — compare uploaded vs required checklist, generate needs list
  7. aggregate           — combine all results, produce final recommendation + borrower action items

The graph runs nodes sequentially because each check needs the gathered documents.
Completeness and gap checks replace the manual Processor review.
"""

import json
import logging
import time
from typing import Any, TypedDict

from langgraph.graph import END, StateGraph

from ...core.config import get_settings
from ...shared.llm import LLMMessage, LLMProvider, create_llm
from .prompts import (
    AGGREGATION_SYSTEM,
    AGGREGATION_USER,
    CHECKLIST_GAP_SYSTEM,
    CHECKLIST_GAP_USER,
    COMPLETENESS_CHECK_SYSTEM,
    COMPLETENESS_CHECK_USER,
    EMPLOYER_CHECK_SYSTEM,
    EMPLOYER_CHECK_USER,
    IDENTITY_CHECK_SYSTEM,
    IDENTITY_CHECK_USER,
    INCOME_RECONCILIATION_SYSTEM,
    INCOME_RECONCILIATION_USER,
)

logger = logging.getLogger(__name__)
settings = get_settings()

# Document types relevant to each check
_IDENTITY_DOC_TYPES = {
    "w2", "pay_stub", "tax_return_1040", "bank_statement", "government_id",
    "ssn_authorization", "voe_written", "voe_verbal", "credit_report",
}
_EMPLOYER_DOC_TYPES = {
    "w2", "pay_stub", "voe_written", "voe_verbal", "employment_contract",
    "tax_return_1040",
}
_INCOME_DOC_TYPES = {
    "w2", "pay_stub", "tax_return_1040", "tax_return_business", "schedule_c",
    "schedule_e", "k1", "form_1099", "bank_statement", "pl_statement",
    "ss_award_letter", "pension_statement",
}

# Fields we look for in extracted_data per check type
_IDENTITY_FIELDS = {"borrower_name", "name", "employee_name", "ssn_last4", "ssn", "dob", "date_of_birth"}
_EMPLOYER_FIELDS = {"employer_name", "employer", "company_name", "job_title", "position", "hire_date",
                    "employment_start", "pay_period_start", "pay_period_end"}
_INCOME_FIELDS = {"gross_income", "gross_pay", "ytd_gross", "wages", "box1_wages", "net_income",
                  "net_pay", "total_income", "schedule_c_net", "total_deposits", "monthly_income",
                  "annual_income", "federal_wages", "social_security_wages"}


class ValidationState(TypedDict):
    """State that flows through the LangGraph."""
    loan_id: str
    documents: list[dict]          # All docs with extracted_data
    all_documents: list[dict]      # ALL docs on loan (incl. those without extracted_data)
    checklist: list[dict]          # Required document checklist for this loan
    loan_metadata: dict            # loan_purpose, persona, property_type, etc.
    identity_docs: list[dict]      # Filtered for identity check
    employer_docs: list[dict]      # Filtered for employer check
    income_docs: list[dict]        # Filtered for income check
    identity_result: dict          # Output of identity check
    employer_result: dict          # Output of employer check
    income_result: dict            # Output of income check
    completeness_result: dict      # Output of completeness check
    gaps_result: dict              # Output of checklist gap analysis
    final_result: dict             # Aggregated final output
    llm_tokens_used: int
    llm_model: str
    errors: list[str]


def _get_llm() -> LLMProvider:
    """Return the best available LLM provider."""
    if settings.anthropic_api_key:
        return create_llm(provider="anthropic", api_key=settings.anthropic_api_key)
    return create_llm(
        provider=settings.llm_provider,
        base_url=settings.llm_base_url,
        api_key=settings.llm_api_key,
        default_model=settings.llm_default_model,
    )


def _parse_llm_json(raw: str) -> dict:
    """Robustly parse JSON from LLM output, handling markdown fences."""
    text = raw.strip()
    if "```json" in text:
        text = text.split("```json", 1)[1].split("```", 1)[0].strip()
    elif "```" in text:
        text = text.split("```", 1)[1].split("```", 1)[0].strip()
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1:
        text = text[start: end + 1]
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _filter_docs(documents: list[dict], type_set: set, field_set: set) -> list[dict]:
    """Filter documents by type and ensure they have at least one relevant extracted field."""
    result = []
    for doc in documents:
        if doc.get("document_type") not in type_set:
            continue
        ext = doc.get("extracted_data") or {}
        # Check if any relevant field exists and is non-empty
        has_field = any(
            ext.get(f) not in (None, "", {}, [])
            for f in field_set
        )
        if has_field:
            result.append(doc)
    return result


def _doc_summary(doc: dict, field_set: set) -> dict:
    """Create a slim summary of a document with only the relevant fields."""
    ext = doc.get("extracted_data") or {}
    relevant = {k: v for k, v in ext.items() if k in field_set and v not in (None, "", {}, [])}
    return {
        "doc_id": doc["id"],
        "document_type": doc.get("document_type"),
        "file_name": doc.get("file_name"),
        "title": doc.get("title"),
        "extracted_fields": relevant,
    }


# ---------------------------------------------------------------------------
# Graph nodes
# ---------------------------------------------------------------------------

def gather_documents(state: ValidationState) -> dict:
    """Partition documents into check-specific buckets."""
    docs = state["documents"]
    return {
        "identity_docs": _filter_docs(docs, _IDENTITY_DOC_TYPES, _IDENTITY_FIELDS),
        "employer_docs": _filter_docs(docs, _EMPLOYER_DOC_TYPES, _EMPLOYER_FIELDS),
        "income_docs": _filter_docs(docs, _INCOME_DOC_TYPES, _INCOME_FIELDS),
    }


async def check_identity(state: ValidationState) -> dict:
    """Compare borrower identity across all relevant documents."""
    docs = state.get("identity_docs", [])
    if len(docs) < 2:
        return {
            "identity_result": {
                "all_same_person": True,
                "confidence": 1.0,
                "flags": ["insufficient_docs_for_identity_check"],
                "skipped": True,
            },
        }

    summaries = [_doc_summary(d, _IDENTITY_FIELDS) for d in docs]
    llm = _get_llm()
    tokens = 0
    model_name = ""
    try:
        messages = [
            LLMMessage(role="system", content=IDENTITY_CHECK_SYSTEM),
            LLMMessage(
                role="user",
                content=IDENTITY_CHECK_USER.format(
                    doc_count=len(docs),
                    loan_id=state["loan_id"],
                    documents_json=json.dumps(summaries, indent=2, default=str),
                ),
            ),
        ]
        resp = await llm.chat(messages, json_mode=True, max_tokens=2048)
        tokens = resp.input_tokens + resp.output_tokens
        model_name = resp.model
        result = _parse_llm_json(resp.content)
        if not result:
            result = {"all_same_person": None, "confidence": 0.0, "flags": ["llm_parse_error"]}
    except Exception as e:
        logger.exception("Identity check failed: %s", e)
        result = {"all_same_person": None, "confidence": 0.0, "flags": [f"error: {e}"]}
    finally:
        await llm.close()

    return {
        "identity_result": result,
        "llm_tokens_used": state.get("llm_tokens_used", 0) + tokens,
        "llm_model": model_name or state.get("llm_model", ""),
    }


async def check_employer(state: ValidationState) -> dict:
    """Compare employer information across employment-related documents."""
    docs = state.get("employer_docs", [])
    if len(docs) < 2:
        return {
            "employer_result": {
                "employer_consistent": True,
                "confidence": 1.0,
                "flags": ["insufficient_docs_for_employer_check"],
                "skipped": True,
            },
        }

    summaries = [_doc_summary(d, _EMPLOYER_FIELDS) for d in docs]
    llm = _get_llm()
    tokens = 0
    model_name = ""
    try:
        messages = [
            LLMMessage(role="system", content=EMPLOYER_CHECK_SYSTEM),
            LLMMessage(
                role="user",
                content=EMPLOYER_CHECK_USER.format(
                    doc_count=len(docs),
                    loan_id=state["loan_id"],
                    documents_json=json.dumps(summaries, indent=2, default=str),
                ),
            ),
        ]
        resp = await llm.chat(messages, json_mode=True, max_tokens=2048)
        tokens = resp.input_tokens + resp.output_tokens
        model_name = resp.model
        result = _parse_llm_json(resp.content)
        if not result:
            result = {"employer_consistent": None, "confidence": 0.0, "flags": ["llm_parse_error"]}
    except Exception as e:
        logger.exception("Employer check failed: %s", e)
        result = {"employer_consistent": None, "confidence": 0.0, "flags": [f"error: {e}"]}
    finally:
        await llm.close()

    return {
        "employer_result": result,
        "llm_tokens_used": state.get("llm_tokens_used", 0) + tokens,
        "llm_model": model_name or state.get("llm_model", ""),
    }


async def check_income(state: ValidationState) -> dict:
    """Cross-check income figures across document types."""
    docs = state.get("income_docs", [])
    if len(docs) < 2:
        return {
            "income_result": {
                "income_consistent": True,
                "confidence": 1.0,
                "flags": ["insufficient_docs_for_income_check"],
                "skipped": True,
            },
        }

    summaries = [_doc_summary(d, _INCOME_FIELDS) for d in docs]
    llm = _get_llm()
    tokens = 0
    model_name = ""
    try:
        messages = [
            LLMMessage(role="system", content=INCOME_RECONCILIATION_SYSTEM),
            LLMMessage(
                role="user",
                content=INCOME_RECONCILIATION_USER.format(
                    doc_count=len(docs),
                    loan_id=state["loan_id"],
                    documents_json=json.dumps(summaries, indent=2, default=str),
                ),
            ),
        ]
        resp = await llm.chat(messages, json_mode=True, max_tokens=2048)
        tokens = resp.input_tokens + resp.output_tokens
        model_name = resp.model
        result = _parse_llm_json(resp.content)
        if not result:
            result = {"income_consistent": None, "confidence": 0.0, "flags": ["llm_parse_error"]}
    except Exception as e:
        logger.exception("Income check failed: %s", e)
        result = {"income_consistent": None, "confidence": 0.0, "flags": [f"error: {e}"]}
    finally:
        await llm.close()

    return {
        "income_result": result,
        "llm_tokens_used": state.get("llm_tokens_used", 0) + tokens,
        "llm_model": model_name or state.get("llm_model", ""),
    }


async def check_completeness(state: ValidationState) -> dict:
    """Check each document for missing fields, signatures, pages, and staleness."""
    docs = state.get("all_documents", []) or state.get("documents", [])
    if not docs:
        return {
            "completeness_result": {
                "documents": [],
                "total_deficiencies": 0,
                "critical_count": 0,
                "confidence": 1.0,
                "flags": ["no_documents_to_check"],
                "skipped": True,
            },
        }

    from datetime import date
    today = date.today().isoformat()

    # Build summaries with ALL extracted fields for completeness analysis
    summaries = []
    for doc in docs:
        ext = doc.get("extracted_data") or {}
        # Remove internal _citations field for cleaner prompt
        clean_ext = {k: v for k, v in ext.items() if not k.startswith("_")}
        summaries.append({
            "doc_id": doc["id"],
            "document_type": doc.get("document_type"),
            "file_name": doc.get("file_name"),
            "title": doc.get("title"),
            "status": doc.get("status"),
            "extracted_fields": clean_ext,
        })

    llm = _get_llm()
    tokens = 0
    model_name = ""
    try:
        messages = [
            LLMMessage(role="system", content=COMPLETENESS_CHECK_SYSTEM),
            LLMMessage(
                role="user",
                content=COMPLETENESS_CHECK_USER.format(
                    doc_count=len(docs),
                    loan_id=state["loan_id"],
                    documents_json=json.dumps(summaries, indent=2, default=str),
                    today=today,
                ),
            ),
        ]
        resp = await llm.chat(messages, json_mode=True, max_tokens=4096)
        tokens = resp.input_tokens + resp.output_tokens
        model_name = resp.model
        result = _parse_llm_json(resp.content)
        if not result:
            result = {"documents": [], "total_deficiencies": 0, "confidence": 0.0,
                      "flags": ["llm_parse_error"]}
    except Exception as e:
        logger.exception("Completeness check failed: %s", e)
        result = {"documents": [], "total_deficiencies": 0, "confidence": 0.0,
                  "flags": [f"error: {e}"]}
    finally:
        await llm.close()

    return {
        "completeness_result": result,
        "llm_tokens_used": state.get("llm_tokens_used", 0) + tokens,
        "llm_model": model_name or state.get("llm_model", ""),
    }


async def check_checklist_gaps(state: ValidationState) -> dict:
    """Compare uploaded documents against required checklist and generate needs list."""
    checklist = state.get("checklist", [])
    all_docs = state.get("all_documents", []) or state.get("documents", [])
    metadata = state.get("loan_metadata", {})

    if not checklist:
        return {
            "gaps_result": {
                "missing_documents": [],
                "re_upload_needed": [],
                "checklist_completion_pct": 0,
                "total_required": 0,
                "total_received": 0,
                "total_missing": 0,
                "confidence": 1.0,
                "flags": ["no_checklist_available"],
                "needs_list_summary": "No checklist available for gap analysis.",
                "skipped": True,
            },
        }

    # Build uploaded doc summaries
    uploaded = []
    for doc in all_docs:
        uploaded.append({
            "doc_id": doc["id"],
            "document_type": doc.get("document_type"),
            "file_name": doc.get("file_name"),
            "status": doc.get("status"),
            "title": doc.get("title"),
        })

    llm = _get_llm()
    tokens = 0
    model_name = ""
    try:
        messages = [
            LLMMessage(role="system", content=CHECKLIST_GAP_SYSTEM),
            LLMMessage(
                role="user",
                content=CHECKLIST_GAP_USER.format(
                    loan_id=state["loan_id"],
                    loan_purpose=metadata.get("loan_purpose", "unknown"),
                    persona=metadata.get("persona", "unknown"),
                    property_type=metadata.get("property_type", "unknown"),
                    checklist_json=json.dumps(checklist, indent=2, default=str),
                    uploaded_json=json.dumps(uploaded, indent=2, default=str),
                ),
            ),
        ]
        resp = await llm.chat(messages, json_mode=True, max_tokens=4096)
        tokens = resp.input_tokens + resp.output_tokens
        model_name = resp.model
        result = _parse_llm_json(resp.content)
        if not result:
            result = _build_fallback_gaps(checklist, all_docs)
    except Exception as e:
        logger.exception("Checklist gap check failed: %s", e)
        result = _build_fallback_gaps(checklist, all_docs)
        result["flags"] = result.get("flags", []) + [f"error: {e}"]
    finally:
        await llm.close()

    return {
        "gaps_result": result,
        "llm_tokens_used": state.get("llm_tokens_used", 0) + tokens,
        "llm_model": model_name or state.get("llm_model", ""),
    }


def _build_fallback_gaps(checklist: list[dict], all_docs: list[dict]) -> dict:
    """Deterministic fallback gap analysis without LLM."""
    uploaded_types = set()
    needs_reupload = []
    for doc in all_docs:
        dt = doc.get("document_type")
        status = doc.get("status", "")
        if dt and status in ("classified", "validated", "extracted"):
            uploaded_types.add(dt)
        elif dt and status in ("needs_review", "rejected"):
            needs_reupload.append({
                "document_type": dt,
                "doc_id": doc["id"],
                "file_name": doc.get("file_name", ""),
                "reason": f"Document status is '{status}' — needs re-upload or review",
            })

    missing = []
    total_required = 0
    for item in checklist:
        if item.get("required"):
            total_required += 1
        dt = item.get("document_type")
        if dt and dt not in uploaded_types:
            missing.append({
                "document_type": dt,
                "label": item.get("label", dt),
                "category": item.get("category", "other"),
                "required": item.get("required", False),
                "priority": "high" if item.get("required") else "medium",
                "borrower_message": f"Please provide: {item.get('label', dt)}",
                "processor_note": item.get("description", ""),
            })

    received = total_required - len([m for m in missing if m.get("required")])
    pct = round((received / total_required * 100) if total_required > 0 else 0)

    return {
        "missing_documents": missing,
        "re_upload_needed": needs_reupload,
        "checklist_completion_pct": pct,
        "total_required": total_required,
        "total_received": received,
        "total_missing": len(missing),
        "confidence": 0.95,
        "flags": [f"{len(missing)} documents still missing from checklist"] if missing else [],
        "needs_list_summary": (
            f"{len(missing)} required documents are still missing. "
            f"Checklist is {pct}% complete."
        ) if missing else "All required documents have been received.",
    }


async def aggregate(state: ValidationState) -> dict:
    """Produce final cross-doc validation summary from all check results."""
    identity = state.get("identity_result", {})
    employer = state.get("employer_result", {})
    income = state.get("income_result", {})
    completeness = state.get("completeness_result", {})
    gaps = state.get("gaps_result", {})

    # If all checks were skipped (not enough docs), produce a simple result
    all_skipped = (
        identity.get("skipped") and employer.get("skipped") and income.get("skipped")
        and completeness.get("skipped") and gaps.get("skipped")
    )
    if all_skipped:
        return {
            "final_result": {
                "overall_pass": True,
                "overall_confidence": 1.0,
                "identity_pass": True,
                "employer_pass": True,
                "income_pass": True,
                "completeness_pass": True,
                "checklist_pass": True,
                "critical_flags": [],
                "warnings": ["Not enough documents to perform cross-validation checks"],
                "borrower_action_items": [],
                "recommendation": "review_required",
                "summary": (
                    "Insufficient documents with extracted data to perform cross-document "
                    "validation. Upload more documents and re-run."
                ),
            },
        }

    llm = _get_llm()
    tokens = 0
    try:
        messages = [
            LLMMessage(role="system", content=AGGREGATION_SYSTEM),
            LLMMessage(
                role="user",
                content=AGGREGATION_USER.format(
                    loan_id=state["loan_id"],
                    identity_json=json.dumps(identity, indent=2, default=str),
                    employer_json=json.dumps(employer, indent=2, default=str),
                    income_json=json.dumps(income, indent=2, default=str),
                    completeness_json=json.dumps(completeness, indent=2, default=str),
                    gaps_json=json.dumps(gaps, indent=2, default=str),
                ),
            ),
        ]
        resp = await llm.chat(messages, json_mode=True, max_tokens=4096)
        tokens = resp.input_tokens + resp.output_tokens
        result = _parse_llm_json(resp.content)
        if not result:
            result = _build_fallback_aggregate(identity, employer, income,
                                                completeness, gaps)
    except Exception as e:
        logger.exception("Aggregation failed: %s", e)
        result = _build_fallback_aggregate(identity, employer, income,
                                            completeness, gaps)
        result["flags"] = result.get("flags", []) + [f"aggregation_llm_error: {e}"]
    finally:
        await llm.close()

    return {
        "final_result": result,
        "llm_tokens_used": state.get("llm_tokens_used", 0) + tokens,
    }


def _build_fallback_aggregate(
    identity: dict, employer: dict, income: dict,
    completeness: dict | None = None, gaps: dict | None = None,
) -> dict:
    """Build aggregate result without LLM if aggregation call fails."""
    completeness = completeness or {}
    gaps = gaps or {}

    id_pass = identity.get("all_same_person", True)
    emp_pass = employer.get("employer_consistent", True)
    inc_pass = income.get("income_consistent", True)
    comp_pass = completeness.get("critical_count", 0) == 0
    checklist_pass = gaps.get("total_missing", 0) == 0

    id_conf = identity.get("confidence", 0.5)
    emp_conf = employer.get("confidence", 0.5)
    inc_conf = income.get("confidence", 0.5)
    comp_conf = completeness.get("confidence", 0.5)
    gaps_conf = gaps.get("confidence", 0.5)

    # Weighted average
    overall_conf = (id_conf * 0.3 + emp_conf * 0.2 + inc_conf * 0.2
                    + comp_conf * 0.15 + gaps_conf * 0.15)
    overall_pass = all([id_pass, emp_pass, inc_pass, comp_pass, checklist_pass])

    all_flags = (
        identity.get("flags", []) +
        employer.get("flags", []) +
        income.get("flags", []) +
        completeness.get("flags", []) +
        gaps.get("flags", [])
    )

    # Build borrower action items from gaps
    borrower_actions = []
    for missing in gaps.get("missing_documents", []):
        msg = missing.get("borrower_message", "")
        if msg:
            borrower_actions.append(msg)
    for reup in gaps.get("re_upload_needed", []):
        borrower_actions.append(
            f"Re-upload {reup.get('file_name', reup.get('document_type', 'document'))}: "
            f"{reup.get('reason', 'needs review')}"
        )
    # Add completeness deficiencies requiring borrower action
    for doc_check in completeness.get("documents", []):
        for deficiency in doc_check.get("deficiencies", []):
            action = deficiency.get("action_required", "")
            if action and deficiency.get("severity") in ("critical", "warning"):
                borrower_actions.append(action)

    if overall_pass and overall_conf >= 0.7:
        rec = "clear"
    elif overall_conf >= 0.5:
        rec = "review_required"
    else:
        rec = "escalate"

    return {
        "overall_pass": overall_pass,
        "overall_confidence": round(overall_conf, 3),
        "identity_pass": id_pass,
        "employer_pass": emp_pass,
        "income_pass": inc_pass,
        "completeness_pass": comp_pass,
        "checklist_pass": checklist_pass,
        "critical_flags": [f for f in all_flags if "critical" in str(f).lower() or "error" in str(f).lower()],
        "warnings": [f for f in all_flags if "critical" not in str(f).lower() and "error" not in str(f).lower()],
        "borrower_action_items": borrower_actions,
        "recommendation": rec,
        "summary": f"Cross-document validation {'passed' if overall_pass else 'found issues'}. "
                   f"Identity={'✓' if id_pass else '✗'}, "
                   f"Employer={'✓' if emp_pass else '✗'}, "
                   f"Income={'✓' if inc_pass else '✗'}, "
                   f"Completeness={'✓' if comp_pass else '✗'}, "
                   f"Checklist={'✓' if checklist_pass else '✗'}.",
    }


# ---------------------------------------------------------------------------
# Build the graph
# ---------------------------------------------------------------------------

def build_cross_doc_graph() -> StateGraph:
    """
    Construct and compile the LangGraph cross-document validation graph.

    Flow:
        gather → identity → employer → income → completeness → gaps → aggregate → END
    """
    graph = StateGraph(ValidationState)

    graph.add_node("gather_documents", gather_documents)
    graph.add_node("check_identity", check_identity)
    graph.add_node("check_employer", check_employer)
    graph.add_node("check_income", check_income)
    graph.add_node("check_completeness", check_completeness)
    graph.add_node("check_checklist_gaps", check_checklist_gaps)
    graph.add_node("aggregate", aggregate)

    graph.set_entry_point("gather_documents")
    graph.add_edge("gather_documents", "check_identity")
    graph.add_edge("check_identity", "check_employer")
    graph.add_edge("check_employer", "check_income")
    graph.add_edge("check_income", "check_completeness")
    graph.add_edge("check_completeness", "check_checklist_gaps")
    graph.add_edge("check_checklist_gaps", "aggregate")
    graph.add_edge("aggregate", END)

    return graph.compile()
