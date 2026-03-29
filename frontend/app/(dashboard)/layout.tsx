"use client";

import { useEffect } from "react";
import { useRouter, usePathname } from "next/navigation";
import Link from "next/link";
import { useAuth } from "@/lib/auth";
import { cn } from "@/lib/utils";

const navItems = [
  { href: "/loans", label: "My Loans", roles: ["loan_officer", "admin", "processor"] },
  { href: "/pipeline", label: "UW Pipeline", roles: ["underwriter", "admin"] },
];

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const { user, hydrate, isLoading, logout } = useAuth();

  useEffect(() => {
    hydrate();
  }, [hydrate]);

  useEffect(() => {
    if (!isLoading && !user) {
      router.push("/login");
    }
  }, [user, isLoading, router]);

  if (isLoading || !user) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="w-6 h-6 border-2 border-(--color-accent) border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  const visibleNav = navItems.filter((item) => item.roles.includes(user.role));

  return (
    <div className="min-h-screen bg-(--color-bg)">
      {/* Top nav */}
      <header className="bg-(--color-primary) border-b-3 border-(--color-accent)">
        <div className="max-w-screen-2xl mx-auto px-6 flex items-center justify-between h-14">
          <div className="flex items-center gap-6">
            <Link href="/" className="flex items-center gap-2">
              <div className="w-7 h-7 bg-(--color-accent) rounded-md flex items-center justify-center">
                <span className="text-white font-bold text-xs">MP</span>
              </div>
              <span className="text-white font-semibold text-sm">Mortgage Processor</span>
            </Link>
            <nav className="flex items-center gap-1 ml-4">
              {visibleNav.map((item) => (
                <Link
                  key={item.href}
                  href={item.href}
                  className={cn(
                    "px-3 py-1.5 rounded-md text-sm font-medium transition-colors",
                    pathname.startsWith(item.href)
                      ? "bg-white/15 text-white"
                      : "text-white/60 hover:text-white hover:bg-white/10"
                  )}
                >
                  {item.label}
                </Link>
              ))}
            </nav>
          </div>
          <div className="flex items-center gap-4">
            <div className="text-right">
              <div className="text-white text-sm font-medium">{user.name}</div>
              <div className="text-white/50 text-xs capitalize">{user.role.replace("_", " ")}</div>
            </div>
            <button
              onClick={() => { logout(); router.push("/login"); }}
              className="px-3 py-1.5 text-white/60 hover:text-white text-sm transition-colors"
            >
              Sign Out
            </button>
          </div>
        </div>
      </header>

      {/* Content */}
      <main className="max-w-screen-2xl mx-auto px-6 py-6">{children}</main>
    </div>
  );
}
