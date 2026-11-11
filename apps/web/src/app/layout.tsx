import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import Link from "next/link";
import { Suspense } from "react";
import { DemoBadge } from "@/components/DemoBadge";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "Countercase",
  description: "A clear, confident workspace for managing payment disputes",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  const fixtureMode = process.env.NEXT_PUBLIC_USE_FIXTURES === "1";
  return (
    <html lang="en" className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}>
      <body className="flex min-h-full flex-col bg-[#f6f7f9] text-zinc-900 dark:bg-zinc-950 dark:text-zinc-100">
        <header className="sticky top-0 z-20 border-b border-zinc-200/80 bg-white/95 backdrop-blur dark:border-zinc-800 dark:bg-zinc-900/95">
          <div className="mx-auto flex w-full max-w-7xl items-center justify-between gap-4 px-5 py-3">
            <Link href="/" className="group flex items-center gap-2.5 text-lg font-semibold tracking-tight">
              <span className="grid h-8 w-8 place-items-center rounded-lg bg-blue-700 text-sm font-bold text-white shadow-sm shadow-blue-900/20 transition group-hover:bg-blue-800">C</span>
              <span>Countercase</span>
            </Link>
            <nav className="flex flex-wrap items-center gap-x-1 gap-y-1 text-sm">
              <Link href="/" className="rounded-md bg-blue-50 px-3 py-2 font-medium text-blue-800 dark:bg-blue-950/60 dark:text-blue-200">
                Inbox
              </Link>
              <Link href="/insights" className="rounded-md px-3 py-2 text-zinc-600 transition hover:bg-zinc-100 hover:text-zinc-900 dark:text-zinc-400 dark:hover:bg-zinc-800 dark:hover:text-zinc-100">
                Insights
              </Link>
              <Link href="/alerts" className="rounded-md px-3 py-2 text-zinc-600 transition hover:bg-zinc-100 hover:text-zinc-900 dark:text-zinc-400 dark:hover:bg-zinc-800 dark:hover:text-zinc-100">
                Alerts
              </Link>
              <Link href="/playbook" className="rounded-md px-3 py-2 text-zinc-600 transition hover:bg-zinc-100 hover:text-zinc-900 dark:text-zinc-400 dark:hover:bg-zinc-800 dark:hover:text-zinc-100">
                Playbook
              </Link>
              <Suspense fallback={null}>
                <DemoBadge />
              </Suspense>
              {fixtureMode && (
                <span
                  className="rounded-full bg-violet-100 px-2 py-0.5 text-xs font-medium text-violet-800 dark:bg-violet-950 dark:text-violet-200"
                  title="Data comes from fixtures/. Deadlines are shifted relative to now."
                >
                  Fixture mode
                </span>
              )}
            </nav>
          </div>
        </header>
        <main className="mx-auto w-full max-w-7xl flex-1 px-5 py-8">{children}</main>
      </body>
    </html>
  );
}
