"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { getPipeline, type PipelineItem } from "@/lib/api";
import { formatCurrency, formatPersona, formatPhase, formatStatus, formatPercent, statusColor, readinessColor } from "@/lib/utils";

export default function PipelinePage() {
  const [loans, setLoans] = useState<PipelineItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<string>("");

  useEffect(() => {
    loadPipeline();
  }, [filter]);

  async function loadPipeline() {
    try {
      const data = await getPipeline(filter ? { status: filter } : undefined);
      setLoans(data);
    } catch {
      // handle error
    } finally {
      setLoading(false);
    }
  }

  const readyCount = loans.filter((l) => (l.ai_readiness_score ?? 0) >= 80).length;
  const needsAttention = loans.filter((l) => l.conditions_open > 0).length;

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-(--color-text)">UW Pipeline</h1>
          <p className="text-sm text-(--color-text-secondary) mt-1">
            {loans.length} loans &middot; {readyCount} AI-ready &middot; {needsAttention} need attention
          </p>
        </div>
        <div className="flex items-center gap-2">
          {["", "submitted_to_uw", "conditionally_approved", "clear_to_close"].map((s) => (
            <button
              key={s}
              onClick={() => setFilter(s)}
              className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
                filter === s
                  ? "bg-(--color-accent) text-white"
                  : "bg-(--color-surface) text-(--color-text-secondary) border border-(--color-border) hover:bg-gray-50"
              }`}
            >
              {s === "" ? "All" : formatStatus(s)}
            </button>
          ))}
        </div>
      </div>

      {loading ? (
        <div className="flex justify-center py-20">
          <div className="w-6 h-6 border-2 border-(--color-accent) border-t-transparent rounded-full animate-spin" />
        </div>
      ) : (
        <div className="bg-(--color-surface) rounded-xl border border-(--color-border) overflow-hidden">
          <table className="w-full">
            <thead>
              <tr className="border-b border-(--color-border) bg-gray-50/50">
                <th className="text-left px-4 py-3 text-xs font-semibold text-(--color-text-secondary) uppercase tracking-wide">Borrower</th>
                <th className="text-left px-4 py-3 text-xs font-semibold text-(--color-text-secondary) uppercase tracking-wide">LO</th>
                <th className="text-left px-4 py-3 text-xs font-semibold text-(--color-text-secondary) uppercase tracking-wide">Amount</th>
                <th className="text-left px-4 py-3 text-xs font-semibold text-(--color-text-secondary) uppercase tracking-wide">Persona</th>
                <th className="text-left px-4 py-3 text-xs font-semibold text-(--color-text-secondary) uppercase tracking-wide">Phase</th>
                <th className="text-center px-4 py-3 text-xs font-semibold text-(--color-text-secondary) uppercase tracking-wide">FICO</th>
                <th className="text-center px-4 py-3 text-xs font-semibold text-(--color-text-secondary) uppercase tracking-wide">DTI</th>
                <th className="text-center px-4 py-3 text-xs font-semibold text-(--color-text-secondary) uppercase tracking-wide">LTV</th>
                <th className="text-center px-4 py-3 text-xs font-semibold text-(--color-text-secondary) uppercase tracking-wide">Docs</th>
                <th className="text-center px-4 py-3 text-xs font-semibold text-(--color-text-secondary) uppercase tracking-wide">Conds</th>
                <th className="text-center px-4 py-3 text-xs font-semibold text-(--color-text-secondary) uppercase tracking-wide">AI Score</th>
                <th className="text-left px-4 py-3 text-xs font-semibold text-(--color-text-secondary) uppercase tracking-wide">Status</th>
              </tr>
            </thead>
            <tbody>
              {loans.map((loan) => (
                <tr
                  key={loan.loan_id}
                  className="border-b border-(--color-border) last:border-0 hover:bg-gray-50/50 transition-colors"
                >
                  <td className="px-4 py-3">
                    <Link
                      href={`/review/${loan.loan_id}`}
                      className="font-medium text-sm text-(--color-text) hover:text-(--color-accent)"
                    >
                      {loan.borrower_name || "—"}
                    </Link>
                    {loan.encompass_loan_number && (
                      <div className="text-xs text-(--color-text-muted) font-mono">{loan.encompass_loan_number}</div>
                    )}
                  </td>
                  <td className="px-4 py-3 text-sm text-(--color-text-secondary)">{loan.loan_officer_name || "—"}</td>
                  <td className="px-4 py-3 text-sm font-medium">{formatCurrency(loan.loan_amount)}</td>
                  <td className="px-4 py-3">
                    <span className="text-xs font-medium text-blue-700">{formatPersona(loan.primary_borrower_persona)}</span>
                  </td>
                  <td className="px-4 py-3 text-sm text-(--color-text-secondary)">{formatPhase(loan.processing_phase)}</td>
                  <td className="px-4 py-3 text-center text-sm font-medium">{loan.credit_score || "—"}</td>
                  <td className="px-4 py-3 text-center text-sm">{formatPercent(loan.dti_back)}</td>
                  <td className="px-4 py-3 text-center text-sm">{formatPercent(loan.ltv)}</td>
                  <td className="px-4 py-3 text-center">
                    <span className="text-xs">
                      <span className="font-medium text-green-600">{loan.documents_validated}</span>
                      <span className="text-(--color-text-muted)">/{loan.documents_uploaded}</span>
                    </span>
                  </td>
                  <td className="px-4 py-3 text-center">
                    {loan.conditions_total > 0 ? (
                      <span className="text-xs">
                        <span className={loan.conditions_open > 0 ? "font-medium text-red-500" : "text-green-600"}>
                          {loan.conditions_open}
                        </span>
                        <span className="text-(--color-text-muted)">/{loan.conditions_total}</span>
                      </span>
                    ) : (
                      <span className="text-xs text-(--color-text-muted)">—</span>
                    )}
                  </td>
                  <td className="px-4 py-3 text-center">
                    <span className={`text-sm font-bold ${readinessColor(loan.ai_readiness_score)}`}>
                      {loan.ai_readiness_score != null ? loan.ai_readiness_score.toFixed(0) : "—"}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${statusColor(loan.status)}`}>
                      {formatStatus(loan.status)}
                    </span>
                  </td>
                </tr>
              ))}
              {loans.length === 0 && (
                <tr>
                  <td colSpan={12} className="px-4 py-12 text-center text-sm text-(--color-text-secondary)">
                    No loans in pipeline
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
