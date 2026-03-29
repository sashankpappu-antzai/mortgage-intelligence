"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { createLoan } from "@/lib/api";

export default function NewLoanPage() {
  const router = useRouter();
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [form, setForm] = useState({
    loan_purpose: "purchase",
    occupancy_type: "primary",
    property_type: "single_family",
    loan_amount: "",
    purchase_price: "",
    borrower_first_name: "",
    borrower_last_name: "",
    borrower_email: "",
    employment_type: "w2",
    self_employed: false,
    ownership_percentage: 0,
  });

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      const incomeSourceKey = form.self_employed ? "self_employment" : "base_salary";
      const loan = await createLoan({
        loan_purpose: form.loan_purpose,
        occupancy_type: form.occupancy_type,
        property_type: form.property_type,
        loan_amount: form.loan_amount ? parseFloat(form.loan_amount) : undefined,
        purchase_price: form.purchase_price ? parseFloat(form.purchase_price) : undefined,
        borrowers: [
          {
            first_name: form.borrower_first_name,
            last_name: form.borrower_last_name,
            email: form.borrower_email || undefined,
            borrower_type: "primary",
            employment_type: form.employment_type,
            self_employed: form.self_employed,
            ownership_percentage: form.self_employed ? form.ownership_percentage : undefined,
            income_sources: { [incomeSourceKey]: 1 },
          },
        ],
      });
      router.push(`/loans/${loan.id}`);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to create loan");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="max-w-2xl">
      <Link href="/loans" className="text-sm text-(--color-text-secondary) hover:text-(--color-accent) mb-4 inline-block">
        &larr; Back to Loans
      </Link>
      <h1 className="text-2xl font-bold mb-6">New Loan</h1>

      {error && <div className="mb-4 p-3 rounded-lg bg-red-50 text-red-700 text-sm">{error}</div>}

      <form onSubmit={handleSubmit} className="space-y-6">
        {/* Borrower */}
        <div className="bg-(--color-surface) border border-(--color-border) rounded-lg p-6">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-(--color-text-secondary) mb-4">Primary Borrower</h2>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium mb-1.5">First Name</label>
              <input
                value={form.borrower_first_name}
                onChange={(e) => setForm({ ...form, borrower_first_name: e.target.value })}
                required
                className="w-full px-3 py-2 rounded-lg border border-(--color-border) text-sm focus:outline-none focus:ring-2 focus:ring-(--color-accent)/30"
              />
            </div>
            <div>
              <label className="block text-sm font-medium mb-1.5">Last Name</label>
              <input
                value={form.borrower_last_name}
                onChange={(e) => setForm({ ...form, borrower_last_name: e.target.value })}
                required
                className="w-full px-3 py-2 rounded-lg border border-(--color-border) text-sm focus:outline-none focus:ring-2 focus:ring-(--color-accent)/30"
              />
            </div>
            <div className="col-span-2">
              <label className="block text-sm font-medium mb-1.5">Email</label>
              <input
                type="email"
                value={form.borrower_email}
                onChange={(e) => setForm({ ...form, borrower_email: e.target.value })}
                className="w-full px-3 py-2 rounded-lg border border-(--color-border) text-sm focus:outline-none focus:ring-2 focus:ring-(--color-accent)/30"
              />
            </div>
          </div>
        </div>

        {/* Employment */}
        <div className="bg-(--color-surface) border border-(--color-border) rounded-lg p-6">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-(--color-text-secondary) mb-4">Employment</h2>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium mb-1.5">Employment Type</label>
              <select
                value={form.employment_type}
                onChange={(e) => setForm({ ...form, employment_type: e.target.value, self_employed: e.target.value === "self_employed" })}
                className="w-full px-3 py-2 rounded-lg border border-(--color-border) text-sm focus:outline-none focus:ring-2 focus:ring-(--color-accent)/30"
              >
                <option value="w2">W-2 Salaried</option>
                <option value="self_employed">Self-Employed</option>
                <option value="commission">Commission/Variable</option>
                <option value="retired">Retired</option>
              </select>
            </div>
            {form.self_employed && (
              <div>
                <label className="block text-sm font-medium mb-1.5">Ownership %</label>
                <input
                  type="number"
                  min="0"
                  max="100"
                  value={form.ownership_percentage}
                  onChange={(e) => setForm({ ...form, ownership_percentage: parseFloat(e.target.value) || 0 })}
                  className="w-full px-3 py-2 rounded-lg border border-(--color-border) text-sm focus:outline-none focus:ring-2 focus:ring-(--color-accent)/30"
                />
              </div>
            )}
          </div>
        </div>

        {/* Loan Details */}
        <div className="bg-(--color-surface) border border-(--color-border) rounded-lg p-6">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-(--color-text-secondary) mb-4">Loan Details</h2>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium mb-1.5">Purpose</label>
              <select
                value={form.loan_purpose}
                onChange={(e) => setForm({ ...form, loan_purpose: e.target.value })}
                className="w-full px-3 py-2 rounded-lg border border-(--color-border) text-sm focus:outline-none focus:ring-2 focus:ring-(--color-accent)/30"
              >
                <option value="purchase">Purchase</option>
                <option value="refinance">Refinance</option>
                <option value="cashout_refi">Cash-Out Refinance</option>
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium mb-1.5">Occupancy</label>
              <select
                value={form.occupancy_type}
                onChange={(e) => setForm({ ...form, occupancy_type: e.target.value })}
                className="w-full px-3 py-2 rounded-lg border border-(--color-border) text-sm focus:outline-none focus:ring-2 focus:ring-(--color-accent)/30"
              >
                <option value="primary">Primary Residence</option>
                <option value="secondary">Second Home</option>
                <option value="investment">Investment Property</option>
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium mb-1.5">Loan Amount</label>
              <input
                type="number"
                value={form.loan_amount}
                onChange={(e) => setForm({ ...form, loan_amount: e.target.value })}
                placeholder="350000"
                className="w-full px-3 py-2 rounded-lg border border-(--color-border) text-sm focus:outline-none focus:ring-2 focus:ring-(--color-accent)/30"
              />
            </div>
            <div>
              <label className="block text-sm font-medium mb-1.5">
                {form.loan_purpose === "purchase" ? "Purchase Price" : "Property Value"}
              </label>
              <input
                type="number"
                value={form.purchase_price}
                onChange={(e) => setForm({ ...form, purchase_price: e.target.value })}
                placeholder="450000"
                className="w-full px-3 py-2 rounded-lg border border-(--color-border) text-sm focus:outline-none focus:ring-2 focus:ring-(--color-accent)/30"
              />
            </div>
          </div>
        </div>

        <div className="flex items-center gap-3">
          <button
            type="submit"
            disabled={loading}
            className="px-6 py-2.5 bg-(--color-accent) hover:bg-(--color-accent-hover) text-white font-medium rounded-lg text-sm transition-colors disabled:opacity-50"
          >
            {loading ? "Creating..." : "Create Loan"}
          </button>
          <Link href="/loans" className="px-4 py-2.5 text-sm text-(--color-text-secondary) hover:text-(--color-text)">
            Cancel
          </Link>
        </div>
      </form>
    </div>
  );
}
