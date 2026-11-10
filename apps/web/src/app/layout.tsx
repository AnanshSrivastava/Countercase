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
  title: "Recoup",
  description: "Memory-driven chargeback defense for small online sellers",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  const fixtureMode = process.env.NEXT_PUBLIC_USE_FIXTURES === "1";
  return (
    <html lang="en" className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}>
      <body className="flex min-h-full flex-col bg-zinc-50 text-zinc-900 dark:bg-zinc-950 dark:text-zinc-100">
        <header className="border-b border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-900">
          <div className="mx-auto flex w-full max-w-5xl items-center justify-between gap-4 px-4 py-3">
            <Link href="/" className="text-lg font-semibold tracking-tight">
              Recoup
            </Link>
            <nav className="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm">
              <Link href="/" className="text-zinc-600 hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-zinc-100">
                Inbox
              </Link>
              <Link href="/insights" className="text-zinc-600 hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-zinc-100">
                Insights
              </Link>
              <Link href="/alerts" className="text-zinc-600 hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-zinc-100">
                Alerts
              </Link>
              <Link href="/playbook" className="text-zinc-600 hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-zinc-100">
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
        <main className="mx-auto w-full max-w-5xl flex-1 px-4 py-6">{children}</main>
      </body>
    </html>
  );
}
