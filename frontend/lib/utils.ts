import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatCurrency(amount: number | null | undefined): string {
  if (amount == null) return "--";
  return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 }).format(amount);
}

export function formatPercent(value: number | null | undefined): string {
  if (value == null) return "--";
  return `${value.toFixed(1)}%`;
}

export function formatPersona(persona: string | null | undefined): string {
  if (!persona) return "Unknown";
  const map: Record<string, string> = {
    w2_salaried: "W-2 Salaried",
    self_employed: "Self-Employed",
    commission_variable: "Commission/Variable",
    retired_fixed: "Retired/Fixed",
    rental_income: "Rental Income",
  };
  return map[persona] || persona;
}

export function formatPhase(phase: string | null | undefined): string {
  if (!phase) return "Unknown";
  const map: Record<string, string> = {
    phase_0_intake: "Intake",
    phase_1_aus_credit: "AUS & Credit",
    phase_2_doc_collection: "Doc Collection",
    phase_3_data_verification: "Verification",
    phase_4_third_party: "Third Party",
    phase_5_uw_submission: "UW Submission",
    phase_6_closing: "Closing",
  };
  return map[phase] || phase;
}

export function formatStatus(status: string): string {
  return status.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

export function statusColor(status: string): string {
  const colors: Record<string, string> = {
    created: "bg-gray-100 text-gray-700",
    intake: "bg-blue-100 text-blue-700",
    processing: "bg-yellow-100 text-yellow-700",
    submitted_to_uw: "bg-purple-100 text-purple-700",
    conditionally_approved: "bg-orange-100 text-orange-700",
    clear_to_close: "bg-green-100 text-green-700",
    closing: "bg-emerald-100 text-emerald-700",
    funded: "bg-green-200 text-green-800",
    suspended: "bg-red-100 text-red-700",
    denied: "bg-red-200 text-red-800",
  };
  return colors[status] || "bg-gray-100 text-gray-700";
}

export function readinessColor(score: number | null | undefined): string {
  if (score == null) return "text-gray-400";
  if (score >= 80) return "text-green-600";
  if (score >= 50) return "text-yellow-600";
  return "text-red-600";
}

export function checklistStatusIcon(status: string): { icon: string; color: string } {
  switch (status) {
    case "validated":
      return { icon: "\u2713", color: "text-green-600 bg-green-50" };
    case "uploaded":
      return { icon: "\u2022", color: "text-blue-600 bg-blue-50" };
    case "rejected":
      return { icon: "\u2717", color: "text-red-600 bg-red-50" };
    default:
      return { icon: "\u25CB", color: "text-gray-400 bg-gray-50" };
  }
}
