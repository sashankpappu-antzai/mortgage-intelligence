"""Document Classifier Agent — OCR + classify 25+ mortgage document types + extract key data."""

import base64
import io
import json
import logging
import uuid
from typing import Any

from sqlalchemy import select

from ...agents.base_agent import BaseAgent
from ...core.config import get_settings
from ...db.models.document import Document
from ...db.postgres import get_db_session
from ...events.sse import broadcast_loan_event
from ...shared.llm import LLMMessage, LLMProvider, create_llm
from ...shared.types import DocumentCategory, DocumentStatus, DocumentType
from .prompts import (
    CLASSIFICATION_SYSTEM_PROMPT,
    build_classification_message,
    build_vision_content,
    build_vision_message,
)

logger = logging.getLogger(__name__)
settings = get_settings()

# Map document types to categories
_TYPE_TO_CATEGORY: dict[str, DocumentCategory] = {
    "w2": DocumentCategory.INCOME,
    "pay_stub": DocumentCategory.INCOME,
    "tax_return_1040": DocumentCategory.INCOME,
    "tax_return_business": DocumentCategory.INCOME,
    "schedule_c": DocumentCategory.INCOME,
    "schedule_e": DocumentCategory.INCOME,
    "k1": DocumentCategory.INCOME,
    "form_1099": DocumentCategory.INCOME,
    "form_1099_r": DocumentCategory.INCOME,
    "pl_statement": DocumentCategory.INCOME,
    "balance_sheet": DocumentCategory.INCOME,
    "ss_award_letter": DocumentCategory.INCOME,
    "pension_statement": DocumentCategory.INCOME,
    "employment_contract": DocumentCategory.INCOME,
    "cpa_letter": DocumentCategory.INCOME,
    "business_license": DocumentCategory.INCOME,
    "bank_statement": DocumentCategory.ASSETS,
    "retirement_statement": DocumentCategory.ASSETS,
    "gift_letter": DocumentCategory.ASSETS,
    "earnest_money_receipt": DocumentCategory.ASSETS,
    "voe_written": DocumentCategory.INCOME,
    "voe_verbal": DocumentCategory.INCOME,
    "credit_report": DocumentCategory.CREDIT,
    "loe_credit": DocumentCategory.CREDIT,
    "purchase_contract": DocumentCategory.PROPERTY,
    "appraisal": DocumentCategory.PROPERTY,
    "title_commitment": DocumentCategory.TITLE,
    "lease_agreement": DocumentCategory.PROPERTY,
    "mortgage_statement": DocumentCategory.PROPERTY,
    "property_tax_bill": DocumentCategory.PROPERTY,
    "hoa_docs": DocumentCategory.PROPERTY,
    "condo_questionnaire": DocumentCategory.PROPERTY,
    "flood_cert": DocumentCategory.PROPERTY,
    "hoi_declaration": DocumentCategory.INSURANCE,
    "form_4506c": DocumentCategory.COMPLIANCE,
    "government_id": DocumentCategory.COMPLIANCE,
    "ssn_authorization": DocumentCategory.COMPLIANCE,
    "divorce_decree": DocumentCategory.LEGAL,
    "bankruptcy_discharge": DocumentCategory.LEGAL,
}


def _get_llm() -> LLMProvider:
    """Return the best available LLM provider. Prefers Anthropic when API key is set."""
    if settings.anthropic_api_key:
        return create_llm(provider="anthropic", api_key=settings.anthropic_api_key)
    return create_llm(
        provider=settings.llm_provider,
        base_url=settings.llm_base_url,
        api_key=settings.llm_api_key,
        default_model=settings.llm_default_model,
    )


def _extract_pdf_text(content: bytes) -> str:
    """Extract text from a PDF using pypdf. Returns empty string on failure."""
    try:
        import pypdf
        reader = pypdf.PdfReader(io.BytesIO(content))
        pages = []
        for page in reader.pages[:20]:
            text = page.extract_text()
            if text:
                pages.append(text)
        return "\n\n--- PAGE BREAK ---\n\n".join(pages)
    except Exception as e:
        logger.debug("pypdf extraction failed: %s", e)
        return ""


def _is_image_file(filename: str, mime_type: str | None) -> bool:
    ext = (filename or "").lower().rsplit(".", 1)[-1]
    return ext in ("jpg", "jpeg", "png", "tiff", "tif", "bmp", "webp") or (
        mime_type is not None and mime_type.startswith("image/")
    )


def _parse_llm_json(raw: str) -> dict:
    """Robustly parse JSON from LLM output."""
    text = raw.strip()
    # Strip markdown code fences
    if "```json" in text:
        text = text.split("```json", 1)[1].split("```", 1)[0].strip()
    elif "```" in text:
        text = text.split("```", 1)[1].split("```", 1)[0].strip()
    # Find first { ... }
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1:
        text = text[start : end + 1]
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _extract_raw_text(content: bytes) -> str:
    """Try to decode content as plain text (UTF-8/Latin-1). Returns empty string on failure."""
    for encoding in ("utf-8", "latin-1"):
        try:
            text = content.decode(encoding)
            # Heuristic: if >80% printable, it's likely text
            printable = sum(1 for c in text[:2000] if c.isprintable() or c in "\n\r\t")
            if printable / max(len(text[:2000]), 1) > 0.80:
                return text[:6000]
        except Exception:
            continue
    return ""


_ANTHROPIC_VISION_TYPES = {"image/jpeg", "image/png", "image/gif", "image/webp"}


async def _call_llm(llm: LLMProvider, content: bytes, filename: str, mime_type: str | None, known_type: str | None = None) -> dict:
    """
    Call LLM to classify and extract data.
    If known_type is provided, skip classification and only extract fields for that type.
    """
    from .prompts import EXTRACTION_ONLY_SYSTEM_PROMPT, build_extraction_message

    is_image = _is_image_file(filename, mime_type)

    # Choose prompt based on whether we already know the type
    system_prompt = EXTRACTION_ONLY_SYSTEM_PROMPT if known_type else CLASSIFICATION_SYSTEM_PROMPT

    if not is_image:
        # Try PDF text extraction first
        text = _extract_pdf_text(content)
        # If PDF extraction fails, try reading as plain text
        if len(text.strip()) < 50:
            text = _extract_raw_text(content)
        if len(text.strip()) >= 50:
            # Good text — use chat (not vision)
            if known_type:
                user_msg = build_extraction_message(text, filename, known_type)
            else:
                user_msg = build_classification_message(text, filename)
            messages = [
                LLMMessage(role="system", content=system_prompt),
                LLMMessage(role="user", content=user_msg),
            ]
            resp = await llm.chat(messages, json_mode=True, max_tokens=2048)
            return _parse_llm_json(resp.content)
        # Scanned PDF with no extractable text — fall through to vision

    # Vision path: only for actual image types (Anthropic rejects application/pdf)
    mt = mime_type or ("image/jpeg" if is_image else "application/pdf")
    use_vision = is_image or mt in _ANTHROPIC_VISION_TYPES
    if use_vision:
        try:
            image_b64 = base64.b64encode(content).decode()
            vision_content = build_vision_content(filename, image_b64, mt)
            messages = [
                LLMMessage(role="system", content=system_prompt),
                LLMMessage(role="user", content=vision_content),
            ]
            vision_model = settings.llm_vision_model if not settings.anthropic_api_key else None
            resp = await llm.chat_with_vision(messages, model=vision_model, max_tokens=2048)
            result = _parse_llm_json(resp.content)
            if result:
                return result
        except Exception as e:
            logger.warning("Vision classification failed for %s: %s", filename, e)

    # Last resort: classify by filename heuristics (or return known type)
    if known_type:
        return {"document_type": known_type, "confidence": 0.95, "extracted_data": {}, "quality_issues": []}
    return _classify_by_filename(filename)


def _classify_by_filename(filename: str) -> dict:
    """Fallback: guess document type from filename keywords."""
    name = filename.lower()
    hints = [
        (["w2", "w-2", "wage"], "w2", 0.55),
        (["paystub", "pay_stub", "pay-stub", "payslip"], "pay_stub", 0.55),
        (["1040", "tax_return", "taxreturn"], "tax_return_1040", 0.55),
        (["bank", "statement", "checking", "savings"], "bank_statement", 0.55),
        (["purchase", "sales_contract", "agreement"], "purchase_contract", 0.55),
        (["hoi", "insurance", "homeowners"], "hoi_declaration", 0.55),
        (["voe", "verification_of_employ"], "voe_written", 0.55),
        (["credit_report", "trimerge", "tri-merge"], "credit_report", 0.55),
        (["photo_id", "drivers_license", "passport", "government_id"], "government_id", 0.55),
        (["4506", "irs"], "form_4506c", 0.55),
        (["ssn", "social_security"], "ssn_authorization", 0.55),
    ]
    for keywords, doc_type, conf in hints:
        if any(k in name for k in keywords):
            return {"document_type": doc_type, "confidence": conf, "extracted_data": {}, "quality_issues": ["classified_by_filename"]}
    return {"document_type": "other", "confidence": 0.3, "extracted_data": {}, "quality_issues": ["could_not_classify"]}


def _normalise_result(raw: dict, filename: str) -> dict:
    """Fill defaults and clamp values in LLM output."""
    raw.setdefault("document_type", "other")
    raw.setdefault("confidence", 0.5)
    raw.setdefault("extracted_data", {})
    raw.setdefault("quality_issues", [])
    raw.setdefault("title", None)
    raw.setdefault("period_start", None)
    raw.setdefault("period_end", None)
    raw.setdefault("tax_year", None)

    raw["confidence"] = max(0.0, min(1.0, float(raw["confidence"])))

    # If LLM returned invalid doc type, fall back to heuristic
    valid_types = {t.value for t in DocumentType}
    if raw["document_type"] not in valid_types:
        heuristic = _classify_by_filename(filename)
        raw["document_type"] = heuristic["document_type"]
        raw["confidence"] = min(raw["confidence"], heuristic["confidence"])

    return raw


async def classify_document(doc_id: str, loan_id: str, content: bytes, filename: str, mime_type: str | None = None) -> None:
    """
    Core classification pipeline called by the background task.
    Updates document status in DB and broadcasts SSE events.
    """
    llm = _get_llm()
    try:
        async with get_db_session() as db:
            result = await db.execute(select(Document).where(Document.id == uuid.UUID(doc_id)))
            doc = result.scalar_one_or_none()
            if not doc:
                logger.error("Document %s not found for classification", doc_id)
                return

            # Remember if document already had a type (pre-typed upload)
            pre_typed = doc.document_type is not None
            known_type = doc.document_type if pre_typed else None

            # → CLASSIFYING (or EXTRACTING for pre-typed)
            doc.status = DocumentStatus.CLASSIFYING
            await db.flush()

        event_name = "document_extracting" if pre_typed else "document_classifying"
        await broadcast_loan_event(loan_id, event_name, {
            "document_id": doc_id, "file_name": filename
        })

        # Run LLM — extraction-only for pre-typed, full classify for untyped
        raw = await _call_llm(llm, content, filename, mime_type, known_type=known_type)
        result_data = _normalise_result(raw, filename)

        async with get_db_session() as db:
            res = await db.execute(select(Document).where(Document.id == uuid.UUID(doc_id)))
            doc = res.scalar_one_or_none()
            if not doc:
                return

            # Apply results — preserve pre-set type if it was already set
            llm_type_str = result_data["document_type"]
            if pre_typed and doc.document_type:
                # Keep the user-specified type; only use LLM for extraction
                doc_type_str = doc.document_type
            else:
                doc_type_str = llm_type_str
                try:
                    doc.document_type = DocumentType(doc_type_str)
                except ValueError:
                    doc.document_type = None

            confidence = result_data["confidence"]
            doc.classification_confidence = confidence
            doc.extracted_data = result_data.get("extracted_data") or {}
            doc.title = result_data.get("title")
            doc.period_start = result_data.get("period_start")
            doc.period_end = result_data.get("period_end")
            if result_data.get("tax_year"):
                try:
                    doc.tax_year = int(result_data["tax_year"])
                except (ValueError, TypeError):
                    pass

            # Derive category from type
            doc.category = _TYPE_TO_CATEGORY.get(doc_type_str)

            # Status — pre-typed uploads with extraction go straight to classified
            quality_issues = result_data.get("quality_issues", [])
            if pre_typed:
                doc.status = DocumentStatus.CLASSIFIED
            elif confidence >= 0.70 and not quality_issues:
                doc.status = DocumentStatus.CLASSIFIED
            else:
                doc.status = DocumentStatus.NEEDS_REVIEW

            await db.flush()

        await broadcast_loan_event(loan_id, "document_classified", {
            "document_id": doc_id,
            "document_type": doc_type_str,
            "status": doc.status,
            "confidence": float(confidence),
            "title": doc.title,
            "extracted_data": doc.extracted_data,
            "quality_issues": quality_issues,
        })

        logger.info("Classified %s → %s (conf=%.2f)", filename, doc_type_str, confidence)

    except Exception as e:
        logger.exception("Classification failed for doc %s: %s", doc_id, e)
        try:
            async with get_db_session() as db:
                res = await db.execute(select(Document).where(Document.id == uuid.UUID(doc_id)))
                doc = res.scalar_one_or_none()
                if doc:
                    doc.status = DocumentStatus.NEEDS_REVIEW
                    await db.flush()
            await broadcast_loan_event(loan_id, "document_classification_failed", {
                "document_id": doc_id, "error": str(e)
            })
        except Exception:
            pass
    finally:
        await llm.close()


class DocumentClassifierAgent(BaseAgent):
    """Langfuse-traced wrapper. For background tasks use classify_document() directly."""

    async def run(self, input: str, session_id: str) -> Any:
        """input = doc_id, session_id = loan_id. Downloads from storage then classifies."""
        from ...shared.storage import LocalStorage
        async with get_db_session() as db:
            result = await db.execute(select(Document).where(Document.id == uuid.UUID(input)))
            doc = result.scalar_one_or_none()
            if not doc:
                return {"error": "Document not found"}
            storage = LocalStorage("./storage")
            content = await storage.download(doc.file_path)
            filename = doc.file_name
            mime_type = doc.mime_type

        await classify_document(input, session_id, content, filename, mime_type)
        return {"status": "done", "doc_id": input}
