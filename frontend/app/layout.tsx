import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Mortgage Processor | AI-Powered Loan Processing",
  description: "Intelligent mortgage processing platform for conventional loans",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="antialiased">{children}</body>
    </html>
  );
}
