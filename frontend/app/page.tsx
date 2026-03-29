"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth";

export default function Home() {
  const router = useRouter();
  const { user, hydrate, isLoading } = useAuth();

  useEffect(() => {
    hydrate();
  }, [hydrate]);

  useEffect(() => {
    if (!isLoading) {
      if (user) {
        if (user.role === "underwriter") {
          router.push("/pipeline");
        } else {
          router.push("/loans");
        }
      } else {
        router.push("/login");
      }
    }
  }, [user, isLoading, router]);

  return (
    <div className="min-h-screen flex items-center justify-center bg-(--color-bg)">
      <div className="text-center">
        <div className="w-8 h-8 border-2 border-(--color-accent) border-t-transparent rounded-full animate-spin mx-auto" />
        <p className="mt-4 text-(--color-text-secondary) text-sm">Loading...</p>
      </div>
    </div>
  );
}
