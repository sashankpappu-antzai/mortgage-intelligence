"use client";

import { useState, useEffect, useRef } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { microsoftLogin, microsoftComplete } from "@/lib/api";
import { useAuth } from "@/lib/auth";

export default function MicrosoftCallbackPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { setAuth } = useAuth();
  const [status, setStatus] = useState<"loading" | "role_select" | "error">("loading");
  const [error, setError] = useState("");
  const [userInfo, setUserInfo] = useState<{ email: string; name: string; azure_ad_oid: string } | null>(null);
  const [role, setRole] = useState("loan_officer");
  const [tenantName, setTenantName] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const processed = useRef(false);

  const code = searchParams.get("code");
  const redirectUri = typeof window !== "undefined"
    ? `${window.location.origin}/auth/microsoft/callback`
    : "";

  useEffect(() => {
    if (!code || processed.current) return;
    processed.current = true;

    microsoftLogin(code, redirectUri)
      .then((res) => {
        if (res.access_token && res.user) {
          setAuth(res.user, res.access_token, res.refresh_token!);
          router.push(res.user.role === "underwriter" ? "/pipeline" : "/loans");
        } else if (res.needs_role) {
          setUserInfo({ email: res.email!, name: res.name!, azure_ad_oid: res.azure_ad_oid! });
          setStatus("role_select");
        }
      })
      .catch((err) => {
        setError(err instanceof Error ? err.message : "Microsoft sign-in failed");
        setStatus("error");
      });
  }, [code, redirectUri, router, setAuth]);

  async function handleComplete(e: React.FormEvent) {
    e.preventDefault();
    if (!code) return;
    setSubmitting(true);
    setError("");
    try {
      const res = await microsoftComplete({
        code,
        redirect_uri: redirectUri,
        role,
        tenant_name: tenantName || "Default",
      });
      setAuth(res.user, res.access_token, res.refresh_token);
      router.push(res.user.role === "underwriter" ? "/pipeline" : "/loans");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to complete sign-up");
      setSubmitting(false);
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-(--color-bg) px-4">
      <div className="w-full max-w-md">
        <div className="text-center mb-8">
          <div className="inline-flex items-center gap-2 mb-2">
            <div className="w-8 h-8 bg-(--color-accent) rounded-lg flex items-center justify-center">
              <span className="text-white font-bold text-sm">MP</span>
            </div>
            <h1 className="text-xl font-bold text-(--color-primary)">Mortgage Processor</h1>
          </div>
        </div>

        <div className="bg-(--color-surface) rounded-xl p-8 shadow-sm border border-(--color-border)">
          {status === "loading" && (
            <div className="text-center py-8">
              <div className="animate-spin w-8 h-8 border-2 border-(--color-accent) border-t-transparent rounded-full mx-auto mb-4" />
              <p className="text-sm text-(--color-text-secondary)">Signing in with Microsoft...</p>
            </div>
          )}

          {status === "error" && (
            <div className="text-center py-4">
              <div className="mb-4 p-3 rounded-lg bg-red-50 text-red-700 text-sm">{error}</div>
              <button
                onClick={() => router.push("/login")}
                className="text-sm text-(--color-accent) hover:underline font-medium"
              >
                Back to Sign In
              </button>
            </div>
          )}

          {status === "role_select" && userInfo && (
            <>
              <h2 className="text-lg font-semibold mb-2">Complete Your Account</h2>
              <p className="text-sm text-(--color-text-secondary) mb-6">
                Welcome, {userInfo.name}! Select your role to continue.
              </p>

              {error && (
                <div className="mb-4 p-3 rounded-lg bg-red-50 text-red-700 text-sm">{error}</div>
              )}

              <form onSubmit={handleComplete} className="space-y-4">
                <div>
                  <label className="block text-sm font-medium text-(--color-text) mb-1.5">Email</label>
                  <input
                    type="email"
                    value={userInfo.email}
                    disabled
                    className="w-full px-3 py-2 rounded-lg border border-(--color-border) text-sm bg-gray-50 text-(--color-text-secondary)"
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium text-(--color-text) mb-1.5">Role</label>
                  <select
                    value={role}
                    onChange={(e) => setRole(e.target.value)}
                    className="w-full px-3 py-2 rounded-lg border border-(--color-border) text-sm focus:outline-none focus:ring-2 focus:ring-(--color-accent)/30 focus:border-(--color-accent)"
                  >
                    <option value="loan_officer">Loan Officer</option>
                    <option value="underwriter">Underwriter</option>
                    <option value="admin">Admin</option>
                  </select>
                </div>

                <div>
                  <label className="block text-sm font-medium text-(--color-text) mb-1.5">Company Name</label>
                  <input
                    type="text"
                    value={tenantName}
                    onChange={(e) => setTenantName(e.target.value)}
                    placeholder="Your Company"
                    className="w-full px-3 py-2 rounded-lg border border-(--color-border) text-sm focus:outline-none focus:ring-2 focus:ring-(--color-accent)/30 focus:border-(--color-accent)"
                  />
                </div>

                <button
                  type="submit"
                  disabled={submitting}
                  className="w-full py-2.5 bg-(--color-accent) hover:bg-(--color-accent-hover) text-white font-medium rounded-lg text-sm transition-colors disabled:opacity-50"
                >
                  {submitting ? "Setting up..." : "Continue"}
                </button>
              </form>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
