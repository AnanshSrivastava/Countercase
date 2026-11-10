import Link from "next/link";
import { Suspense } from "react";

import { getAlerts } from "@/lib/alerts-data";
import type { Alert } from "@/lib/alerts-data";

import { checkDeadlinesNow } from "./actions";

export const metadata = { title: "Deadline alerts · Recoup" };

const card = "rounded-lg border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-900";

export default function AlertsPage() {
  return (
    <div className="flex flex-col gap-6">
      <header>
        <h1 className="text-2xl font-semibold">Deadline alerts</h1>
        <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">
          Recoup warns you 72, 24 and 6 hours before a response is due, only for disputes still waiting on you. Each
          warning is sent once.
        </p>
      </header>
      <form action={checkDeadlinesNow}>
        <button
          type="submit"
          className="rounded-md bg-zinc-900 px-3 py-1.5 text-sm font-medium text-white dark:bg-zinc-100 dark:text-zinc-900"
        >
          Check deadlines now
        </button>
      </form>
      <Suspense fallback={<div className="h-24 animate-pulse rounded-lg bg-zinc-200/70 dark:bg-zinc-800" />}>
        <AlertList />
      </Suspense>
    </div>
  );
}

async function AlertList() {
  const { alerts, unavailable } = await getAlerts();
  if (unavailable) {
    return (
      <p className="rounded-md bg-amber-50 p-3 text-sm text-amber-900 dark:bg-amber-950 dark:text-amber-200">
        {unavailable}
      </p>
    );
  }
  if (alerts.length === 0) {
    return <p className={`${card} text-sm text-zinc-600 dark:text-zinc-400`}>No alerts yet. Nothing is close to its deadline.</p>;
  }
  return (
    <ul className="flex flex-col gap-3">
      {alerts.map((a) => (
        <AlertCard key={a.id} a={a} />
      ))}
    </ul>
  );
}

function AlertCard({ a }: { a: Alert }) {
  const tone =
    a.threshold_hours === 6
      ? "bg-red-100 text-red-900 dark:bg-red-950 dark:text-red-200"
      : a.threshold_hours === 24
        ? "bg-orange-100 text-orange-900 dark:bg-orange-950 dark:text-orange-200"
        : "bg-amber-100 text-amber-900 dark:bg-amber-950 dark:text-amber-200";
  return (
    <li className={card}>
      <div className="flex flex-wrap items-center gap-2 text-xs">
        <span className={`rounded px-1.5 py-0.5 font-medium ${tone}`}>{a.threshold_hours}h warning</span>
        {a.channel === "simulated" ? (
          <span className="rounded bg-violet-100 px-1.5 py-0.5 font-medium text-violet-900 dark:bg-violet-950 dark:text-violet-200">
            Simulated email — nothing was delivered
          </span>
        ) : (
          <span className="rounded bg-emerald-100 px-1.5 py-0.5 font-medium text-emerald-900 dark:bg-emerald-950 dark:text-emerald-200">
            Email sent{a.to_address ? ` to ${a.to_address}` : ""}
          </span>
        )}
        {a.status === "failed" && (
          <span className="rounded bg-red-100 px-1.5 py-0.5 font-medium text-red-900 dark:bg-red-950 dark:text-red-200">
            Failed: {a.error}
          </span>
        )}
        {a.sent_at && <span className="text-zinc-500 dark:text-zinc-400">{new Date(a.sent_at).toUTCString()}</span>}
      </div>
      <p className="mt-2 font-medium">{a.subject}</p>
      <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">{a.body}</p>
      <Link href={`/disputes/${a.dispute_id}`} className="mt-2 inline-block text-sm text-sky-700 hover:underline dark:text-sky-400">
        Open dispute →
      </Link>
    </li>
  );
}
