"use client";

import Link from "next/link";

export default function UWReviewPage() {
  return (
    <div className="min-h-screen bg-(--color-bg) p-6">
      <Link href="/pipeline" className="text-sm text-(--color-text-secondary) hover:text-(--color-accent) mb-4 inline-block">
        &larr; Back to Pipeline
      </Link>
      <div className="bg-(--color-surface) border border-(--color-border) rounded-xl p-12 text-center">
        <div className="text-5xl mb-4">🏗️</div>
        <h2 className="text-xl font-bold text-(--color-text)">UW Review Dashboard</h2>
        <p className="text-sm text-(--color-text-secondary) mt-2 max-w-md mx-auto">
          The full UW single-view dashboard with validation matrix, income worksheets, condition tracker,
          document vault, risk flags, and audit trail will be built in Milestone 6.
        </p>
        <div className="mt-6 grid grid-cols-3 gap-4 max-w-lg mx-auto text-left">
          {[
            { label: "Validation Matrix", desc: "Agent results with confidence scores" },
            { label: "Income Worksheet", desc: "FNMA-compliant calculations" },
            { label: "Condition Tracker", desc: "PTD/PTF/PTC status & linked docs" },
            { label: "Document Vault", desc: "OCR overlay + verified flags" },
            { label: "Risk Flags", desc: "Fraud indicators + inconsistencies" },
            { label: "Audit Trail", desc: "Every agent decision logged" },
          ].map((item) => (
            <div key={item.label} className="p-3 bg-gray-50 rounded-lg">
              <div className="text-xs font-semibold text-(--color-text)">{item.label}</div>
              <div className="text-xs text-(--color-text-muted) mt-0.5">{item.desc}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
