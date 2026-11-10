import Link from "next/link";
import { Suspense } from "react";

import { saveDirective } from "@/features/memory/actions";
import { BeliefChanges } from "@/features/memory/MemoryTab";
import { getBeliefChanges, getPlaybook } from "@/features/memory/data";
import type { Belief } from "@/features/memory/types";

export const metadata = { title: "Seller Playbook · Recoup" };

const card = "rounded-lg border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-900";

export default function PlaybookPage() {
  return (
    <div className="flex flex-col gap-6">
      <Link href="/" className="text-sm text-zinc-600 hover:underline dark:text-zinc-400">
        ← Inbox
      </Link>
      <Suspense fallback={<div className="h-40 animate-pulse rounded-lg bg-zinc-200/70 dark:bg-zinc-800" />}>
        <PlaybookContent />
      </Suspense>
    </div>
  );
}

async function PlaybookContent() {
  const [pb, changes] = await Promise.all([getPlaybook(), getBeliefChanges()]);
  const book = pb.data;

  return (
    <>
      <header>
        <h1 className="text-2xl font-semibold">Your Playbook</h1>
        <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">
          What Recoup has learned about your business
          {book ? ` from ${book.n_cases} resolved disputes` : ""}. Every line is counted from your own cases, with its
          confidence shown. Reject anything that looks wrong on a dispute&apos;s Memory tab.
        </p>
      </header>

      {pb.unavailable && (
        <p className="rounded-md bg-amber-50 p-3 text-sm text-amber-900 dark:bg-amber-950 dark:text-amber-200">
          {pb.unavailable}
        </p>
      )}

      {book && (
        <>
          <BeliefChanges changes={changes.data} />

          <Section title="Best evidence">
            <BeliefList items={book.best_evidence} empty="Not enough history yet." />
          </Section>

          <Section title="Risky couriers">
            <BeliefList items={book.risky_couriers} empty="None detected." />
          </Section>

          <Section title="Repeat disputers">
            {book.repeat_disputers.length === 0 ? (
              <p className="text-sm text-zinc-500">None.</p>
            ) : (
              <ul className="flex flex-col gap-1 text-sm">
                {book.repeat_disputers.map((r) => (
                  <li key={r.customer}>
                    <span className="font-mono text-xs">{r.customer}</span> — {r.disputes} disputes
                  </li>
                ))}
              </ul>
            )}
          </Section>

          <Section title="Your rules">
            {book.preferences.length === 0 ? (
              <p className="text-sm text-zinc-500">No rules saved yet.</p>
            ) : (
              <ul className="list-disc pl-5 text-sm">
                {book.preferences.map((p) => (
                  <li key={p}>{p}</li>
                ))}
              </ul>
            )}
            <form action={saveDirective} className="mt-3 flex gap-2">
              <input
                name="text"
                required
                placeholder="Add a rule, e.g. Never fight disputes under 20"
                className="min-w-0 flex-1 rounded-md border border-zinc-300 bg-white px-3 py-1.5 text-sm dark:border-zinc-700 dark:bg-zinc-950"
              />
              <button
                type="submit"
                className="rounded-md bg-zinc-900 px-3 py-1.5 text-sm font-medium text-white dark:bg-zinc-100 dark:text-zinc-900"
              >
                Save rule
              </button>
            </form>
            <p className="mt-1 text-xs text-zinc-500">Rules apply to every draft from now on.</p>
          </Section>
        </>
      )}
    </>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className={card}>
      <h2 className="font-semibold">{title}</h2>
      <div className="mt-2">{children}</div>
    </section>
  );
}

function BeliefList({ items, empty }: { items: Belief[]; empty: string }) {
  if (items.length === 0) return <p className="text-sm text-zinc-500">{empty}</p>;
  return (
    <ul className="flex flex-col gap-2 text-sm">
      {items.map((b) => (
        <li key={b.key}>
          {b.text}
          <span className="ml-2 text-xs text-zinc-500 dark:text-zinc-400">
            confidence {Math.round(b.confidence * 100)}% · {b.label} · n={b.n}
          </span>
        </li>
      ))}
    </ul>
  );
}
