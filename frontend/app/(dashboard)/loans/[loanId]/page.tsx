"use client";

import { useEffect, useState, useCallback } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { getLoan, uploadDocument, type LoanDetail, type ChecklistItem } from "@/lib/api";
import {
  formatCurrency,
  formatPersona,
  formatPhase,
  formatStatus,
  formatPercent,
  statusColor,
  checklistStatusIcon,
} from "@/lib/utils";

export default function LoanDetailPage() {
  const params = useParams();
  const loanId = params.loanId as string;
  const [loan, setLoan] = useState<LoanDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState("");
  const [activeTab, setActiveTab] = useState<"checklist" | "documents" | "conditions">("checklist");

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

  useEffect(() => {
    loadLoan();
  }, [loadLoan]);

  async function handleUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const files = e.target.files;
    if (!files || !loan) return;
    setUploading(true);
    try {
      for (const file of Array.from(files)) {
        await uploadDocument(loan.id, file);
      }
      await loadLoan();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Upload failed");
    } finally {
      setUploading(false);
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
      <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-7 gap-3 mb-6">
        {[
          { label: "Amount", value: formatCurrency(loan.loan_amount) },
          { label: "Purpose", value: loan.loan_purpose ? loan.loan_purpose.charAt(0).toUpperCase() + loan.loan_purpose.slice(1) : "—" },
          { label: "Phase", value: formatPhase(loan.processing_phase) },
          { label: "LTV", value: formatPercent(loan.ltv) },
          { label: "DTI (Back)", value: formatPercent(loan.dti_back) },
          { label: "Credit Score", value: loan.representative_credit_score?.toString() || "—" },
          { label: "AUS", value: loan.aus_finding || "Pending" },
        ].map((m) => (
          <div key={m.label} className="bg-(--color-surface) border border-(--color-border) rounded-lg p-3">
            <div className="text-xs text-(--color-text-muted) uppercase tracking-wide">{m.label}</div>
            <div className="text-sm font-semibold mt-1 text-(--color-text)">{m.value}</div>
          </div>
        ))}
      </div>

      {/* Tabs */}
      <div className="flex items-center gap-1 border-b border-(--color-border) mb-4">
        {(["checklist", "documents", "conditions"] as const).map((tab) => (
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
            {tab === "documents" && "Uploaded Documents"}
            {tab === "conditions" && `Conditions (${loan.conditions_summary.total})`}
          </button>
        ))}
      </div>

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
          <div className="bg-(--color-surface) border-2 border-dashed border-(--color-border) rounded-lg p-6 mb-4 text-center hover:border-(--color-accent)/50 transition-colors">
            <input
              type="file"
              multiple
              accept=".pdf,.jpg,.jpeg,.png,.tiff"
              onChange={handleUpload}
              className="hidden"
              id="file-upload"
              disabled={uploading}
            />
            <label htmlFor="file-upload" className="cursor-pointer">
              <div className="text-2xl mb-2">{uploading ? "..." : "📄"}</div>
              <p className="text-sm font-medium text-(--color-text)">
                {uploading ? "Uploading..." : "Drop documents here or click to upload"}
              </p>
              <p className="text-xs text-(--color-text-muted) mt-1">PDF, JPG, PNG, TIFF</p>
            </label>
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
                    const { icon, color } = checklistStatusIcon(item.status);
                    return (
                      <div key={item.document_type} className="flex items-center gap-3 px-4 py-3">
                        <div className={`w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold ${color}`}>
                          {icon}
                        </div>
                        <div className="flex-1 min-w-0">
                          <div className="text-sm font-medium text-(--color-text)">{item.label}</div>
                          {item.description && (
                            <div className="text-xs text-(--color-text-muted) mt-0.5 truncate">{item.description}</div>
                          )}
                        </div>
                        <div className="text-xs font-medium capitalize text-(--color-text-secondary)">
                          {item.status === "missing" ? (
                            <span className="text-red-500">Missing</span>
                          ) : (
                            <span className={item.status === "validated" ? "text-green-600" : "text-blue-600"}>
                              {item.status}
                            </span>
                          )}
                        </div>
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
        <div className="bg-(--color-surface) border border-(--color-border) rounded-lg p-6 text-center">
          <div className="text-4xl mb-3">📁</div>
          <p className="text-sm text-(--color-text-secondary)">
            Uploaded documents will appear here with classification results and extracted data.
          </p>
        </div>
      )}
    </div>
  );
}
