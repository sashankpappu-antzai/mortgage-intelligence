"use client";

import { useEffect, useState, useCallback, useRef, Fragment } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import dynamic from "next/dynamic";
import { getLoan, uploadDocument, listDocuments, confirmDocument, deleteDocument, deleteBorrower, subscribeLoanEvents, listValidations, triggerValidation, type LoanDetail, type ChecklistItem, type DocumentItem, type ValidationResult } from "@/lib/api";

const DocumentViewer = dynamic(() => import("./document-viewer"), { ssr: false });
import {
  formatCurrency,
  formatPersona,
  formatPhase,
  formatStatus,
  formatPercent,
  statusColor,
  checklistStatusIcon,
} from "@/lib/utils";

const DOC_STATUS_BADGE: Record<string, string> = {
  uploaded: "bg-blue-50 text-blue-700",
  classifying: "bg-yellow-50 text-yellow-700",
  classified: "bg-purple-50 text-purple-700",
  extracted: "bg-indigo-50 text-indigo-700",
  validated: "bg-green-50 text-green-700",
  needs_review: "bg-orange-50 text-orange-700",
  rejected: "bg-red-50 text-red-700",
};

function DocumentTable({ documents, onViewDoc }: { documents: DocumentItem[]; onViewDoc: (doc: DocumentItem) => void }) {
  const [expandedId, setExpandedId] = useState<string | null>(null);

  return (
    <div className="bg-(--color-surface) border border-(--color-border) rounded-xl overflow-hidden">
      <table className="w-full">
        <thead>
          <tr className="border-b border-(--color-border) bg-gray-50/50">
            <th className="text-left px-4 py-3 text-xs font-semibold text-(--color-text-secondary) uppercase tracking-wide">File</th>
            <th className="text-left px-4 py-3 text-xs font-semibold text-(--color-text-secondary) uppercase tracking-wide">Type</th>
            <th className="text-left px-4 py-3 text-xs font-semibold text-(--color-text-secondary) uppercase tracking-wide">Status</th>
            <th className="text-left px-4 py-3 text-xs font-semibold text-(--color-text-secondary) uppercase tracking-wide">Confidence</th>
            <th className="text-left px-4 py-3 text-xs font-semibold text-(--color-text-secondary) uppercase tracking-wide">Pages</th>
            <th className="text-left px-4 py-3 text-xs font-semibold text-(--color-text-secondary) uppercase tracking-wide">Uploaded</th>
            <th className="text-left px-4 py-3 text-xs font-semibold text-(--color-text-secondary) uppercase tracking-wide"></th>
          </tr>
        </thead>
        <tbody>
          {documents.map((doc) => {
            const isClassifying = doc.status === "classifying";
            const hasData = doc.extracted_data && Object.keys(doc.extracted_data).length > 0;
            const isExpanded = expandedId === doc.id;
            return (
              <Fragment key={doc.id}>
                <tr
                  className={`border-b border-(--color-border) last:border-0 ${hasData ? "cursor-pointer hover:bg-gray-50/50" : ""}`}
                  onClick={() => hasData && setExpandedId(isExpanded ? null : doc.id)}
                >
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-2">
                      {isClassifying ? (
                        <div className="w-4 h-4 border-2 border-yellow-400 border-t-transparent rounded-full animate-spin" />
                      ) : (
                        <span className="text-base">📄</span>
                      )}
                      <div>
                        <span className="text-sm font-medium text-(--color-text) truncate max-w-[200px] block">
                          {doc.file_name}
                        </span>
                        {doc.title && (
                          <span className="text-xs text-(--color-text-muted)">{doc.title}</span>
                        )}
                      </div>
                    </div>
                  </td>
                  <td className="px-4 py-3 text-sm text-(--color-text-secondary)">
                    {isClassifying ? (
                      <span className="text-yellow-600 italic">Classifying…</span>
                    ) : doc.document_type ? (
                      doc.document_type.replace(/_/g, " ").replace(/\b\w/g, c => c.toUpperCase())
                    ) : (
                      <span className="text-(--color-text-muted) italic">Pending</span>
                    )}
                  </td>
                  <td className="px-4 py-3">
                    <span className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-xs font-medium capitalize ${DOC_STATUS_BADGE[doc.status] || "bg-gray-100 text-gray-600"}`}>
                      {isClassifying && (
                        <span className="w-2.5 h-2.5 border border-yellow-500 border-t-transparent rounded-full animate-spin inline-block" />
                      )}
                      {doc.status.replace(/_/g, " ")}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-sm text-(--color-text-secondary)">
                    {doc.classification_confidence != null ? `${(doc.classification_confidence * 100).toFixed(0)}%` : "—"}
                  </td>
                  <td className="px-4 py-3 text-sm text-(--color-text-secondary)">{doc.page_count ?? "—"}</td>
                  <td className="px-4 py-3 text-sm text-(--color-text-secondary)">
                    <div className="flex items-center justify-between gap-2">
                      {new Date(doc.created_at).toLocaleDateString()}
                      {hasData && (
                        <span className="text-xs text-(--color-accent)">{isExpanded ? "▲" : "▼"}</span>
                      )}
                    </div>
                  </td>
                  <td className="px-4 py-3">
                    {(doc.status === "classified" || doc.status === "needs_review") && (
                      <button
                        onClick={(e) => { e.stopPropagation(); onViewDoc(doc); }}
                        className="text-xs px-2.5 py-1 rounded-md bg-indigo-50 text-indigo-700 hover:bg-indigo-100 transition-colors font-medium"
                      >
                        View
                      </button>
                    )}
                  </td>
                </tr>
                {isExpanded && hasData && (
                  <tr className="border-b border-(--color-border) bg-indigo-50/30">
                    <td colSpan={7} className="px-6 py-3">
                      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-2">
                        {Object.entries(doc.extracted_data!).map(([key, value]) => {
                          if (value === null || value === undefined || value === "") return null;
                          let displayVal: string;
                          if (Array.isArray(value)) {
                            displayVal = `${value.length} item${value.length !== 1 ? "s" : ""}`;
                          } else if (typeof value === "object") {
                            displayVal = JSON.stringify(value);
                          } else if (typeof value === "number") {
                            const isCurrency = !key.match(/year|last4|page|count|zip|ssn|ein/i) && value >= 1000;
                            displayVal = isCurrency ? `$${value.toLocaleString()}` : String(value);
                          } else {
                            displayVal = String(value);
                          }
                          return (
                            <div key={key} className="bg-white rounded px-3 py-1.5 border border-indigo-100">
                              <div className="text-xs text-(--color-text-muted) uppercase tracking-wide">
                                {key.replace(/_/g, " ")}
                              </div>
                              <div className="text-xs font-medium text-(--color-text) mt-0.5 truncate" title={displayVal}>
                                {displayVal}
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    </td>
                  </tr>
                )}
              </Fragment>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

export default function LoanDetailPage() {
  const params = useParams();
  const loanId = params.loanId as string;
  const [loan, setLoan] = useState<LoanDetail | null>(null);
  const [documents, setDocuments] = useState<DocumentItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [uploadingType, setUploadingType] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [successMsg, setSuccessMsg] = useState("");
  const [validations, setValidations] = useState<ValidationResult[]>([]);
  const [validating, setValidating] = useState(false);
  const [activeTab, setActiveTab] = useState<"checklist" | "documents" | "conditions" | "borrowers" | "validation">("checklist");
  const [expandedChecklist, setExpandedChecklist] = useState<string | null>(null);
  const [viewingDoc, setViewingDoc] = useState<DocumentItem | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const pendingDocType = useRef<string | null>(null);
  const pendingReplaceDocId = useRef<string | null>(null);

  const loadLoan = useCallback(async () => {
    try {
      const data = await getLoan(loanId);
      setLoan(data);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to load loan");
    } finally {
      setLoading(false);
    }
  }, [loanId]);

  const loadDocuments = useCallback(async () => {
    try {
      const docs = await listDocuments(loanId);
      setDocuments(docs);
    } catch {
      // non-fatal
    }
  }, [loanId]);

  const loadValidations = useCallback(async () => {
    try {
      const vals = await listValidations(loanId);
      setValidations(vals);
    } catch {
      // non-fatal
    }
  }, [loanId]);

  useEffect(() => {
    loadLoan();
    loadDocuments();
    loadValidations();
  }, [loadLoan, loadDocuments, loadValidations]);

  // Subscribe to real-time loan events for live classification updates
  useEffect(() => {
    const unsubscribe = subscribeLoanEvents(loanId, (data: unknown) => {
      const event = data as { event?: string };
      if (
        event.event === "document_classified" ||
        event.event === "document_classifying" ||
        event.event === "document_extracting" ||
        event.event === "document_classification_failed" ||
        event.event === "document_uploaded" ||
        event.event === "document_deleted"
      ) {
        loadDocuments();
        loadLoan();
      }
      if (
        event.event === "cross_doc_validation_started" ||
        event.event === "cross_doc_validation_completed"
      ) {
        loadValidations();
        if (event.event === "cross_doc_validation_completed") {
          setValidating(false);
        }
      }
      if (event.event === "loan_metrics_updated") {
        loadLoan(); // Refresh loan to pick up new LTV, DTI, credit score, AI readiness
      }
    });
    return () => unsubscribe();
  }, [loanId, loadDocuments, loadLoan, loadValidations]);

  async function handleConfirmDoc(documentId: string, docType?: string) {
    if (!loan) return;
    try {
      await confirmDocument(loan.id, documentId, {
        status: "classified",
        ...(docType ? { document_type: docType } : {}),
      });
      setSuccessMsg("Classification confirmed!");
      setTimeout(() => setSuccessMsg(""), 4000);
      await Promise.all([loadLoan(), loadDocuments()]);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to confirm");
    }
  }

  function triggerUploadForItem(documentType: string, replaceDocId?: string) {
    pendingDocType.current = documentType;
    pendingReplaceDocId.current = replaceDocId || null;
    fileInputRef.current?.click();
  }

  async function handleUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const files = e.target.files;
    if (!files || !loan) return;
    const docType = pendingDocType.current ?? undefined;
    const replaceDocId = pendingReplaceDocId.current;
    pendingDocType.current = null;
    pendingReplaceDocId.current = null;
    setUploading(true);
    setUploadingType(docType || null);
    setError("");
    setSuccessMsg("");
    try {
      // If re-uploading, delete the old document first
      if (replaceDocId) {
        try {
          await deleteDocument(loan.id, replaceDocId);
        } catch {
          // Non-fatal — old doc may already be gone
        }
      }
      for (const file of Array.from(files)) {
        await uploadDocument(loan.id, file, docType);
      }
      await Promise.all([loadLoan(), loadDocuments()]);
      const label = docType ? docType.replace(/_/g, " ").replace(/\b\w/g, c => c.toUpperCase()) : "Document";
      setSuccessMsg(`${label} ${replaceDocId ? "re-uploaded" : "uploaded"} — AI classification in progress...`);
      setTimeout(() => setSuccessMsg(""), 6000);
      // Stay on current tab — don't switch away
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Upload failed");
    } finally {
      setUploading(false);
      setUploadingType(null);
      e.target.value = "";
    }
  }

  if (loading) {
    return (
      <div className="flex justify-center py-20">
        <div className="w-6 h-6 border-2 border-(--color-accent) border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  // Build a map: document_type → best matching document (prefer classified > needs_review > uploaded)
  const docByType = documents.reduce<Record<string, DocumentItem>>((acc, doc) => {
    if (!doc.document_type) return acc;
    const existing = acc[doc.document_type];
    if (!existing || (doc.status === "classified" && existing.status !== "classified")) {
      acc[doc.document_type] = doc;
    }
    return acc;
  }, {});

  if (error || !loan) {
    return <div className="p-4 bg-red-50 text-red-700 rounded-lg">{error || "Loan not found"}</div>;
  }

  const checklistByCategory = loan.document_checklist.reduce<Record<string, ChecklistItem[]>>((acc, item) => {
    const cat = item.category || "other";
    if (!acc[cat]) acc[cat] = [];
    acc[cat].push(item);
    return acc;
  }, {});

  const totalDocs = loan.document_checklist.length;
  const completedDocs = loan.document_checklist.filter((d) => d.status === "validated" || d.status === "uploaded").length;
  const completionPct = totalDocs > 0 ? Math.round((completedDocs / totalDocs) * 100) : 0;

  return (
    <div>
      {/* Header */}
      <div className="flex items-start justify-between mb-6">
        <div>
          <Link href="/loans" className="text-sm text-(--color-text-secondary) hover:text-(--color-accent) mb-2 inline-block">
            &larr; Back to Loans
          </Link>
          <h1 className="text-2xl font-bold text-(--color-text)">
            {loan.borrower_name || "Loan Details"}
          </h1>
          <div className="flex items-center gap-3 mt-2">
            {loan.encompass_loan_number && (
              <span className="text-sm font-mono text-(--color-text-secondary)">#{loan.encompass_loan_number}</span>
            )}
            <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${statusColor(loan.status)}`}>
              {formatStatus(loan.status)}
            </span>
            <span className="px-2 py-0.5 rounded-full text-xs font-medium bg-blue-50 text-blue-700">
              {formatPersona(loan.primary_borrower_persona)}
            </span>
          </div>
        </div>
        <div className="text-right">
          <div className="text-sm text-(--color-text-secondary)">AI Readiness</div>
          <div className={`text-3xl font-bold ${loan.ai_readiness_score != null && loan.ai_readiness_score >= 80 ? "text-green-600" : loan.ai_readiness_score != null && loan.ai_readiness_score >= 50 ? "text-yellow-600" : "text-gray-300"}`}>
            {loan.ai_readiness_score != null ? `${loan.ai_readiness_score.toFixed(0)}%` : "—"}
          </div>
        </div>
      </div>

      {/* Key metrics */}
      <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-5 gap-3 mb-3">
        {[
          { label: "Loan Amount", value: formatCurrency(loan.loan_amount) },
          { label: "Purchase Price", value: formatCurrency(loan.purchase_price) },
          { label: "LTV", value: formatPercent(loan.ltv), highlight: loan.ltv != null && loan.ltv > 95 ? "text-red-600" : loan.ltv != null && loan.ltv > 80 ? "text-yellow-600" : undefined },
          { label: "Credit Score", value: loan.representative_credit_score?.toString() || "—", highlight: loan.representative_credit_score != null && loan.representative_credit_score < 620 ? "text-red-600" : loan.representative_credit_score != null && loan.representative_credit_score < 680 ? "text-yellow-600" : undefined },
          { label: "Purpose", value: loan.loan_purpose ? loan.loan_purpose.charAt(0).toUpperCase() + loan.loan_purpose.slice(1) : "—" },
        ].map((m) => (
          <div key={m.label} className="bg-(--color-surface) border border-(--color-border) rounded-lg p-3">
            <div className="text-xs text-(--color-text-muted) uppercase tracking-wide">{m.label}</div>
            <div className={`text-sm font-semibold mt-1 ${(m as { highlight?: string }).highlight || "text-(--color-text)"}`}>{m.value}</div>
          </div>
        ))}
      </div>
      <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-5 gap-3 mb-6">
        {[
          { label: "DTI (Front)", value: formatPercent(loan.dti_front), highlight: loan.dti_front != null && loan.dti_front > 36 ? "text-red-600" : loan.dti_front != null && loan.dti_front > 28 ? "text-yellow-600" : undefined },
          { label: "DTI (Back)", value: formatPercent(loan.dti_back), highlight: loan.dti_back != null && loan.dti_back > 50 ? "text-red-600" : loan.dti_back != null && loan.dti_back > 43 ? "text-yellow-600" : undefined },
          { label: "Monthly Income", value: loan.qualifying_income_monthly ? formatCurrency(loan.qualifying_income_monthly) : "--" },
          { label: "Phase", value: formatPhase(loan.processing_phase) },
          { label: "AUS", value: loan.aus_finding || "Pending" },
        ].map((m) => (
          <div key={m.label} className="bg-(--color-surface) border border-(--color-border) rounded-lg p-3">
            <div className="text-xs text-(--color-text-muted) uppercase tracking-wide">{m.label}</div>
            <div className={`text-sm font-semibold mt-1 ${(m as { highlight?: string }).highlight || "text-(--color-text)"}`}>{m.value}</div>
          </div>
        ))}
      </div>

      {/* Tabs */}
      <div className="flex items-center gap-1 border-b border-(--color-border) mb-4">
        {(["checklist", "documents", "borrowers", "validation", "conditions"] as const).map((tab) => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            className={`px-4 py-2.5 text-sm font-medium border-b-2 transition-colors -mb-px ${
              activeTab === tab
                ? "border-(--color-accent) text-(--color-accent)"
                : "border-transparent text-(--color-text-secondary) hover:text-(--color-text)"
            }`}
          >
            {tab === "checklist" && `Document Checklist (${completedDocs}/${totalDocs})`}
            {tab === "documents" && `Uploaded Documents${documents.length > 0 ? ` (${documents.length})` : ""}`}
            {tab === "borrowers" && `Borrowers (${loan.borrowers.length})`}
            {tab === "validation" && `Cross-Doc Validation${validations.length > 0 ? ` (${validations.length})` : ""}`}
            {tab === "conditions" && `Conditions (${loan.conditions_summary.total})`}
          </button>
        ))}
      </div>

      {/* Toast messages */}
      {successMsg && (
        <div className="mb-4 px-4 py-3 rounded-lg bg-green-50 border border-green-200 text-green-800 text-sm flex items-center gap-2 animate-in fade-in">
          <span className="w-4 h-4 border-2 border-green-500 border-t-transparent rounded-full animate-spin" />
          {successMsg}
        </div>
      )}

      {/* Tab content */}
      {activeTab === "checklist" && (
        <div>
          {/* Progress bar */}
          <div className="bg-(--color-surface) border border-(--color-border) rounded-lg p-4 mb-4">
            <div className="flex items-center justify-between mb-2">
              <span className="text-sm font-medium">Document Completion</span>
              <span className="text-sm font-bold text-(--color-accent)">{completionPct}%</span>
            </div>
            <div className="h-2 bg-gray-100 rounded-full overflow-hidden">
              <div
                className="h-full bg-(--color-accent) rounded-full transition-all duration-500"
                style={{ width: `${completionPct}%` }}
              />
            </div>
          </div>

          {/* Upload area */}
          <input
            ref={fileInputRef}
            type="file"
            accept=".pdf,.jpg,.jpeg,.png,.tiff"
            onChange={handleUpload}
            className="hidden"
            disabled={uploading}
          />
          <div
            className="bg-(--color-surface) border-2 border-dashed border-(--color-border) rounded-lg p-5 mb-4 text-center hover:border-(--color-accent)/50 transition-colors cursor-pointer"
            onClick={() => { pendingDocType.current = null; fileInputRef.current?.click(); }}
          >
            <div className="text-2xl mb-1">{uploading && !uploadingType ? "⏳" : "📄"}</div>
            <p className="text-sm font-medium text-(--color-text)">
              {uploading && !uploadingType ? "Uploading..." : "Click to upload without a specific type (AI will classify)"}
            </p>
            <p className="text-xs text-(--color-text-muted) mt-0.5">PDF, JPG, PNG, TIFF</p>
          </div>

          {/* Checklist by category */}
          <div className="space-y-4">
            {Object.entries(checklistByCategory).map(([category, items]) => (
              <div key={category} className="bg-(--color-surface) border border-(--color-border) rounded-lg overflow-hidden">
                <div className="px-4 py-2.5 bg-gray-50 border-b border-(--color-border)">
                  <h3 className="text-sm font-semibold capitalize text-(--color-text)">{category} Documents</h3>
                </div>
                <div className="divide-y divide-(--color-border)">
                  {items.map((item) => {
                    const matchedDoc = docByType[item.document_type];
                    const isItemUploading = uploading && uploadingType === item.document_type;
                    const isClassifying = matchedDoc?.status === "classifying";
                    const isClassified = matchedDoc?.status === "classified";
                    const isNeedsReview = matchedDoc?.status === "needs_review";
                    const hasExtractedData = matchedDoc?.extracted_data && Object.keys(matchedDoc.extracted_data).length > 0;
                    const canExpand = !!matchedDoc && (matchedDoc.status !== "uploaded" || isClassifying);
                    const isExpanded = expandedChecklist === item.document_type || isNeedsReview;
                    const { icon, color } = checklistStatusIcon(item.status);

                    return (
                      <div key={item.document_type}>
                        <div className={`flex items-center gap-3 px-4 py-3 ${canExpand ? "cursor-pointer hover:bg-gray-50/60" : ""}`}
                          onClick={() => canExpand && setExpandedChecklist(
                            expandedChecklist === item.document_type ? null : item.document_type
                          )}
                        >
                          {/* Status icon */}
                          <div className={`w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold flex-shrink-0 ${
                            isItemUploading || isClassifying
                              ? "bg-yellow-100 text-yellow-700"
                              : isClassified
                              ? "bg-green-100 text-green-700"
                              : isNeedsReview
                              ? "bg-orange-100 text-orange-700"
                              : color
                          }`}>
                            {isItemUploading ? (
                              <span className="w-3.5 h-3.5 border-2 border-yellow-500 border-t-transparent rounded-full animate-spin" />
                            ) : isClassifying ? (
                              <span className="w-3.5 h-3.5 border-2 border-yellow-500 border-t-transparent rounded-full animate-spin" />
                            ) : isClassified ? (
                              "✓"
                            ) : isNeedsReview ? (
                              "!"
                            ) : (
                              icon
                            )}
                          </div>

                          {/* Label + description + matched doc info */}
                          <div className="flex-1 min-w-0">
                            <div className="text-sm font-medium text-(--color-text)">{item.label}</div>
                            {item.status === "missing" && !matchedDoc && item.description && (
                              <div className="text-xs text-(--color-text-muted) mt-0.5 truncate">{item.description}</div>
                            )}
                            {isItemUploading && (
                              <div className="text-xs text-yellow-600 mt-0.5 font-medium">Uploading...</div>
                            )}
                            {isClassifying && matchedDoc && (
                              <div className="text-xs text-yellow-600 mt-0.5 font-medium flex items-center gap-1">
                                <span className="w-2.5 h-2.5 border border-yellow-500 border-t-transparent rounded-full animate-spin inline-block" />
                                {item.status !== "missing" ? "Extracting fields from" : "Classifying"} {matchedDoc.file_name}...
                              </div>
                            )}
                            {isClassified && matchedDoc && (
                              <div className="flex items-center gap-2 mt-0.5 flex-wrap">
                                <span className="text-xs text-(--color-text-muted)">{matchedDoc.file_name}</span>
                                <span className="inline-flex items-center px-1.5 py-0.5 rounded-full text-[10px] font-medium bg-green-50 text-green-700">
                                  classified
                                </span>
                                {matchedDoc.classification_confidence != null && (
                                  <span className="text-[10px] text-(--color-text-muted)">
                                    {(matchedDoc.classification_confidence * 100).toFixed(0)}% conf.
                                  </span>
                                )}
                                {matchedDoc.title && (
                                  <span className="text-[10px] text-(--color-text-secondary) italic truncate max-w-[250px]">
                                    {matchedDoc.title}
                                  </span>
                                )}
                              </div>
                            )}
                            {isNeedsReview && matchedDoc && (
                              <div className="flex items-center gap-2 mt-0.5 flex-wrap">
                                <span className="text-xs text-(--color-text-muted)">{matchedDoc.file_name}</span>
                                <span className="inline-flex items-center px-1.5 py-0.5 rounded-full text-[10px] font-medium bg-orange-50 text-orange-700">
                                  needs review
                                </span>
                                {matchedDoc.classification_confidence != null && (
                                  <span className="text-[10px] text-(--color-text-muted)">
                                    {(matchedDoc.classification_confidence * 100).toFixed(0)}% conf.
                                  </span>
                                )}
                              </div>
                            )}
                            {matchedDoc?.status === "uploaded" && !isClassifying && (
                              <div className="text-xs text-blue-600 mt-0.5">
                                {matchedDoc.file_name} — uploaded, awaiting classification
                              </div>
                            )}
                          </div>

                          {/* Right side: actions + expand indicator */}
                          <div className="flex items-center gap-2 flex-shrink-0">
                            {item.status === "missing" && !isItemUploading && (
                              <button
                                onClick={(e) => { e.stopPropagation(); triggerUploadForItem(item.document_type); }}
                                disabled={uploading}
                                className="text-xs px-2.5 py-1 rounded border border-(--color-accent) text-(--color-accent) hover:bg-(--color-accent) hover:text-white transition-colors disabled:opacity-40"
                              >
                                Upload
                              </button>
                            )}
                            {canExpand && (
                              <span className="text-xs text-(--color-accent) ml-1">{isExpanded ? "▲" : "▼"}</span>
                            )}
                          </div>
                        </div>

                        {/* Expanded detail panel */}
                        {isExpanded && matchedDoc && (
                          <div className="px-4 pb-3 pt-0">
                            <div className={`ml-9 rounded-lg p-3 border ${
                              isNeedsReview
                                ? "bg-orange-50/50 border-orange-200"
                                : "bg-indigo-50/50 border-indigo-100"
                            }`}>
                              {/* Needs Review banner */}
                              {isNeedsReview && (
                                <div className="flex items-center justify-between mb-3 pb-2 border-b border-orange-200">
                                  <div>
                                    <div className="text-sm font-semibold text-orange-800">Review Required</div>
                                    <div className="text-xs text-orange-600 mt-0.5">
                                      AI classified this as <strong>{matchedDoc.document_type?.replace(/_/g, " ").replace(/\b\w/g, c => c.toUpperCase())}</strong>
                                      {matchedDoc.classification_confidence != null && ` with ${(matchedDoc.classification_confidence * 100).toFixed(0)}% confidence`}.
                                      {" "}Please review and confirm or re-upload.
                                    </div>
                                  </div>
                                  <div className="flex items-center gap-2 flex-shrink-0">
                                    <button
                                      onClick={(e) => {
                                        e.stopPropagation();
                                        handleConfirmDoc(matchedDoc.id, matchedDoc.document_type || undefined);
                                      }}
                                      className="text-xs px-3 py-1.5 rounded bg-green-600 text-white hover:bg-green-700 transition-colors font-medium"
                                    >
                                      Confirm Classification
                                    </button>
                                    <button
                                      onClick={(e) => { e.stopPropagation(); triggerUploadForItem(item.document_type, matchedDoc.id); }}
                                      disabled={uploading}
                                      className="text-xs px-3 py-1.5 rounded border border-orange-300 text-orange-700 hover:bg-orange-100 transition-colors font-medium"
                                    >
                                      Re-upload
                                    </button>
                                  </div>
                                </div>
                              )}

                              {/* Extracted fields */}
                              {hasExtractedData ? (
                                <>
                                  <div className={`flex items-center justify-between mb-2`}>
                                    <span className={`text-xs font-semibold uppercase tracking-wide ${isNeedsReview ? "text-orange-700" : "text-indigo-700"}`}>
                                      AI Extracted Fields
                                    </span>
                                    <button
                                      onClick={(e) => { e.stopPropagation(); setViewingDoc(matchedDoc); }}
                                      className="text-[10px] px-2.5 py-1 rounded-md bg-indigo-600 text-white hover:bg-indigo-700 transition-colors font-medium flex items-center gap-1"
                                    >
                                      <span>&#128269;</span> View &amp; Verify
                                    </button>
                                  </div>
                                  <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-2">
                                    {Object.entries(matchedDoc.extracted_data!).map(([key, value]) => {
                                      if (value === null || value === undefined || value === "") return null;
                                      let displayVal: string;
                                      if (Array.isArray(value)) {
                                        displayVal = value.map((v, i) => {
                                          if (typeof v === "object" && v !== null) {
                                            const parts = Object.entries(v as Record<string, unknown>).map(([k, val]) => `${k}: ${val}`);
                                            return `(${i + 1}) ${parts.join(", ")}`;
                                          }
                                          return String(v);
                                        }).join("; ");
                                      } else if (typeof value === "object") {
                                        displayVal = JSON.stringify(value);
                                      } else if (typeof value === "number") {
                                        const isCurrency = !key.match(/year|last4|page|count|zip|ssn|ein/i) && value >= 1000;
                                        displayVal = isCurrency ? `$${value.toLocaleString()}` : String(value);
                                      } else {
                                        displayVal = String(value);
                                      }
                                      return (
                                        <div key={key} className="bg-white rounded px-2.5 py-1.5 border border-indigo-100">
                                          <div className="text-[10px] text-(--color-text-muted) uppercase tracking-wide">
                                            {key.replace(/_/g, " ")}
                                          </div>
                                          <div className="text-xs font-medium text-(--color-text) mt-0.5 truncate" title={displayVal}>
                                            {displayVal}
                                          </div>
                                        </div>
                                      );
                                    })}
                                  </div>
                                </>
                              ) : isClassifying ? (
                                <div className="text-xs text-(--color-text-muted) italic flex items-center gap-1.5">
                                  <span className="w-2.5 h-2.5 border border-yellow-500 border-t-transparent rounded-full animate-spin inline-block" />
                                  Extracting key fields...
                                </div>
                              ) : (
                                <div className="text-xs text-(--color-text-muted)">
                                  {matchedDoc.title && <><strong>Title:</strong> {matchedDoc.title}<br /></>}
                                  No extracted data available for this document.
                                </div>
                              )}
                            </div>
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {activeTab === "conditions" && (
        <div className="bg-(--color-surface) border border-(--color-border) rounded-lg p-6 text-center">
          <div className="text-4xl mb-3">📋</div>
          <p className="text-sm text-(--color-text-secondary)">
            {loan.conditions_summary.total > 0
              ? `${loan.conditions_summary.open} open, ${loan.conditions_summary.cleared} cleared of ${loan.conditions_summary.total} total`
              : "No conditions yet. Submit to AUS to generate conditions."}
          </p>
        </div>
      )}

      {activeTab === "documents" && (
        documents.length === 0 ? (
          <div className="bg-(--color-surface) border border-(--color-border) rounded-lg p-8 text-center">
            <div className="text-4xl mb-3">📁</div>
            <p className="text-sm font-medium text-(--color-text)">No documents uploaded yet</p>
            <p className="text-xs text-(--color-text-muted) mt-1">Use the checklist tab to upload documents</p>
          </div>
        ) : (
          <DocumentTable documents={documents} onViewDoc={setViewingDoc} />
        )
      )}

      {activeTab === "borrowers" && (
        <div className="space-y-4">
          {loan.borrowers.map((borrower) => (
            <div key={borrower.id} className="bg-(--color-surface) border border-(--color-border) rounded-xl p-5">
              <div className="flex items-start justify-between mb-4">
                <div>
                  <h3 className="text-base font-semibold text-(--color-text)">
                    {borrower.first_name} {borrower.last_name}
                  </h3>
                  <span className="inline-block mt-1 px-2 py-0.5 rounded-full text-xs font-medium bg-gray-100 text-gray-600 capitalize">
                    {borrower.borrower_type}
                  </span>
                </div>
                <div className="flex items-center gap-2">
                  <span className="inline-block px-2 py-0.5 rounded-full text-xs font-medium bg-blue-50 text-blue-700">
                    {formatPersona(borrower.persona)}
                  </span>
                  <button
                    onClick={async () => {
                      if (!confirm(`Remove ${borrower.first_name} ${borrower.last_name} from this loan?`)) return;
                      try {
                        await deleteBorrower(loanId, borrower.id);
                        const updated = await getLoan(loanId);
                        setLoan(updated);
                      } catch (err) {
                        alert(err instanceof Error ? err.message : "Failed to delete borrower");
                      }
                    }}
                    className="p-1 rounded-md text-gray-400 hover:text-red-600 hover:bg-red-50 transition-colors"
                    title="Remove borrower"
                  >
                    <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <polyline points="3 6 5 6 21 6" />
                      <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
                      <line x1="10" y1="11" x2="10" y2="17" />
                      <line x1="14" y1="11" x2="14" y2="17" />
                    </svg>
                  </button>
                </div>
              </div>
              <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
                <div>
                  <div className="text-xs text-(--color-text-muted) uppercase tracking-wide mb-0.5">Employment Type</div>
                  <div className="text-sm text-(--color-text) capitalize">{borrower.employment_type?.replace(/_/g, " ") || "—"}</div>
                </div>
                <div>
                  <div className="text-xs text-(--color-text-muted) uppercase tracking-wide mb-0.5">Self-Employed</div>
                  <div className="text-sm text-(--color-text)">{borrower.self_employed == null ? "—" : borrower.self_employed ? "Yes" : "No"}</div>
                </div>
              </div>
            </div>
          ))}
          {loan.borrowers.length === 0 && (
            <div className="bg-(--color-surface) border border-(--color-border) rounded-lg p-8 text-center">
              <p className="text-sm text-(--color-text-secondary)">No borrowers on this loan.</p>
            </div>
          )}
        </div>
      )}

      {activeTab === "validation" && (
        <div className="space-y-4">
          {/* Run validation button */}
          <div className="flex items-center justify-between">
            <p className="text-sm text-(--color-text-secondary)">
              Cross-document consistency checks verify identity, employer, and income data across all uploaded documents.
            </p>
            <button
              onClick={async () => {
                setValidating(true);
                try {
                  await triggerValidation(loanId);
                  setSuccessMsg("Validation started — results will appear shortly...");
                  setTimeout(() => setSuccessMsg(""), 6000);
                } catch (err) {
                  setError(err instanceof Error ? err.message : "Failed to start validation");
                  setValidating(false);
                }
              }}
              disabled={validating}
              className="flex-shrink-0 px-4 py-2 bg-(--color-accent) hover:bg-(--color-accent-hover) text-white font-medium rounded-lg text-sm transition-colors disabled:opacity-50 flex items-center gap-2"
            >
              {validating && <span className="w-3.5 h-3.5 border-2 border-white border-t-transparent rounded-full animate-spin" />}
              {validating ? "Running..." : "Run Validation"}
            </button>
          </div>

          {validations.length === 0 ? (
            <div className="bg-(--color-surface) border border-(--color-border) rounded-xl p-10 text-center">
              <div className="text-4xl mb-3">🔍</div>
              <h3 className="text-lg font-semibold text-(--color-text)">No validation results yet</h3>
              <p className="text-sm text-(--color-text-secondary) mt-1">
                Upload at least 2 documents with extracted data, then run validation.
              </p>
            </div>
          ) : (
            validations.map((v) => {
              const agg = v.result?.aggregate;
              const overallPass = agg?.overall_pass;
              const rec = agg?.recommendation || "unknown";
              const recColors: Record<string, string> = {
                clear: "bg-green-50 text-green-700 border-green-200",
                review_required: "bg-yellow-50 text-yellow-700 border-yellow-200",
                escalate: "bg-red-50 text-red-700 border-red-200",
              };
              const recLabels: Record<string, string> = {
                clear: "Clear",
                review_required: "Review Required",
                escalate: "Escalate",
              };
              const checkItems = [
                { label: "Identity", pass: agg?.identity_pass, detail: v.result?.identity },
                { label: "Employer", pass: agg?.employer_pass, detail: v.result?.employer },
                { label: "Income", pass: agg?.income_pass, detail: v.result?.income },
                { label: "Completeness", pass: agg?.completeness_pass, detail: v.result?.completeness },
                { label: "Checklist", pass: agg?.checklist_pass, detail: v.result?.gaps },
              ];
              return (
                <div key={v.id} className="bg-(--color-surface) border border-(--color-border) rounded-xl overflow-hidden">
                  {/* Header */}
                  <div className={`px-5 py-4 flex items-center justify-between border-b ${overallPass ? "bg-green-50/50 border-green-200" : "bg-red-50/50 border-red-200"}`}>
                    <div className="flex items-center gap-3">
                      <div className={`w-10 h-10 rounded-full flex items-center justify-center text-lg font-bold ${overallPass ? "bg-green-100 text-green-700" : "bg-red-100 text-red-700"}`}>
                        {overallPass ? "✓" : "✗"}
                      </div>
                      <div>
                        <div className="text-sm font-semibold text-(--color-text)">
                          Cross-Document Validation
                        </div>
                        <div className="text-xs text-(--color-text-secondary) mt-0.5">
                          {new Date(v.created_at).toLocaleString()}
                          {v.processing_time_ms != null && ` · ${(v.processing_time_ms / 1000).toFixed(1)}s`}
                        </div>
                      </div>
                    </div>
                    <div className="flex items-center gap-3">
                      <div className="text-right">
                        <div className="text-xs text-(--color-text-muted) uppercase tracking-wide">Confidence</div>
                        <div className={`text-lg font-bold ${v.confidence_score >= 0.8 ? "text-green-600" : v.confidence_score >= 0.5 ? "text-yellow-600" : "text-red-500"}`}>
                          {(v.confidence_score * 100).toFixed(0)}%
                        </div>
                      </div>
                      <span className={`px-3 py-1.5 rounded-full text-xs font-semibold border ${recColors[rec] || "bg-gray-50 text-gray-700 border-gray-200"}`}>
                        {recLabels[rec] || rec}
                      </span>
                    </div>
                  </div>

                  {/* Summary */}
                  {agg?.summary && (
                    <div className="px-5 py-3 border-b border-(--color-border) bg-gray-50/30">
                      <p className="text-sm text-(--color-text)">{agg.summary}</p>
                    </div>
                  )}

                  {/* Check cards */}
                  <div className="grid grid-cols-2 md:grid-cols-5 divide-y md:divide-y-0 md:divide-x divide-(--color-border)">
                    {checkItems.map((check) => {
                      const skipped = (check.detail as Record<string, unknown>)?.skipped === true;
                      const conf = (check.detail as Record<string, unknown>)?.confidence;
                      const flags = (check.detail as Record<string, unknown>)?.flags as string[] | undefined;
                      return (
                        <div key={check.label} className="px-5 py-4">
                          <div className="flex items-center gap-2 mb-2">
                            <span className={`w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold ${
                              skipped ? "bg-gray-100 text-gray-400" : check.pass ? "bg-green-100 text-green-700" : check.pass === false ? "bg-red-100 text-red-700" : "bg-gray-100 text-gray-400"
                            }`}>
                              {skipped ? "—" : check.pass ? "✓" : check.pass === false ? "✗" : "?"}
                            </span>
                            <span className="text-sm font-semibold text-(--color-text)">{check.label}</span>
                          </div>
                          {conf != null && (
                            <div className="text-xs text-(--color-text-secondary) mb-1">
                              Confidence: {((conf as number) * 100).toFixed(0)}%
                            </div>
                          )}
                          {skipped && (
                            <div className="text-xs text-(--color-text-muted) italic">
                              Not enough documents for this check
                            </div>
                          )}
                          {flags && flags.length > 0 && (
                            <div className="mt-2 space-y-1">
                              {flags.map((flag, i) => (
                                <div key={i} className="text-xs px-2 py-1 rounded bg-yellow-50 text-yellow-800 border border-yellow-200">
                                  {flag}
                                </div>
                              ))}
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>

                  {/* Critical flags and warnings */}
                  {((agg?.critical_flags && agg.critical_flags.length > 0) || (agg?.warnings && agg.warnings.length > 0)) && (
                    <div className="px-5 py-3 border-t border-(--color-border) bg-gray-50/30">
                      {agg?.critical_flags && agg.critical_flags.length > 0 && (
                        <div className="mb-2">
                          <div className="text-xs font-semibold text-red-700 uppercase tracking-wide mb-1">Critical Flags</div>
                          {agg.critical_flags.map((f, i) => (
                            <div key={i} className="text-xs px-2.5 py-1.5 rounded bg-red-50 text-red-800 border border-red-200 mb-1">
                              {f}
                            </div>
                          ))}
                        </div>
                      )}
                      {agg?.warnings && agg.warnings.length > 0 && (
                        <div>
                          <div className="text-xs font-semibold text-yellow-700 uppercase tracking-wide mb-1">Warnings</div>
                          {agg.warnings.map((w, i) => (
                            <div key={i} className="text-xs px-2.5 py-1.5 rounded bg-yellow-50 text-yellow-800 border border-yellow-200 mb-1">
                              {w}
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  )}

                  {/* Borrower Action Items */}
                  {agg?.borrower_action_items && agg.borrower_action_items.length > 0 && (
                    <div className="px-5 py-4 border-t border-(--color-border) bg-blue-50/30">
                      <div className="text-xs font-semibold text-blue-800 uppercase tracking-wide mb-2">
                        Borrower Action Required ({agg.borrower_action_items.length})
                      </div>
                      <p className="text-xs text-blue-700 mb-2">
                        These items need to be collected from or completed by the borrower:
                      </p>
                      <div className="space-y-1.5">
                        {agg.borrower_action_items.map((item, i) => (
                          <div key={i} className="flex items-start gap-2 text-xs px-3 py-2 rounded-lg bg-white border border-blue-200 text-blue-900">
                            <span className="text-blue-500 mt-0.5 flex-shrink-0">●</span>
                            <span>{item}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Missing Documents from Checklist */}
                  {v.result?.gaps?.missing_documents && v.result.gaps.missing_documents.length > 0 && (
                    <div className="px-5 py-4 border-t border-(--color-border)">
                      <div className="flex items-center justify-between mb-2">
                        <div className="text-xs font-semibold text-(--color-text) uppercase tracking-wide">
                          Missing Documents ({v.result.gaps.missing_documents.length})
                        </div>
                        {v.result.gaps.checklist_completion_pct != null && (
                          <span className="text-xs font-medium text-(--color-text-secondary)">
                            Checklist: {v.result.gaps.checklist_completion_pct}% complete
                          </span>
                        )}
                      </div>
                      {v.result.gaps.needs_list_summary && (
                        <p className="text-xs text-(--color-text-secondary) mb-2 italic">{v.result.gaps.needs_list_summary}</p>
                      )}
                      <div className="space-y-1.5">
                        {v.result.gaps.missing_documents.map((md, i) => (
                          <div key={i} className="flex items-start gap-3 text-xs px-3 py-2 rounded-lg bg-orange-50 border border-orange-200">
                            <div className="flex-shrink-0 mt-0.5">
                              <span className={`inline-block px-1.5 py-0.5 rounded text-[10px] font-semibold uppercase ${
                                md.priority === "high" ? "bg-red-100 text-red-700" :
                                md.priority === "medium" ? "bg-yellow-100 text-yellow-700" :
                                "bg-gray-100 text-gray-600"
                              }`}>{md.priority}</span>
                            </div>
                            <div className="flex-1 min-w-0">
                              <div className="font-medium text-(--color-text)">{md.label}</div>
                              <div className="text-orange-700 mt-0.5">{md.borrower_message}</div>
                            </div>
                            <span className="text-[10px] text-(--color-text-muted) uppercase flex-shrink-0">{md.category}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Document Deficiencies */}
                  {v.result?.completeness?.documents && v.result.completeness.documents.some(d => d.deficiencies?.length > 0) && (
                    <div className="px-5 py-4 border-t border-(--color-border)">
                      <div className="text-xs font-semibold text-(--color-text) uppercase tracking-wide mb-2">
                        Document Deficiencies
                      </div>
                      <div className="space-y-3">
                        {v.result.completeness.documents.filter(d => d.deficiencies?.length > 0).map((doc) => (
                          <div key={doc.doc_id} className="rounded-lg border border-(--color-border) overflow-hidden">
                            <div className="px-3 py-2 bg-gray-50 border-b border-(--color-border) flex items-center gap-2">
                              <span className={`w-5 h-5 rounded-full flex items-center justify-center text-[10px] font-bold ${doc.complete ? "bg-green-100 text-green-700" : "bg-red-100 text-red-700"}`}>
                                {doc.complete ? "✓" : "✗"}
                              </span>
                              <span className="text-xs font-medium text-(--color-text)">{doc.file_name}</span>
                              <span className="text-[10px] text-(--color-text-muted)">({doc.document_type?.replace(/_/g, " ")})</span>
                              {doc.stale && <span className="text-[10px] px-1.5 py-0.5 rounded bg-orange-100 text-orange-700 font-medium">STALE</span>}
                              {doc.missing_signature && <span className="text-[10px] px-1.5 py-0.5 rounded bg-red-100 text-red-700 font-medium">NO SIGNATURE</span>}
                              {doc.missing_pages && <span className="text-[10px] px-1.5 py-0.5 rounded bg-red-100 text-red-700 font-medium">MISSING PAGES</span>}
                            </div>
                            <div className="px-3 py-2 space-y-1">
                              {doc.deficiencies.map((def_, j) => (
                                <div key={j} className={`text-xs px-2.5 py-1.5 rounded border ${
                                  def_.severity === "critical" ? "bg-red-50 border-red-200 text-red-800" :
                                  def_.severity === "warning" ? "bg-yellow-50 border-yellow-200 text-yellow-800" :
                                  "bg-gray-50 border-gray-200 text-gray-700"
                                }`}>
                                  <span className="font-medium">{def_.field}:</span> {def_.message}
                                  {def_.action_required && (
                                    <div className="mt-0.5 text-blue-700 font-medium">→ {def_.action_required}</div>
                                  )}
                                </div>
                              ))}
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              );
            })
          )}
        </div>
      )}

      {/* Document Viewer Modal */}
      {viewingDoc && (
        <DocumentViewer
          doc={viewingDoc}
          loanId={loanId}
          onClose={() => setViewingDoc(null)}
          onConfirm={
            viewingDoc.status === "needs_review" || viewingDoc.status === "classified"
              ? async () => {
                  await handleConfirmDoc(viewingDoc.id, viewingDoc.document_type || undefined);
                  setViewingDoc(null);
                }
              : undefined
          }
          onReupload={
            viewingDoc.document_type
              ? () => {
                  setViewingDoc(null);
                  triggerUploadForItem(viewingDoc.document_type!);
                }
              : undefined
          }
        />
      )}
    </div>
  );
}
