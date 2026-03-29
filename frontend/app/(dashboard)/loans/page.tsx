"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { listLoans, type LoanSummary } from "@/lib/api";
import { formatCurrency, formatPersona, formatPhase, formatStatus, statusColor } from "@/lib/utils";

export default function LoansPage() {
  const [loans, setLoans] = useState<LoanSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [showCreate, setShowCreate] = useState(false);

  useEffect(() => {
    loadLoans();
  }, []);

  async function loadLoans() {
    try {
      const data = await listLoans();
      setLoans(data);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to load loans");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-(--color-text)">My Loans</h1>
          <p className="text-sm text-(--color-text-secondary) mt-1">
            {loans.length} loan{loans.length !== 1 ? "s" : ""} in your pipeline
          </p>
        </div>
        <Link
          href="/loans/new"
          className="px-4 py-2 bg-(--color-accent) hover:bg-(--color-accent-hover) text-white font-medium rounded-lg text-sm transition-colors"
        >
          + New Loan
        </Link>
      </div>

      {error && <div className="p-4 rounded-lg bg-red-50 text-red-700 text-sm mb-4">{error}</div>}

      {loading ? (
        <div className="flex justify-center py-20">
          <div className="w-6 h-6 border-2 border-(--color-accent) border-t-transparent rounded-full animate-spin" />
        </div>
      ) : loans.length === 0 ? (
        <div className="text-center py-20 bg-(--color-surface) rounded-xl border border-(--color-border)">
          <div className="text-4xl mb-3">📋</div>
          <h3 className="text-lg font-semibold text-(--color-text)">No loans yet</h3>
          <p className="text-sm text-(--color-text-secondary) mt-1">Create your first loan to get started</p>
          <Link
            href="/loans/new"
            className="inline-block mt-4 px-4 py-2 bg-(--color-accent) text-white rounded-lg text-sm font-medium"
          >
            Create Loan
          </Link>
        </div>
      ) : (
        <div className="bg-(--color-surface) rounded-xl border border-(--color-border) overflow-hidden">
          <table className="w-full">
            <thead>
              <tr className="border-b border-(--color-border) bg-gray-50/50">
                <th className="text-left px-4 py-3 text-xs font-semibold text-(--color-text-secondary) uppercase tracking-wide">Borrower</th>
                <th className="text-left px-4 py-3 text-xs font-semibold text-(--color-text-secondary) uppercase tracking-wide">Loan #</th>
                <th className="text-left px-4 py-3 text-xs font-semibold text-(--color-text-secondary) uppercase tracking-wide">Amount</th>
                <th className="text-left px-4 py-3 text-xs font-semibold text-(--color-text-secondary) uppercase tracking-wide">Purpose</th>
                <th className="text-left px-4 py-3 text-xs font-semibold text-(--color-text-secondary) uppercase tracking-wide">Persona</th>
                <th className="text-left px-4 py-3 text-xs font-semibold text-(--color-text-secondary) uppercase tracking-wide">Phase</th>
                <th className="text-left px-4 py-3 text-xs font-semibold text-(--color-text-secondary) uppercase tracking-wide">Status</th>
                <th className="text-right px-4 py-3 text-xs font-semibold text-(--color-text-secondary) uppercase tracking-wide">AI Score</th>
              </tr>
            </thead>
            <tbody>
              {loans.map((loan) => (
                <tr
                  key={loan.id}
                  className="border-b border-(--color-border) last:border-0 hover:bg-gray-50/50 transition-colors cursor-pointer"
                >
                  <td className="px-4 py-3">
                    <Link href={`/loans/${loan.id}`} className="font-medium text-sm text-(--color-text) hover:text-(--color-accent)">
                      {loan.borrower_name || "—"}
                    </Link>
                  </td>
                  <td className="px-4 py-3 text-sm text-(--color-text-secondary) font-mono">
                    {loan.encompass_loan_number || "—"}
                  </td>
                  <td className="px-4 py-3 text-sm font-medium">{formatCurrency(loan.loan_amount)}</td>
                  <td className="px-4 py-3 text-sm text-(--color-text-secondary) capitalize">{loan.loan_purpose || "—"}</td>
                  <td className="px-4 py-3">
                    <span className="inline-block px-2 py-0.5 rounded-full text-xs font-medium bg-blue-50 text-blue-700">
                      {formatPersona(loan.primary_borrower_persona)}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-sm text-(--color-text-secondary)">{formatPhase(loan.processing_phase)}</td>
                  <td className="px-4 py-3">
                    <span className={`inline-block px-2 py-0.5 rounded-full text-xs font-medium ${statusColor(loan.status)}`}>
                      {formatStatus(loan.status)}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-right">
                    {loan.ai_readiness_score != null ? (
                      <span className={`font-bold text-sm ${loan.ai_readiness_score >= 80 ? "text-green-600" : loan.ai_readiness_score >= 50 ? "text-yellow-600" : "text-red-500"}`}>
                        {loan.ai_readiness_score.toFixed(0)}
                      </span>
                    ) : (
                      <span className="text-gray-300 text-sm">—</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
