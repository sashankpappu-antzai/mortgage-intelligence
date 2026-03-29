# CLAUDE.md — mortgage-intelligence frontend

> Read this before writing, editing, or reviewing any frontend code in this project.

---

## What This Is

Frontend for **mortgage-intelligence** — Next.js 15 with three portals: LO Dashboard, UW Pipeline, and Borrower Portal.

**Stack:** Next.js 15 (App Router), React 19, TypeScript, Tailwind CSS v4, Zustand

---

## Structure

```
frontend/
├── app/
│   ├── layout.tsx                      # Root layout + metadata
│   ├── page.tsx                        # Auth redirect (LO→/loans, UW→/pipeline)
│   ├── globals.css                     # Tailwind v4 @theme tokens
│   ├── (auth)/
│   │   ├── login/page.tsx              # Email/password login
│   │   └── register/page.tsx           # Registration with role selection
│   ├── (dashboard)/
│   │   ├── layout.tsx                  # Shared nav (role-based menu items)
│   │   ├── loans/page.tsx              # LO loan list table
│   │   ├── loans/new/page.tsx          # Create loan form → auto persona
│   │   ├── loans/[loanId]/page.tsx     # Loan detail + checklist + upload
│   │   └── pipeline/page.tsx           # UW pipeline (FICO, DTI, LTV, AI score)
│   ├── (uw)/
│   │   └── review/[loanId]/page.tsx    # UW single-view dashboard (M6)
│   └── (borrower)/                     # Borrower self-service portal (M7)
├── lib/
│   ├── api.ts                          # Typed API client (all endpoints + SSE)
│   ├── auth.ts                         # Zustand auth store (JWT + localStorage)
│   └── utils.ts                        # Formatters (currency, persona, status, colors)
├── next.config.ts                      # API rewrite proxy to backend
├── tsconfig.json                       # Path alias: @/* → ./*
├── postcss.config.mjs                  # Tailwind v4 PostCSS plugin
└── package.json
```

---

## Conventions

- Path alias: `@/lib/api`, `@/app/...` — maps to `frontend/*`
- Role-based routing: LOs see `/loans`, UWs see `/pipeline`
- API calls through `lib/api.ts` (typed client) — never raw `fetch`
- Auth state in `lib/auth.ts` (Zustand store) — hydrate on mount
- Tailwind v4 CSS-based config via `@theme {}` in `globals.css`
- All pages are `"use client"` for now (SSR optimization comes in M6+)

---

## Running

```bash
npm install
npm run dev
```
