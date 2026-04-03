"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { login, getMicrosoftConfig, type MicrosoftConfig } from "@/lib/api";
import { useAuth } from "@/lib/auth";

export default function LoginPage() {
  const router = useRouter();
  const { setAuth } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [msConfig, setMsConfig] = useState<MicrosoftConfig | null>(null);

  useEffect(() => {
    getMicrosoftConfig()
      .then(setMsConfig)
      .catch(() => setMsConfig({ configured: false }));
  }, []);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      const res = await login(email, password);
      setAuth(res.user, res.access_token, res.refresh_token);
      router.push(res.user.role === "underwriter" ? "/pipeline" : "/loans");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Login failed");
    } finally {
      setLoading(false);
    }
  }

  function handleMicrosoftSignIn() {
    if (!msConfig?.configured || !msConfig.tenant_id || !msConfig.client_id) return;
    const redirectUri = msConfig.redirect_uri || `${window.location.origin}/auth/microsoft/callback`;
    const params = new URLSearchParams({
      client_id: msConfig.client_id,
      response_type: "code",
      redirect_uri: redirectUri,
      scope: "openid profile email",
      response_mode: "query",
    });
    window.location.href = `https://login.microsoftonline.com/${msConfig.tenant_id}/oauth2/v2.0/authorize?${params}`;
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
          <p className="text-sm text-(--color-text-secondary)">AI-Powered Loan Processing</p>
        </div>

        <div className="bg-(--color-surface) rounded-xl p-8 shadow-sm border border-(--color-border)">
          <h2 className="text-lg font-semibold mb-6">Sign In</h2>

          {error && (
            <div className="mb-4 p-3 rounded-lg bg-red-50 text-red-700 text-sm">{error}</div>
          )}

          {msConfig?.configured && (
            <>
              <button
                type="button"
                onClick={handleMicrosoftSignIn}
                className="w-full flex items-center justify-center gap-3 py-2.5 border border-(--color-border) rounded-lg text-sm font-medium text-(--color-text) hover:bg-gray-50 transition-colors"
              >
                <svg width="20" height="20" viewBox="0 0 21 21" fill="none">
                  <rect x="1" y="1" width="9" height="9" fill="#F25022" />
                  <rect x="11" y="1" width="9" height="9" fill="#7FBA00" />
                  <rect x="1" y="11" width="9" height="9" fill="#00A4EF" />
                  <rect x="11" y="11" width="9" height="9" fill="#FFB900" />
                </svg>
                Sign in with Microsoft
              </button>

              <div className="relative my-6">
                <div className="absolute inset-0 flex items-center">
                  <div className="w-full border-t border-(--color-border)" />
                </div>
                <div className="relative flex justify-center text-xs">
                  <span className="bg-(--color-surface) px-3 text-(--color-text-secondary)">or continue with email</span>
                </div>
              </div>
            </>
          )}

          <form onSubmit={handleSubmit}>
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-(--color-text) mb-1.5">Email</label>
                <input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  required
                  className="w-full px-3 py-2 rounded-lg border border-(--color-border) text-sm focus:outline-none focus:ring-2 focus:ring-(--color-accent)/30 focus:border-(--color-accent)"
                  placeholder="you@company.com"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-(--color-text) mb-1.5">Password</label>
                <input
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                  className="w-full px-3 py-2 rounded-lg border border-(--color-border) text-sm focus:outline-none focus:ring-2 focus:ring-(--color-accent)/30 focus:border-(--color-accent)"
                />
              </div>
            </div>

            <button
              type="submit"
              disabled={loading}
              className="w-full mt-6 py-2.5 bg-(--color-accent) hover:bg-(--color-accent-hover) text-white font-medium rounded-lg text-sm transition-colors disabled:opacity-50"
            >
              {loading ? "Signing in..." : "Sign In"}
            </button>
          </form>

          <p className="mt-4 text-center text-sm text-(--color-text-secondary)">
            Don&apos;t have an account?{" "}
            <Link href="/register" className="text-(--color-accent) hover:underline font-medium">Register</Link>
          </p>
        </div>
      </div>
    </div>
  );
}
